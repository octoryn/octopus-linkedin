"""Tests for scheduler.publish_due using a stub client (no network)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from linkedin import scheduler
from linkedin.drafts import DraftStore


class StubClient:
    """Records calls; returns a fake post URN."""

    def __init__(self):
        self.posted = []

    def create_post(self, text, visibility="PUBLIC"):
        self.posted.append(("text", text))
        return {"post_urn": "urn:li:share:stub", "url": "u", "status": "PUBLISHED"}

    def share_link(self, *a, **k):
        self.posted.append(("link", a))
        return {"post_urn": "urn:li:share:stub", "url": "u", "status": "PUBLISHED"}

    def share_image(self, *a, **k):
        self.posted.append(("image", a))
        return {"post_urn": "urn:li:share:stub", "url": "u", "status": "PUBLISHED"}


@pytest.fixture()
def store(tmp_path):
    return DraftStore(tmp_path / "drafts.json")


def _past(store, draft_id):
    raw = store._load()
    for item in raw:
        if item["id"] == draft_id:
            item["scheduled_at"] = (
                datetime.now(timezone.utc) - timedelta(minutes=1)
            ).isoformat()
    store._save(raw)


def test_publish_due_only_sends_approved(store):
    approved = store.create("ready")
    store.approve(approved["id"])
    store.schedule(
        approved["id"], (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    )
    _past(store, approved["id"])

    unapproved = store.create("not ready")
    store.schedule(
        unapproved["id"], (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    )
    _past(store, unapproved["id"])

    client = StubClient()
    results = scheduler.publish_due(client, store)

    assert len(results) == 1
    assert len(client.posted) == 1
    assert store.get(approved["id"])["status"] == "published"
    assert store.get(approved["id"])["published_urn"] == "urn:li:share:stub"
    assert store.get(unapproved["id"])["status"] == "draft"


def test_publish_due_isolates_failures(store, monkeypatch):
    good = store.create("good")
    store.approve(good["id"])
    store.schedule(
        good["id"], (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    )
    _past(store, good["id"])

    class Boom(StubClient):
        def create_post(self, *a, **k):
            raise RuntimeError("api down")

    results = scheduler.publish_due(Boom(), store)
    assert len(results) == 1
    assert "error" in results[0]
    # failed publish leaves the draft approved for a retry
    assert store.get(good["id"])["status"] == "approved"
