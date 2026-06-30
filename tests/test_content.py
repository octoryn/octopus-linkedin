"""Tests for content ops (LLM stubbed) and the SSRF/URL guards."""

from __future__ import annotations

import pytest

from linkedin import content
from linkedin.content import ContentError, _assert_public_http_url, _html_to_text


@pytest.fixture()
def stub_llm(monkeypatch):
    """Replace llm.complete with a recorder returning a canned response."""
    calls = {}

    def fake(system, prompt, temperature=None, max_tokens=None):
        calls["system"] = system
        calls["prompt"] = prompt
        return calls.get("response", "STUBBED")

    monkeypatch.setattr(content.llm, "complete", fake)
    return calls


def test_generate_draft_uses_llm(stub_llm):
    stub_llm["response"] = "A great post"
    assert content.generate_draft("launch news") == "A great post"
    assert "launch news" in stub_llm["prompt"]


def test_generate_draft_rejects_empty(stub_llm):
    with pytest.raises(ContentError):
        content.generate_draft("   ")


def test_polish_and_optimize(stub_llm):
    stub_llm["response"] = "edited"
    assert content.polish("rough text") == "edited"
    assert content.optimize("rough text") == "edited"


def test_ab_variants_parses_json(stub_llm):
    stub_llm["response"] = '["v1", "v2", "v3"]'
    out = content.ab_variants("seed", 3)
    assert out == ["v1", "v2", "v3"]


def test_ab_variants_handles_code_fence(stub_llm):
    stub_llm["response"] = '```json\n["a", "b"]\n```'
    assert content.ab_variants("seed", 2) == ["a", "b"]


def test_ab_variants_bad_output_raises(stub_llm):
    stub_llm["response"] = "not json at all"
    with pytest.raises(ContentError):
        content.ab_variants("seed", 2)


def test_triage_maps_back_to_comments(stub_llm):
    stub_llm["response"] = (
        '[{"i":0,"category":"question","priority":"high","suggested_reply":"Sure!"}]'
    )
    comments = [{"author": "urn:li:person:a", "text": "How does it work?"}]
    out = content.triage_comments(comments)
    assert out[0]["category"] == "question"
    assert out[0]["suggested_reply"] == "Sure!"


def test_triage_empty_input_returns_empty(stub_llm):
    assert content.triage_comments([]) == []
    assert content.triage_comments([{"text": "  "}]) == []


def test_triage_unparseable_raises(stub_llm):
    stub_llm["response"] = "the model rambled and never returned JSON"
    with pytest.raises(ContentError):
        content.triage_comments([{"author": "a", "text": "hi"}])


def test_triage_validates_enums(stub_llm):
    stub_llm["response"] = (
        '[{"i":0,"category":"HACKED","priority":"urgent","suggested_reply":"x"}]'
    )
    out = content.triage_comments([{"author": "a", "text": "hi"}])
    assert out[0]["category"] == "other"  # invalid category coerced
    assert out[0]["priority"] == "low"  # invalid priority coerced


def test_triage_caps_comment_count(stub_llm):
    stub_llm["response"] = "[]"
    many = [{"author": "a", "text": f"c{i}"} for i in range(100)]
    # the model gets at most _MAX_TRIAGE items; unparseable -> raises, but the
    # point is it doesn't send all 100. We assert the prompt was capped.
    with pytest.raises(ContentError):
        content.triage_comments(many)
    assert stub_llm["prompt"].count('"i":') <= content._MAX_TRIAGE


def test_rejects_disallowed_port():
    with pytest.raises(ContentError):
        _assert_public_http_url("http://8.8.8.8:22/")
    with pytest.raises(ContentError):
        _assert_public_http_url("http://8.8.8.8:6379/")


# --- SSRF / URL guards (no network) ---------------------------------------


def test_rejects_non_http_scheme():
    with pytest.raises(ContentError):
        _assert_public_http_url("file:///etc/passwd")
    with pytest.raises(ContentError):
        _assert_public_http_url("ftp://example.com/x")


def test_rejects_loopback_and_private():
    with pytest.raises(ContentError):
        _assert_public_http_url("http://127.0.0.1/admin")
    with pytest.raises(ContentError):
        _assert_public_http_url("http://localhost/")
    with pytest.raises(ContentError):
        _assert_public_http_url("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(ContentError):
        _assert_public_http_url("http://10.0.0.5/")


def test_html_to_text_strips_scripts():
    html = "<html><body><script>evil()</script><p>Hello <b>world</b></p></body></html>"
    text = _html_to_text(html)
    assert "Hello" in text and "world" in text
    assert "evil" not in text
