"""Tests for the LLM provider dispatch using httpx.MockTransport (no network)."""

from __future__ import annotations

import httpx
import pytest

from linkedin import llm
from linkedin.llm import LLMError


def _patch_transport(monkeypatch, handler):
    """Make llm's httpx.Client use a mock transport."""
    real_client = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        kwargs.pop("timeout", None)
        return real_client(**kwargs)

    monkeypatch.setattr(llm.httpx, "Client", factory)


def test_provider_validation(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    with pytest.raises(LLMError):
        llm.provider_info()


def test_anthropic_dispatch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "api.anthropic.com" in str(request.url)
        assert request.headers["x-api-key"] == "k"
        return httpx.Response(200, json={"content": [{"type": "text", "text": "hi"}]})

    _patch_transport(monkeypatch, handler)
    assert llm.complete("sys", "user") == "hi"


def test_openai_dispatch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "api.openai.com" in str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _patch_transport(monkeypatch, handler)
    assert llm.complete("sys", "user") == "ok"


def test_gemini_dispatch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "generativelanguage.googleapis.com" in str(request.url)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "yo"}]}}]},
        )

    _patch_transport(monkeypatch, handler)
    assert llm.complete("sys", "user") == "yo"


def test_missing_key_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError):
        llm.complete("sys", "user")


def test_api_error_surfaced(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    _patch_transport(monkeypatch, handler)
    with pytest.raises(LLMError):
        llm.complete("sys", "user")
