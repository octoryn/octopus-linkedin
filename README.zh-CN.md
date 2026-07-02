[English](README.md) | **简体中文**

# Octopus LinkedIn

[![PyPI](https://img.shields.io/pypi/v/octopus-linkedin.svg)](https://pypi.org/project/octopus-linkedin/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-brightgreen.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/protocol-MCP-8A2BE2.svg)](https://modelcontextprotocol.io)

> **[Octopus Core](https://github.com/octoryn) 的一部分 —— 受治理 AI 的开源基础设施栈。** 每个仓库只做一件事，沿 agent 生命周期组合：[Scout](https://github.com/octoryn/octopus-scout) · [Observe](https://github.com/octoryn/octopus-observe) · [Experience](https://github.com/octoryn/octopus-experience) · [Blackboard](https://github.com/octoryn/octopus-blackboard) · [Runtime](https://github.com/octoryn/octopus-runtime) · [Replay](https://github.com/octoryn/octopus-replay) —— [Inspect](https://github.com/octoryn/octopus-inspect) 横贯每一环做治理。
>
> **本仓库 —— LinkedIn · 治理示例：** 把 draft→approve→publish 的纪律用在真实外发。

**通过 MCP 进行受治理的 LinkedIn 营销。** 在 Claude Desktop、Claude Code 或任何
兼容 MCP 的智能体里，使用**官方 LinkedIn API** 起草、审核、发布、评论并查看互动数据。

大多数「LinkedIn AI」工具只做到帮你*写*帖子。显而易见的下一步是*发布*它——而这一步
你需要的是治理，而不是黑箱。Octopus LinkedIn 把整个闭环显式化：

> **起草 → 审核 → 批准 → 发布 → 评论 → 分析**

起草和批准都是**纯本地**的——全程不联网。`publish_draft` 是唯一把内容发出去的关口，
而且它会拒绝发布任何状态不是 `approved` 的草稿。

## 工具

| 工具 | 是否发往 LinkedIn | 作用 |
|------|:---:|--------------|
| `get_profile` | 读取 | 你的身份信息 + 连通性检查 |
| `create_post` | ✅ | 发布纯文本帖 |
| `share_link` | ✅ | 发布带链接预览卡的帖子 |
| `share_image` | ✅ | 发布带单张本地图片的帖子 |
| `share_images` | ✅ | 发布带最多 9 张图片的帖子 |
| `delete_post` | ✅ | 删除你的某条帖子 |
| `list_comments` | 读取 | 列出你帖子下的评论 |
| `reply_comment` | ✅ | 评论你掌控的内容 |
| `get_post_stats` | 读取 | 某帖的点赞数 + 评论数 |
| `create_draft` | ⬜ 本地 | 保存草稿（文本/链接/图片） |
| `list_drafts` | ⬜ 本地 | 列出草稿，可按状态过滤 |
| `get_draft` | ⬜ 本地 | 读取单条草稿 |
| `update_draft` | ⬜ 本地 | 编辑草稿（会重置批准状态） |
| `approve_draft` | ⬜ 本地 | **审核关口** |
| `delete_draft` | ⬜ 本地 | 删除草稿 |
| `schedule_draft` | ⬜ 本地 | 为已批准的草稿安排定时 |
| `unschedule_draft` | ⬜ 本地 | 清除草稿的定时 |
| `publish_draft` | ✅ | 立即发布一条**已批准**的草稿 |
| `publish_due` | ✅ | 发布所有到点的已批准草稿 |

### 内容智能（LLM 驱动）

全部以你的品牌语气为条件，且都在审核关口之内（不会绕过审核发布）。

| 工具 | 作用 |
|------|------|
| `llm_info` | 显示当前 LLM 提供商/模型（配置检查） |
| `generate_draft` | 从简述生成帖子 → 存为草稿 |
| `polish_text` / `polish_draft` | 润色，提升清晰度与流畅度 |
| `optimize_text` / `optimize_draft` | 针对开头钩子+结构+CTA 优化 |
| `ab_variants` | 生成 N 个不同的 A/B 变体 |
| `repurpose_url` | 把文章 URL 改写成原创草稿（已做 SSRF 防护） |
| `triage_comments` | 给你帖子下的评论分类 + 起草回复 |
| `get_voice` / `set_voice` | 读取/更新品牌语气档案 |

外加 MCP **prompts**（`draft_post`、`repurpose_article`、`reply_to_comments`）和
**resources**（`voice://profile`、`drafts://list`），让 MCP 客户端拿到任务模板和实时上下文。

**LLM 配置**：在 `.env` 里设一个提供商及其密钥：

```bash
LLM_PROVIDER=anthropic       # anthropic | openai | gemini
ANTHROPIC_API_KEY=sk-ant-... # 或 OPENAI_API_KEY / GEMINI_API_KEY
```

> **权限范围说明：** 官方 API 只允许你评论你所掌控的内容（你自己的帖子，或你管理的
> 公司主页）。它**无法**自动评论任意第三方帖子——这是设计使然。详见
> [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 快速开始

### 1. 安装

```bash
pip install octopus-linkedin
```

会装上两个命令：`octopus-linkedin`（CLI）和 `octopus-linkedin-mcp`（MCP server）。
想从源码开发见 [开发](#开发) 一节。

### 2. 创建 LinkedIn 应用

在 [linkedin.com/developers](https://www.linkedin.com/developers/apps) 创建一个绑定
公司主页的 **Standalone app**，然后添加这两个产品：

- **Share on LinkedIn** → 授予 `w_member_social`（发帖）
- **Sign In with LinkedIn using OpenID Connect** → 授予 `openid profile email`

在应用的 **Auth** 标签页，添加授权回调地址：

```
http://localhost:8000/callback
```

### 3. 配置

```bash
cp .env.example .env
chmod 600 .env
```

编辑 `.env`，填入你的 **Client ID** 和 **Client Secret**（Auth 标签页）。

### 4. 授权（一次性）

```bash
python -m linkedin.auth
```

浏览器会打开，登录并批准即可。token 会缓存到 `token.json`（已 gitignore，权限 `0600`）。
成员 token 有效期约 60 天，过期后重跑此命令即可。

### 5. 运行

```bash
python server.py
```

## 接入 Claude Code

```bash
claude mcp add octopus-linkedin -- octopus-linkedin-mcp
```

然后直接说：*"帮我起草一条关于 X 的 LinkedIn 帖子，我审核后再发布。"*

## CLI

同一套引擎也提供 CLI，便于脚本化和 cron：

```bash
octopus-linkedin authorize
octopus-linkedin post "你好，世界" --visibility PUBLIC
octopus-linkedin draft "一条稍后审核的帖子"
octopus-linkedin approve drft_abc123 --note "通过"
octopus-linkedin schedule drft_abc123 2026-07-02T09:00:00Z
octopus-linkedin run-scheduler --interval 60
octopus-linkedin stats urn:li:share:123
```

## 定时发布

定时被拆成两步，确保不会有内容意外发出：你先用 `schedule_draft` 为一条**已批准**的
草稿设定一个未来的 UTC 时间，再由一个 runner 在到点时真正发送。三种运行方式任选其一：

- `octopus-linkedin run-scheduler` —— 简单的前台循环，或
- 用 `cron` 每隔几分钟跑一次 `octopus-linkedin publish-due`，或
- 按需调用 `publish_due` 这个 MCP 工具。

只有**既已批准、又已到点**的草稿才会被发布。

## 开发

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && pytest
```

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 安全

`.env` 和 `token.json` 存有凭据，已被 gitignore——切勿提交。报告方式和凭据处理见
[SECURITY.md](SECURITY.md)。

## 许可证

[Apache-2.0](LICENSE)。
