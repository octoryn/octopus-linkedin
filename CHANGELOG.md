**English** | [简体中文](CHANGELOG.zh-CN.md)

# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1]

### Changed
- Release workflow now triggers on a version tag, verifies the tag matches
  `pyproject.toml`, and gates publishing on the full lint/format/test suite.
- Contact addresses moved to the `octopusos.ai` domain
  (security@octopusos.ai, conduct@octopusos.ai); maintainer: Ran Tao
  (ran@octopusos.ai).

## [0.2.0]

### Changed
- **Relicensed from AGPL-3.0-or-later to Apache-2.0** to make adoption and
  embedding easier for developers.

## [Unreleased]

### Added — content intelligence
- Pluggable LLM backend (`linkedin.llm`) over plain httpx: Anthropic, OpenAI,
  and Google Gemini, selected via `LLM_PROVIDER` with per-provider model
  defaults and `LLM_MODEL` override.
- Content tools: `generate_draft` (brief → draft), `polish_text`/`polish_draft`,
  `optimize_text`/`optimize_draft`, `ab_variants`, `repurpose_url` (article →
  draft, SSRF-guarded), `triage_comments` (classify + suggest replies), and
  `llm_info`.
- Brand-voice memory (`linkedin.voice`): a local profile (tone, audience,
  examples, banned phrases) that conditions every content operation.
- MCP `prompts` (`draft_post`, `repurpose_article`, `reply_to_comments`) and
  `resources` (`voice://profile`, `drafts://list`).
- CLI subcommands: `generate`, `polish`, `optimize`, `ab`, `repurpose`, `voice`,
  `set-voice`, `llm-info`.
- `repurpose_url` blocks non-public hosts (private/loopback/link-local/reserved)
  and re-checks after redirects; only http(s) is fetched.

### Added
- Initial MCP server (`octopus-linkedin`) over FastMCP, plus a standalone CLI
  (`octopus-linkedin`) and MCP entry point (`octopus-linkedin-mcp`).
- OAuth 2.0 3-legged authorization flow with local token caching and refresh
  (`linkedin.auth`).
- Identity tool: `get_profile`.
- Direct publishing: `create_post` (text), `share_link` (URL preview card),
  `share_image` / `share_images` (single + up to 9 images), `delete_post`.
- Comments: `list_comments`, `reply_comment`.
- Analytics: `get_post_stats` (likes + comments).
- Local draft store with a review/approval workflow (`linkedin.drafts`):
  `create_draft`, `list_drafts`, `get_draft`, `update_draft`, `approve_draft`,
  `delete_draft`, and `publish_draft`.
- Scheduling: `schedule_draft` / `unschedule_draft` / `publish_due`, plus a
  `run-scheduler` loop in the CLI.
- Hardening (from an adversarial review): file-locked, atomic-write draft store
  with JSON-corruption handling; a compare-and-set publish gate (`approved →
  publishing → published`) that makes double-publish impossible across a manual
  publish racing the scheduler; media-path size cap + optional
  `LINKEDIN_MEDIA_DIR` confinement; refusal to send the bearer token to any
  non-LinkedIn upload host; safer token-refresh and expiry handling.
- Unit tests (33) for the draft workflow, scheduling, the publish gate, and the
  hardening fixes; CI via GitHub Actions.

### Notes
- Posting uses the classic `/v2/ugcPosts` endpoint, which works with the
  `w_member_social` scope and needs no API-version header.
- The official API can only comment on content you control (your own posts, or
  an org page you administer) — it cannot auto-comment on arbitrary posts.
- Document/PDF posts and per-reactor reaction breakdowns were prototyped and
  **removed**: documents require the versioned `/rest/posts` + Documents API
  (not `/v2/ugcPosts`), and reading reactions needs the restricted
  `r_member_social_feed` scope. Both are tracked on the roadmap instead of
  shipped as broken tools.
