**English** | [简体中文](ARCHITECTURE.zh-CN.md)

# Architecture

Octopus LinkedIn is a small, governed MCP server that sits between an MCP client
(Claude Desktop, Claude Code, any MCP-compatible agent) and the official
LinkedIn API.

```
  MCP client (Claude)
        │  MCP (stdio)
        ▼
  server.py  ── FastMCP, 19 tools
        │
        ├── linkedin/drafts.py   local JSON store, review workflow (no network)
        │
        └── linkedin/client.py   LinkedIn REST wrapper
                  │
                  └── linkedin/auth.py   OAuth 2.0, token cache + refresh
                          │  HTTPS
                          ▼
                  api.linkedin.com / www.linkedin.com
```

## Design principles

**Governance first.** The draft store is local-only. Creating, editing, and
approving a draft never touches the network. `publish_draft` is the single gate
that sends content out, and it refuses to publish anything whose status is not
`approved`. This keeps a human (or an explicit approval step) in the loop by
default, while still offering direct-publish tools for when you don't want the
gate.

**Official API, compliance path.** We use LinkedIn's documented endpoints with
OAuth and the `w_member_social` scope. No browser automation, no scraping of the
session. The tradeoff is a deliberately bounded surface: you can post to your
own feed and comment on content you control, but the API does not allow
auto-commenting on arbitrary third-party posts.

**Thin, legible tool surface.** Each MCP tool is a small wrapper whose docstring
is the contract an LLM reads. Tool names make network effects obvious
(`create_post` posts; `create_draft` does not).

## Components

| File | Responsibility |
|------|----------------|
| `server.py` | FastMCP server; defines and registers the 19 tools |
| `linkedin/auth.py` | 3-legged OAuth, local `token.json` cache, refresh, re-auth |
| `linkedin/client.py` | REST calls: identity, posting, comments, analytics |
| `linkedin/drafts.py` | Local draft store; the draft→approved→publishing→published workflow, file-locked with atomic writes |
| `linkedin/scheduler.py` | Publishes approved+due drafts; the compare-and-set publish gate |
| `linkedin/llm.py` | Provider-agnostic LLM client (Anthropic / OpenAI / Gemini) over httpx |
| `linkedin/content.py` | Write/polish/optimize/repurpose/A-B/triage; SSRF-guarded URL fetch |
| `linkedin/voice.py` | Local brand-voice profile, rendered into the generation system prompt |

## API endpoints used

| Purpose | Endpoint |
|---------|----------|
| Identity | `GET /v2/userinfo` |
| Create post (text/link/image) | `POST /v2/ugcPosts` |
| Delete post | `DELETE /v2/ugcPosts/{urn}` |
| Image upload | `POST /v2/assets?action=registerUpload` + `PUT {uploadUrl}` |
| List / add comments | `GET`/`POST /v2/socialActions/{urn}/comments` |
| Engagement counts | `GET /v2/socialActions/{urn}` |

We use the classic `/v2/ugcPosts` endpoint rather than the versioned
`/rest/posts` Posts API, because the latter requires a `LinkedIn-Version` header
that expires every ~12 months; `ugcPosts` works with just `w_member_social` and
needs no version pin.

## Token lifecycle

`auth.py` runs a one-time browser flow, captures the OAuth code on a localhost
callback, exchanges it for a token, and writes `token.json` (mode `0600`).
`client.py` reads it through `get_access_token()`, which refreshes automatically
when a refresh token is present and otherwise raises with instructions to
re-run authorization. Member access tokens last ~60 days.

## Roadmap

See the roadmap section in the [README](../README.md#roadmap).
