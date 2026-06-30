"""Tests for the brand-voice profile store."""

from __future__ import annotations

from linkedin.voice import VoiceProfile


def test_empty_profile_defaults(tmp_path):
    v = VoiceProfile(tmp_path / "voice.json")
    p = v.get()
    assert p == {"tone": "", "audience": "", "examples": [], "banned_phrases": []}
    assert v.prompt_fragment() == ""


def test_set_and_fragment(tmp_path):
    v = VoiceProfile(tmp_path / "voice.json")
    v.set(tone="dry and direct", audience="founders", banned_phrases=["synergy"])
    frag = v.prompt_fragment()
    assert "dry and direct" in frag
    assert "founders" in frag
    assert "synergy" in frag


def test_partial_update_preserves(tmp_path):
    v = VoiceProfile(tmp_path / "voice.json")
    v.set(tone="warm")
    v.set(audience="PMs")  # should not wipe tone
    p = v.get()
    assert p["tone"] == "warm"
    assert p["audience"] == "PMs"


def test_add_example_and_truncation(tmp_path):
    v = VoiceProfile(tmp_path / "voice.json")
    for i in range(5):
        v.add_example(f"example {i}")
    assert len(v.get()["examples"]) == 5
    # only first 3 examples make it into the prompt fragment
    frag = v.prompt_fragment()
    assert "example 0" in frag
    assert "example 4" not in frag


def test_corrupt_voice_file_is_tolerated(tmp_path):
    path = tmp_path / "voice.json"
    path.write_text("{ not json")
    v = VoiceProfile(path)
    assert v.get()["tone"] == ""


def test_clear(tmp_path):
    v = VoiceProfile(tmp_path / "voice.json")
    v.set(tone="x", audience="y")
    v.clear()
    assert v.prompt_fragment() == ""
