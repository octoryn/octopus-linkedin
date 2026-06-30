**English** | [简体中文](README.zh-CN.md)

# Octopus LinkedIn

[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-brightgreen.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/protocol-MCP-8A2BE2.svg)](https://modelcontextprotocol.io)

**Governed LinkedIn marketing over MCP.** Draft, review, publish, comment, and
read engagement on LinkedIn — from Claude Desktop, Claude Code, or any
MCP-compatible agent — using the **official LinkedIn API**.

Most "LinkedIn AI" tooling stops at *writing* the post. The obvious next step is
*publishing* it — and that's where you want governance, not a black box. Octopus
LinkedIn makes the whole loop explicit:

> **draft → review → approve → publish → comment → analyze**

Drafting and approving are **local-only** — they never touch the network.
`publish_draft` is the single gate that sends anything out, and it refuses to
publish a draft that hasn't been explicitly approved.

## Tools

| Tool | Sends to LinkedIn? | What it does |
|------|:---:|--------------|
| `get_profile` | read | Your identity + a connectivity check |
| `create_post` | ✅ | Publish a text post |
| `share_link` | ✅ | Publish a post with a URL preview card |
| `share_image` | ✅ | Publish a post with one local image |
| `share_images` | ✅ | Publish a post with up to 9 images |
| `delete_post` | ✅ | Delete one of your posts |
| `list_comments` | read | List comments on your post |
| `reply_comment` | ✅ | Comment on a post you control |
| `get_post_stats` | read | Likes + comments for a post |
| `create_draft` | ⬜ local | Save a draft (text / link / image) |
| `list_drafts` | ⬜ local | List drafts, optionally by status |
| `get_draft` | ⬜ local | Read one draft |
| `update_draft` | ⬜ local | Edit a draft (resets approval) |
| `approve_draft` | ⬜ local | **The review gate** |
| `delete_draft` | ⬜ local | Delete a draft |
| `schedule_draft` | ⬜ local | Schedule an approved draft for later |
| `unschedule_draft` | ⬜ local | Clear a draft's scheduled time |
| `publish_draft` | ✅ | Publish an **approved** draft now |
| `publish_due` | ✅ | Publish all approved drafts whose time has come |

### Content intelligence (LLM-backed)

Conditioned on your brand voice; everything stays behind the approval gate.

| Tool | What it does |
|------|--------------|
| `llm_info` | Show the active LLM provider/model (config check) |
| `generate_draft` | Write a post from a brief → saved as a draft |
| `polish_text` / `polish_draft` | Tighten clarity and flow |
| `optimize_text` / `optimize_draft` | Rework for hook + structure + CTA |
| `ab_variants` | Generate N distinct A/B variants |
| `repurpose_url` | Turn an article URL into an original draft (SSRF-guarded) |
| `triage_comments` | Classify your post's comments + draft replies |
| `get_voice` / `set_voice` | Read/update your brand-voice profile |

Plus MCP **prompts** (`draft_post`, `repurpose_article`, `reply_to_comments`) and
**resources** (`voice://profile`, `drafts://list`) so MCP clients get task
templates and live context, not just raw tool calls.

> **Scope note:** the official API only lets you comment on content you control
> (your own posts, or an org Page you admin). It cannot auto-comment on arbitrary
> third-party posts — by design. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### LLM configuration

Set one provider and its key (see `.env.example`):

```bash
LLM_PROVIDER=anthropic       # anthropic | openai | gemini
ANTHROPIC_API_KEY=sk-ant-... # or OPENAI_API_KEY / GEMINI_API_KEY
# LLM_MODEL=claude-sonnet-4-6  # optional override
```

## Quick start

### 1. Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### 2. Create a LinkedIn app

At [linkedin.com/developers](https://www.linkedin.com/developers/apps), create a
**Standalone app** tied to a Company Page, then add these products:

- **Share on LinkedIn** → grants `w_member_social` (posting)
- **Sign In with LinkedIn using OpenID Connect** → grants `openid profile email`

In the app's **Auth** tab, add an authorized redirect URL:

```
http://localhost:8000/callback
```

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env` and paste your **Client ID** and **Client Secret** (Auth tab).

### 4. Authorize (one time)

```bash
python -m linkedin.auth
```

This opens your browser; log in and approve. A token is cached to `token.json`
(gitignored, `0600`). Member tokens last ~60 days; re-run this when it expires.

### 5. Run

```bash
python server.py
```

## Connect to Claude Code

```bash
claude mcp add octopus-linkedin -- python /absolute/path/to/octopus-linkedin/server.py
```

Or add it to your MCP client config:

```json
{
  "mcpServers": {
    "octopus-linkedin": {
      "command": "python",
      "args": ["/absolute/path/to/octopus-linkedin/server.py"]
    }
  }
}
```

Then just ask: *"Draft a LinkedIn post about X, let me review it, then publish."*

## Example workflow

1. `create_draft` — "Save this post about our launch."
2. `list_drafts` / `get_draft` — review the wording.
3. `approve_draft` — sign off.
4. `publish_draft` — it goes live (and only now).
5. `get_post_stats` — check likes and comments later.

## CLI

The same engine ships as a CLI for scripting and cron:

```bash
octopus-linkedin authorize
octopus-linkedin post "Hello, world" --visibility PUBLIC
octopus-linkedin draft "A post to review later"
octopus-linkedin drafts --status approved
octopus-linkedin approve drft_abc123 --note "lgtm"
octopus-linkedin schedule drft_abc123 2026-07-02T09:00:00Z
octopus-linkedin run-scheduler --interval 60     # loop: publish due drafts
octopus-linkedin stats urn:li:share:123
```

## Scheduling

Scheduling is split so nothing publishes by surprise: you `schedule_draft` an
**approved** draft for a future UTC time, then a runner actually sends it when
due. Run the runner one of three ways:

- `octopus-linkedin run-scheduler` — a simple foreground loop, or
- `octopus-linkedin publish-due` from `cron` every few minutes, or
- the `publish_due` MCP tool on demand.

Only drafts that are **both approved and past their time** are published.

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

Shipped:

- [x] Scheduled publishing (publish an approved draft at a future time)
- [x] Multi-image posts (up to 9)
- [x] A standalone CLI alongside the MCP server
- [x] Bilingual docs (English | 简体中文)

Content-intelligence layer (shipped):

- [x] LLM backend — Anthropic / OpenAI / Gemini (write / polish / optimize)
- [x] MCP `prompts` + `resources` surface
- [x] Draft-from-URL / article repurposing (SSRF-guarded)
- [x] Brand-voice memory (conditions every generation)
- [x] Comment triage on your own posts (classify → draft reply → approve)
- [x] A/B variant generation

Gated (need LinkedIn approval), tracked but not built:

- [ ] Company Page posting & engagement (Community Management API)
- [ ] Impressions / reach via `memberCreatorPostAnalytics` (partner-gated, 2025)
- [ ] PDF/document posts (need the versioned `/rest/posts` + Documents API)

Contributions to any of these are welcome.

## Security

`.env` and `token.json` hold credentials and are gitignored — never commit them.
See [SECURITY.md](SECURITY.md) for reporting and credential handling.

## License

[AGPL-3.0-or-later](LICENSE).
