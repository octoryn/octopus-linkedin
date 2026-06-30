"""Tests for draft scheduling and the publish-due gate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from linkedin.drafts import DraftError, DraftStore, parse_when


@pytest.fixture()
def store(tmp_path):
    return DraftStore(tmp_path / "drafts.json")


def test_parse_when_accepts_z_suffix():
    dt = parse_when("2030-01-01T00:00:00Z")
    assert dt.tzinfo is not None
    assert dt.year == 2030


def test_parse_when_assumes_utc_for_naive():
    dt = parse_when("2030-01-01T00:00:00")
    assert dt.tzinfo == timezone.utc


def test_parse_when_rejects_garbage():
    with pytest.raises(DraftError):
        parse_when("not-a-date")


def test_schedule_requires_future(store):
    d = store.create("x")
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with pytest.raises(DraftError):
        store.schedule(d["id"], past)


def test_schedule_sets_time(store):
    d = store.create("x")
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    out = store.schedule(d["id"], future)
    assert out["scheduled_at"] is not None


def test_due_only_returns_approved_and_past(store):
    soon = datetime.now(timezone.utc) + timedelta(seconds=1)
    # approved + scheduled in the (near) past -> due
    a = store.create("due")
    store.approve(a["id"])
    store.schedule(
        a["id"], (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    )
    # force its scheduled_at into the past by re-saving
    raw = store._load()
    for item in raw:
        if item["id"] == a["id"]:
            item["scheduled_at"] = (
                datetime.now(timezone.utc) - timedelta(minutes=1)
            ).isoformat()
    store._save(raw)

    # approved but future -> not due
    b = store.create("future")
    store.approve(b["id"])
    store.schedule(
        b["id"], (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    )

    # scheduled+past but NOT approved -> not due
    c = store.create("unapproved")
    store.schedule(
        c["id"], (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    )
    raw = store._load()
    for item in raw:
        if item["id"] == c["id"]:
            item["scheduled_at"] = (
                datetime.now(timezone.utc) - timedelta(minutes=1)
            ).isoformat()
    store._save(raw)

    due_ids = {d["id"] for d in store.due(now=soon)}
    assert a["id"] in due_ids
    assert b["id"] not in due_ids
    assert c["id"] not in due_ids


def test_cannot_schedule_published(store):
    d = store.create("x")
    store.approve(d["id"])
    store.mark_published(d["id"], "urn:li:share:1")
    with pytest.raises(DraftError):
        store.schedule(
            d["id"], (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        )


def test_unschedule_clears(store):
    d = store.create("x")
    store.schedule(
        d["id"], (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    )
    out = store.unschedule(d["id"])
    assert out["scheduled_at"] is None
