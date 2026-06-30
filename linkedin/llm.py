"""Provider-agnostic LLM client for drafting, polishing, and optimizing copy.

Supports three backends — Anthropic, OpenAI, and Google Gemini — over plain
HTTPS (httpx), so there's no heavy SDK dependency to keep in sync.

Configuration (environment):
    LLM_PROVIDER     anthropic | openai | gemini   (default: anthropic)
    LLM_MODEL        override the model id           (per-provider default below)
    LLM_TEMPERATURE  float                           (default: 0.7)
    LLM_MAX_TOKENS   int                             (default: 1024)
    ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY

Only the key for the selected provider is required.
"""

from __future__ import annotations

import os
import time

import httpx

# Per-provider default models. Override any of these with LLM_MODEL.
# Keep these current: retired model ids fail (Gemini 1.5 is shut down; GPT-4o is
# end-of-life). Anthropic claude-sonnet-4-6 / claude-opus-4-8 are current.
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-5.1",
    "gemini": "gemini-2.5-pro",
}

PROVIDERS = set(DEFAULT_MODELS)

# Statuses worth retrying with backoff.
_RETRY_STATUS = {429, 500, 502, 503, 504, 529}
_MAX_RETRIES = 2


class LLMError(RuntimeError):
    """Raised when an LLM call cannot be made or the API returns an error."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status

    @property
    def retryable(self) -> bool:
        return self.status in _RETRY_STATUS


class LLMTruncated(LLMError):
    """Raised when the model hit the token cap and output is incomplete."""


def _cfg() -> dict[str, str]:
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider not in PROVIDERS:
        raise LLMError(
            f"LLM_PROVIDER must be one of {sorted(PROVIDERS)}, got {provider!r}"
        )
    return {
        "provider": provider,
        "model": os.getenv("LLM_MODEL", DEFAULT_MODELS[provider]),
        "temperature": os.getenv("LLM_TEMPERATURE", "0.7"),
        "max_tokens": os.getenv("LLM_MAX_TOKENS", "1024"),
    }


def _require_key(env_name: str) -> str:
    key = os.getenv(env_name)
    if not key:
        raise LLMError(f"{env_name} is not set; required for the selected provider.")
    return key


def provider_info() -> dict[str, str]:
    """The active provider/model — handy for a connectivity check tool."""
    cfg = _cfg()
    return {"provider": cfg["provider"], "model": cfg["model"]}


def complete(
    system: str,
    prompt: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Return the model's text completion for a system+user prompt.

    Retries transient (429/5xx) errors with a short backoff. Raises LLMTruncated
    if the model stopped at the token cap (so callers parsing JSON don't get
    silently-truncated output).
    """
    cfg = _cfg()
    temp = float(cfg["temperature"]) if temperature is None else temperature
    tokens = int(cfg["max_tokens"]) if max_tokens is None else int(max_tokens)
    dispatch = {"anthropic": _anthropic, "openai": _openai, "gemini": _gemini}[
        cfg["provider"]
    ]
    attempt = 0
    while True:
        try:
            text = dispatch(cfg["model"], system, prompt, temp, tokens)
            return text.strip()
        except LLMTruncated:
            raise
        except LLMError as e:
            if e.retryable and attempt < _MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
                attempt += 1
                continue
            raise
        except httpx.HTTPError as e:
            raise LLMError(f"{cfg['provider']} request failed: {e}") from e


# -- providers --------------------------------------------------------------


def _anthropic(model, system, prompt, temperature, max_tokens) -> str:
    key = _require_key("ANTHROPIC_API_KEY")
    with httpx.Client(timeout=120) as c:
        resp = c.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    _raise_for_api(resp, "anthropic")
    data = resp.json()
    if data.get("stop_reason") == "max_tokens":
        raise LLMTruncated("anthropic output truncated; raise LLM_MAX_TOKENS")
    parts = data.get("content", [])
    text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
    if not text:
        raise LLMError(f"anthropic returned no text (stop={data.get('stop_reason')})")
    return text


def _is_openai_reasoning(model: str) -> bool:
    m = model.lower()
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


def _openai(model, system, prompt, temperature, max_tokens) -> str:
    key = _require_key("OPENAI_API_KEY")
    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    # GPT-5.x / reasoning models use max_completion_tokens and reject a custom
    # temperature; older chat models use max_tokens + temperature.
    if _is_openai_reasoning(model):
        body["max_completion_tokens"] = max_tokens
    else:
        body["max_tokens"] = max_tokens
        body["temperature"] = temperature
    with httpx.Client(timeout=120) as c:
        resp = c.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=body,
        )
    _raise_for_api(resp, "openai")
    choices = resp.json().get("choices", [])
    if not choices:
        raise LLMError("openai returned no choices")
    choice = choices[0]
    if choice.get("finish_reason") == "length":
        raise LLMTruncated("openai output truncated; raise LLM_MAX_TOKENS")
    content = (choice.get("message") or {}).get("content")
    if not content:
        raise LLMError(
            f"openai returned empty content (finish={choice.get('finish_reason')})"
        )
    return content


def _gemini(model, system, prompt, temperature, max_tokens) -> str:
    key = _require_key("GEMINI_API_KEY")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    with httpx.Client(timeout=120) as c:
        resp = c.post(
            url,
            headers={"x-goog-api-key": key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            },
        )
    _raise_for_api(resp, "gemini")
    candidates = resp.json().get("candidates", [])
    if not candidates:
        raise LLMError("gemini returned no candidates")
    cand = candidates[0]
    if cand.get("finishReason") == "MAX_TOKENS":
        raise LLMTruncated("gemini output truncated; raise LLM_MAX_TOKENS")
    parts = cand.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    if not text:
        raise LLMError(
            f"gemini returned empty text (finish={cand.get('finishReason')})"
        )
    return text


def _raise_for_api(resp: httpx.Response, provider: str) -> None:
    if resp.status_code >= 400:
        # Keep a short, scrubbed detail — don't pass full upstream bodies through.
        detail = resp.text[:300] if resp.text else ""
        raise LLMError(
            f"{provider} API {resp.status_code}: {detail}", status=resp.status_code
        )
