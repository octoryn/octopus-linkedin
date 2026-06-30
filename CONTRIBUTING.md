**English** | [简体中文](CONTRIBUTING.zh-CN.md)

# Contributing to Octopus LinkedIn

Thanks for your interest in improving Octopus LinkedIn. Contributions of all
kinds are welcome — bug reports, feature ideas, docs, and code.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Authorize once against your own LinkedIn developer app (see the README) to run
the live tools. Unit tests do **not** require credentials.

## Running checks

```bash
ruff check .          # lint
ruff format --check . # formatting
pytest                # tests
```

Please make sure all three pass before opening a pull request. CI runs the same
checks.

## Guidelines

- Keep the public tool surface small and well-documented — each MCP tool's
  docstring is what an LLM reads to decide how to call it. Be precise.
- Anything that sends data to LinkedIn must be obvious from the tool name.
  Local-only operations (drafts) must never make network calls.
- Add or update tests for behavior changes. The draft workflow has full unit
  coverage; keep it that way.
- Match the existing style; `ruff format` is the source of truth.

## Reporting bugs

Open an issue with reproduction steps, expected vs. actual behavior, and your
environment (OS, Python version). For security issues, see [SECURITY.md](SECURITY.md)
— do **not** open a public issue.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By
participating, you agree to uphold it.
