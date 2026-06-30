"""Brand-voice memory.

A tiny local store of how *you* write, so every generated/polished draft sounds
like you instead of generic LinkedIn filler. It holds a short tone description,
your audience, a few example posts, and banned phrases, and renders them into a
system-prompt fragment that conditions all content operations.

Local-only and dependency-free, like the draft store. Nothing is sent anywhere
except as part of the LLM prompt you explicitly trigger.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "voice.json"

_FIELDS = ("tone", "audience", "examples", "banned_phrases")
# Caps so the profile (and the prompt it builds) stay bounded.
_MAX_EXAMPLES = 20
_MAX_FIELD_CHARS = 4000


def _store_path() -> Path:
    return Path(os.getenv("LINKEDIN_VOICE_PATH", str(DEFAULT_PATH)))


class VoiceProfile:
    """Read/update a single local brand-voice profile."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else _store_path()

    def get(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"tone": "", "audience": "", "examples": [], "banned_phrases": []}
        try:
            data = json.loads(self.path.read_text() or "{}")
        except json.JSONDecodeError:
            return {"tone": "", "audience": "", "examples": [], "banned_phrases": []}
        # normalize
        return {
            "tone": data.get("tone", ""),
            "audience": data.get("audience", ""),
            "examples": list(data.get("examples", [])),
            "banned_phrases": list(data.get("banned_phrases", [])),
        }

    def set(
        self,
        tone: str | None = None,
        audience: str | None = None,
        examples: list[str] | None = None,
        banned_phrases: list[str] | None = None,
    ) -> dict[str, Any]:
        profile = self.get()
        if tone is not None:
            profile["tone"] = tone[:_MAX_FIELD_CHARS]
        if audience is not None:
            profile["audience"] = audience[:_MAX_FIELD_CHARS]
        if examples is not None:
            profile["examples"] = [
                str(e)[:_MAX_FIELD_CHARS] for e in examples[:_MAX_EXAMPLES]
            ]
        if banned_phrases is not None:
            profile["banned_phrases"] = [str(b)[:200] for b in banned_phrases[:100]]
        self._write_atomic(profile)
        return profile

    def _write_atomic(self, profile: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(profile, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def add_example(self, text: str) -> dict[str, Any]:
        profile = self.get()
        profile["examples"].append(text)
        return self.set(examples=profile["examples"])

    def clear(self) -> dict[str, Any]:
        return self.set(tone="", audience="", examples=[], banned_phrases=[])

    def prompt_fragment(self) -> str:
        """Render the profile into a system-prompt fragment (empty if unset)."""
        p = self.get()
        lines: list[str] = []
        if p["tone"]:
            lines.append(f"Voice & tone: {p['tone']}")
        if p["audience"]:
            lines.append(f"Audience: {p['audience']}")
        if p["banned_phrases"]:
            joined = ", ".join(p["banned_phrases"])
            lines.append(f"Never use these words/phrases: {joined}")
        if p["examples"]:
            sample = "\n---\n".join(p["examples"][:3])
            lines.append(
                f"Match the style of these example posts (do not copy them):\n{sample}"
            )
        if not lines:
            return ""
        return "Write in the user's established brand voice.\n" + "\n".join(lines)
