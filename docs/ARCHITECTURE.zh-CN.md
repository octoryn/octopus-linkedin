[English](ARCHITECTURE.md) | **简体中文**

# 架构

Octopus LinkedIn 是一个小而受治理的 MCP server，夹在 MCP 客户端（Claude Desktop、
Claude Code，或任何兼容 MCP 的智能体）和官方 LinkedIn API 之间。

```
  MCP 客户端（Claude）
        │  MCP (stdio)
        ▼
  server.py  ── FastMCP，19 个核心工具 + 内容工具 + prompts/resources
        │
        ├── linkedin/drafts.py   本地草稿库，审核流程（不联网）
        ├── linkedin/scheduler.py 发布到点草稿；compare-and-set 发布关口
        ├── linkedin/llm.py       大模型客户端（Anthropic / OpenAI / Gemini）
        ├── linkedin/content.py   写/润色/优化/改写/AB/评论分诊；SSRF 防护抓取
        ├── linkedin/voice.py     本地品牌语气档案，注入生成提示
        └── linkedin/client.py    LinkedIn REST 封装
                  │
                  └── linkedin/auth.py   OAuth 2.0，令牌缓存 + 刷新
                          │  HTTPS
                          ▼
                  api.linkedin.com / www.linkedin.com
```

## 设计原则

**治理优先。** 草稿库纯本地。撰写、编辑、批准草稿都不联网。`publish_draft` 是唯一
把内容发出去的关口，且拒绝发布任何状态不是 `approved` 的草稿。这让默认就有一个人
（或一个明确的批准步骤）卡在发布前；同时也提供直接发布工具，供你不需要关口时使用。

**官方 API，合规路线。** 我们用 LinkedIn 文档化的端点 + OAuth + `w_member_social`
权限。不做浏览器自动化，不爬登录态。代价是有意收窄的能力面：你能发到自己的 feed、
评论你掌控的内容，但 API 不允许自动评论任意第三方帖子。

**内容由大模型驱动，但不可信输入有边界。** `repurpose_url` 抓取的网页、`triage_comments`
读到的第三方评论，都会被当作"数据而非指令"包裹后再交给大模型；抓取本身有 SSRF 防护
（只许公网 http(s)、DNS 绑定到连接、不自动跟随跳转）。

## 组件

| 文件 | 职责 |
|------|------|
| `server.py` | FastMCP server；定义并注册 30 个工具、3 个 prompts、2 个 resources |
| `linkedin/auth.py` | 三脚 OAuth，本地 `token.json` 缓存、刷新、重新授权 |
| `linkedin/client.py` | REST 调用：身份、发帖、评论、分析 |
| `linkedin/drafts.py` | 本地草稿库；draft→approved→publishing→published 流程，带文件锁与原子写 |
| `linkedin/scheduler.py` | 发布到点的已批准草稿；compare-and-set 发布关口 |
| `linkedin/llm.py` | 提供商无关的大模型客户端（Anthropic / OpenAI / Gemini） |
| `linkedin/content.py` | 写/润色/优化/改写/AB/分诊；带 SSRF 防护的 URL 抓取 |
| `linkedin/voice.py` | 本地品牌语气档案，渲染进生成系统提示 |

## 为什么用 `/v2/ugcPosts` 而非 `/rest/posts`

我们用经典的 `/v2/ugcPosts` 而不是带版本号的 Posts API，因为后者需要每约 12 个月就会
过期的 `LinkedIn-Version` 头；`ugcPosts` 配 `w_member_social` 即可，无需版本绑定。

## 令牌生命周期

`auth.py` 跑一次性浏览器流程，在 localhost 回调上捕获 OAuth code，换成令牌并写入
`token.json`（权限 `0600`）。`client.py` 通过 `get_access_token()` 读取，存在刷新令牌时
自动刷新，否则抛错并提示重新授权。成员访问令牌有效期约 60 天。

## 路线图

见 [README.zh-CN.md](../README.zh-CN.md) 的路线图部分。
