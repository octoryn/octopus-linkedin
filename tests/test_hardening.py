"""Tests for the hardening fixes from adversarial review:
corruption handling, the compare-and-set publish gate, and media-path guards.
"""

from __future__ import annotations

import pytest

from linkedin import scheduler
from linkedin.client import LinkedInError, _safe_media_path
from linkedin.drafts import (
    STATUS_APPROVED,
    STATUS_PUBLISHED,
    STATUS_PUBLISHING,
    DraftError,
    DraftStore,
)


@pytest.fixture()
def store(tmp_path):
    return DraftStore(tmp_path / "drafts.json")


# --- corruption -----------------------------------------------------------


def test_corrupt_store_raises_drafterror_not_crash(store):
    store.path.write_text("{ this is not json ]")
    with pytest.raises(DraftError):
        store.list()


def test_atomic_write_leaves_no_tmp_files(store):
    store.create("hello")
    leftovers = list(store.path.parent.glob("*.tmp"))
    assert leftovers == []


# --- compare-and-set publish gate -----------------------------------------


class StubClient:
    def __init__(self):
        self.calls = 0

    def create_post(self, text, visibility="PUBLIC"):
        self.calls += 1
        return {"post_urn": "urn:li:share:x", "url": "u", "status": "PUBLISHED"}


def test_claim_is_single_use(store):
    d = store.create("x")
    store.approve(d["id"])
    claimed = store.claim_for_publish(d["id"])
    assert claimed["status"] == STATUS_PUBLISHING
    # second claim must fail — the draft is no longer 'approved'
    with pytest.raises(DraftError):
        store.claim_for_publish(d["id"])


def test_publish_one_twice_posts_once(store):
    d = store.create("x")
    store.approve(d["id"])
    client = StubClient()
    scheduler.publish_one(client, store, store.get(d["id"]))
    assert store.get(d["id"])["status"] == STATUS_PUBLISHED
    # a second publish of the same (now published) draft must not post again
    with pytest.raises(DraftError):
        scheduler.publish_one(client, store, store.get(d["id"]))
    assert client.calls == 1


def test_unapproved_cannot_be_claimed(store):
    d = store.create("x")  # status draft
    with pytest.raises(DraftError):
        store.claim_for_publish(d["id"])


def test_failed_send_reverts_to_approved(store):
    d = store.create("x")
    store.approve(d["id"])

    class Boom(StubClient):
        def create_post(self, *a, **k):
            raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        scheduler.publish_one(Boom(), store, store.get(d["id"]))
    assert store.get(d["id"])["status"] == STATUS_APPROVED


# --- media path guard -----------------------------------------------------


def test_missing_media_path_rejected():
    with pytest.raises(LinkedInError):
        _safe_media_path("/no/such/file.png")


def test_media_dir_confinement(tmp_path, monkeypatch):
    allowed = tmp_path / "media"
    allowed.mkdir()
    inside = allowed / "ok.png"
    inside.write_bytes(b"x")
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"x")
    monkeypatch.setenv("LINKEDIN_MEDIA_DIR", str(allowed))
    assert _safe_media_path(str(inside)) == inside.resolve()
    with pytest.raises(LinkedInError):
        _safe_media_path(str(outside))


def test_oversize_media_rejected(tmp_path, monkeypatch):
    import linkedin.client as clientmod

    monkeypatch.setattr(clientmod, "MAX_IMAGE_BYTES", 4)
    big = tmp_path / "big.png"
    big.write_bytes(b"12345")
    with pytest.raises(LinkedInError):
        _safe_media_path(str(big))


def test_due_skips_unparseable_scheduled_at(store):
    d = store.create("x")
    store.approve(d["id"])
    raw = store._load()
    for item in raw:
        if item["id"] == d["id"]:
            item["scheduled_at"] = "garbage-not-a-date"
    store._save(raw)
    # must not raise — bad entries are skipped
    assert store.due() == []


def test_approved_constant_unchanged():
    assert STATUS_APPROVED == "approved"
