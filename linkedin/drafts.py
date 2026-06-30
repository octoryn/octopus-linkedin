"""Local draft store with a review/approval workflow.

Drafts live in a single JSON file (drafts.json in the project root by default).
The lifecycle is:

    draft  ->  approved  ->  publishing  ->  published

You write a draft, review and approve it, then publish. `publishing` is a brief
claimed state used as a compare-and-set lock so the same draft can never be
published twice (e.g. a manual publish racing the scheduler loop). Publishing is
the only step that touches LinkedIn; everything else is local.

All mutations take an exclusive file lock and write atomically, so concurrent
processes (an MCP server plus a `run-scheduler` loop) can't lose updates or
leave a half-written file.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl  # POSIX only
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore[assignment]

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "drafts.json"

VALID_MEDIA = {"none", "link", "image"}
VALID_VISIBILITY = {"PUBLIC", "CONNECTIONS"}
STATUS_DRAFT = "draft"
STATUS_APPROVED = "approved"
STATUS_PUBLISHING = "publishing"
STATUS_PUBLISHED = "published"
# States in which a draft is locked from edits/scheduling.
_LOCKED = {STATUS_PUBLISHING, STATUS_PUBLISHED}


class DraftError(RuntimeError):
    """Raised on invalid draft operations."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_when(when: str) -> datetime:
    """Parse an ISO 8601 timestamp into an aware UTC datetime.

    Accepts a single trailing 'Z' and naive timestamps (assumed UTC).
    """
    normalized = when[:-1] + "+00:00" if when.endswith("Z") else when
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as e:
        raise DraftError(
            f"Invalid datetime {when!r}; use ISO 8601 like 2026-07-02T09:00:00Z"
        ) from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _store_path() -> Path:
    return Path(os.getenv("LINKEDIN_DRAFTS_PATH", str(DEFAULT_PATH)))


class DraftStore:
    """A tiny JSON-backed draft store with file locking and atomic writes."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else _store_path()
        self._lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    # -- persistence --------------------------------------------------------

    @contextmanager
    def _lock(self):
        """Exclusive cross-process lock for the duration of a read/modify/write."""
        if fcntl is None:  # pragma: no cover - non-POSIX best effort
            yield
            return
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        raw = self.path.read_text() or "[]"
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise DraftError(
                f"Draft store {self.path} is corrupt ({e}). "
                "Inspect or remove it to recover."
            ) from e

    def _save(self, drafts: list[dict[str, Any]]) -> None:
        """Write atomically: temp file in the same dir, then os.replace."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(drafts, fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _mutate(self, fn: Callable[[list[dict[str, Any]]], Any]) -> Any:
        """Run `fn(drafts)` under lock and persist the (possibly mutated) list."""
        with self._lock():
            drafts = self._load()
            result = fn(drafts)
            self._save(drafts)
            return result

    @staticmethod
    def _find(drafts: list[dict[str, Any]], draft_id: str) -> dict[str, Any]:
        for d in drafts:
            if d["id"] == draft_id:
                return d
        raise DraftError(f"No draft with id {draft_id}")

    # -- CRUD ---------------------------------------------------------------

    def create(
        self,
        text: str,
        visibility: str = "PUBLIC",
        media_type: str = "none",
        link_url: str | None = None,
        image_path: str | None = None,
        title: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        if visibility not in VALID_VISIBILITY:
            raise DraftError(f"visibility must be one of {sorted(VALID_VISIBILITY)}")
        if media_type not in VALID_MEDIA:
            raise DraftError(f"media_type must be one of {sorted(VALID_MEDIA)}")
        if media_type == "link" and not link_url:
            raise DraftError("media_type 'link' requires link_url")
        if media_type == "image" and not image_path:
            raise DraftError("media_type 'image' requires image_path")

        draft = {
            "id": "drft_" + uuid.uuid4().hex[:12],
            "text": text,
            "visibility": visibility,
            "media_type": media_type,
            "link_url": link_url,
            "image_path": image_path,
            "title": title,
            "description": description,
            "status": STATUS_DRAFT,
            "review_note": None,
            "published_urn": None,
            "scheduled_at": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self._mutate(lambda drafts: drafts.append(draft))
        return draft

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock():
            drafts = self._load()
        if status:
            drafts = [d for d in drafts if d["status"] == status]
        return drafts

    def get(self, draft_id: str) -> dict[str, Any]:
        with self._lock():
            return self._find(self._load(), draft_id)

    def update(self, draft_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {
            "text",
            "visibility",
            "media_type",
            "link_url",
            "image_path",
            "title",
            "description",
        }
        bad = set(fields) - allowed
        if bad:
            raise DraftError(f"Cannot update fields: {sorted(bad)}")

        def apply(drafts):
            d = self._find(drafts, draft_id)
            if d["status"] in _LOCKED:
                raise DraftError(f"Cannot edit a {d['status']} draft")
            d.update({k: v for k, v in fields.items() if v is not None})
            # Editing sends an approved draft back to draft for re-review.
            if d["status"] == STATUS_APPROVED:
                d["status"] = STATUS_DRAFT
            d["updated_at"] = _now()
            return d

        return self._mutate(apply)

    def approve(self, draft_id: str, note: str | None = None) -> dict[str, Any]:
        def apply(drafts):
            d = self._find(drafts, draft_id)
            if d["status"] in _LOCKED:
                raise DraftError(f"Cannot approve a {d['status']} draft")
            d["status"] = STATUS_APPROVED
            if note is not None:
                d["review_note"] = note
            d["updated_at"] = _now()
            return d

        return self._mutate(apply)

    def claim_for_publish(self, draft_id: str) -> dict[str, Any]:
        """Atomically transition approved -> publishing and return the claimed
        draft. Raises if it isn't approved, so a concurrent claim (manual
        publish racing the scheduler) can only succeed once.
        """

        def apply(drafts):
            d = self._find(drafts, draft_id)
            if d["status"] != STATUS_APPROVED:
                raise DraftError(
                    f"Draft {draft_id} is '{d['status']}', not 'approved'."
                )
            d["status"] = STATUS_PUBLISHING
            d["updated_at"] = _now()
            return dict(d)

        return self._mutate(apply)

    def mark_published(self, draft_id: str, post_urn: str) -> dict[str, Any]:
        def apply(drafts):
            d = self._find(drafts, draft_id)
            d["status"] = STATUS_PUBLISHED
            d["published_urn"] = post_urn
            d["updated_at"] = _now()
            return d

        return self._mutate(apply)

    def revert_to_approved(self, draft_id: str) -> dict[str, Any]:
        """Return a claimed (publishing) draft to approved after a failed send."""

        def apply(drafts):
            d = self._find(drafts, draft_id)
            if d["status"] == STATUS_PUBLISHING:
                d["status"] = STATUS_APPROVED
                d["updated_at"] = _now()
            return d

        return self._mutate(apply)

    def delete(self, draft_id: str) -> dict[str, Any]:
        def apply(drafts):
            before = len(drafts)
            drafts[:] = [d for d in drafts if d["id"] != draft_id]
            if len(drafts) == before:
                raise DraftError(f"No draft with id {draft_id}")

        self._mutate(apply)
        return {"id": draft_id, "deleted": True}

    # -- scheduling ---------------------------------------------------------

    def schedule(self, draft_id: str, when: str) -> dict[str, Any]:
        """Set a future publish time (ISO 8601). Does not change approval —
        the scheduler only publishes drafts that are also approved.
        """
        dt = parse_when(when)
        if dt <= datetime.now(timezone.utc):
            raise DraftError(f"Scheduled time must be in the future: {when}")

        def apply(drafts):
            d = self._find(drafts, draft_id)
            if d["status"] in _LOCKED:
                raise DraftError(f"Cannot schedule a {d['status']} draft")
            d["scheduled_at"] = dt.isoformat(timespec="seconds")
            d["updated_at"] = _now()
            return d

        return self._mutate(apply)

    def unschedule(self, draft_id: str) -> dict[str, Any]:
        def apply(drafts):
            d = self._find(drafts, draft_id)
            d["scheduled_at"] = None
            d["updated_at"] = _now()
            return d

        return self._mutate(apply)

    def due(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Approved drafts whose scheduled_at has arrived. A malformed
        scheduled_at is skipped (never crashes the scheduler loop).
        """
        moment = now or datetime.now(timezone.utc)
        with self._lock():
            drafts = self._load()
        out = []
        for d in drafts:
            if d["status"] != STATUS_APPROVED or not d.get("scheduled_at"):
                continue
            try:
                when = parse_when(d["scheduled_at"])
            except DraftError:
                continue
            if when <= moment:
                out.append(d)
        return out
