**English** | [简体中文](SECURITY.zh-CN.md)

# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security vulnerabilities.

Report privately via GitHub Security Advisories ("Report a vulnerability" on the
repository's Security tab) or email **security@octopusos.ai** (maintainer:
Ran Tao, ran@octopusos.ai). Include a description, reproduction steps, and
impact. We aim to acknowledge within a few business days.

## Handling credentials

Octopus LinkedIn talks to LinkedIn on your behalf using OAuth. Treat these as
secrets and never commit them:

- **`.env`** — holds your `LINKEDIN_CLIENT_SECRET`. Gitignored by default.
- **`token.json`** — holds your access (and refresh) token. Gitignored by
  default, and written with `0600` permissions.

If a Client Secret is ever exposed, rotate it immediately in the LinkedIn
developer console (App → Auth → Generate a new Client Secret). Existing access
tokens keep working until they expire; re-run `python -m linkedin.auth` to
re-authorize.

## Scope notes

- Tokens are stored locally and only sent to `api.linkedin.com` and
  `www.linkedin.com`.
- The drafting workflow is local-only by design: writing and approving drafts
  never makes a network call. Only `publish_draft` and the direct-publish tools
  send data to LinkedIn.
