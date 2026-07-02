[English](CHANGELOG.md) | **简体中文**

# 更新日志

本项目的所有重要变更都记录在此。格式参考
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，并遵循
[语义化版本](https://semver.org/lang/zh-CN/)。

## [0.2.0]

### 变更
- **许可证从 AGPL-3.0-or-later 改为 Apache-2.0**，降低开发者采用与集成的门槛。

## [未发布]

### 新增 —— 内容智能
- 可插拔的大模型后端（`linkedin.llm`），基于 httpx：支持 Anthropic、OpenAI、
  Google Gemini，通过 `LLM_PROVIDER` 选择，各家有默认模型，可用 `LLM_MODEL` 覆盖。
- 内容工具：`generate_draft`（简述 → 草稿）、`polish_text`/`polish_draft`、
  `optimize_text`/`optimize_draft`、`ab_variants`、`repurpose_url`（文章 → 草稿，
  已做 SSRF 防护）、`triage_comments`（分类 + 拟回复）、`llm_info`。
- 品牌语气记忆（`linkedin.voice`）：本地档案（语气、受众、示例、禁用词），
  条件化每一次内容生成。
- MCP `prompts`（`draft_post`、`repurpose_article`、`reply_to_comments`）与
  `resources`（`voice://profile`、`drafts://list`）。
- CLI 子命令：`generate`、`polish`、`optimize`、`ab`、`repurpose`、`voice`、
  `set-voice`、`llm-info`。
- `repurpose_url` 拦截非公网主机（私有/回环/链路本地/保留地址），并在跳转后重新校验；
  只抓取 http(s)，DNS 解析结果绑定到连接以防 DNS 重绑定。

### 新增
- 初始 MCP server（`octopus-linkedin`），基于 FastMCP；外加独立 CLI
  （`octopus-linkedin`）和 MCP 入口（`octopus-linkedin-mcp`）。
- OAuth 2.0 三脚授权流程，本地缓存与刷新令牌（`linkedin.auth`）。
- 身份工具：`get_profile`。
- 直接发布：`create_post`（文本）、`share_link`（链接预览卡）、
  `share_image` / `share_images`（单图 + 最多 9 图）、`delete_post`。
- 评论：`list_comments`、`reply_comment`。
- 分析：`get_post_stats`（点赞 + 评论数）。
- 本地草稿库 + 审核流程（`linkedin.drafts`）：create/list/get/update/approve/
  delete/publish 一整套草稿工具。
- 定时：`schedule_draft` / `unschedule_draft` / `publish_due`，以及 CLI 的
  `run-scheduler` 循环。
- 加固（来自对抗审核）：带文件锁的原子写草稿库 + JSON 损坏处理；compare-and-set
  发布关口（approved → publishing → published），让手动发布与定时器并发也不会重复发帖；
  媒体路径体积上限 + 可选 `LINKEDIN_MEDIA_DIR` 限定目录；拒绝把令牌发往非 LinkedIn
  上传主机；更稳的令牌刷新与过期处理。
- 单元测试（60 个）覆盖草稿流程、定时、发布关口、内容安全与加固；CI 走 GitHub Actions。

### 说明
- 发帖使用经典的 `/v2/ugcPosts` 端点，配 `w_member_social` 权限即可，无需 API 版本头。
- 官方 API 只能评论你掌控的内容（你自己的帖子，或你管理的公司主页）——无法自动评论
  任意第三方帖子。
- 文档/PDF 发帖与按反应类型的细分曾做过原型但**已移除**：文档需要带版本号的
  `/rest/posts` + Documents API（`/v2/ugcPosts` 做不到），读取反应需要受限的
  `r_member_social_feed` 权限。二者都列入路线图，而非作为坏掉的工具发布。
