"""Tests for the local draft store and its review workflow."""

from __future__ import annotations

import pytest

from linkedin.drafts import (
    STATUS_APPROVED,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    DraftError,
    DraftStore,
)


@pytest.fixture()
def store(tmp_path):
    return DraftStore(tmp_path / "drafts.json")


def test_create_defaults_to_draft(store):
    d = store.create("hello")
    assert d["status"] == STATUS_DRAFT
    assert d["id"].startswith("drft_")
    assert d["media_type"] == "none"


def test_link_requires_url(store):
    with pytest.raises(DraftError):
        store.create("x", media_type="link")


def test_image_requires_path(store):
    with pytest.raises(DraftError):
        store.create("x", media_type="image")


def test_invalid_visibility_rejected(store):
    with pytest.raises(DraftError):
        store.create("x", visibility="SECRET")


def test_approve_then_publish(store):
    d = store.create("ship it")
    store.approve(d["id"], note="lgtm")
    assert store.get(d["id"])["status"] == STATUS_APPROVED
    assert store.get(d["id"])["review_note"] == "lgtm"
    store.mark_published(d["id"], "urn:li:share:42")
    pub = store.get(d["id"])
    assert pub["status"] == STATUS_PUBLISHED
    assert pub["published_urn"] == "urn:li:share:42"


def test_editing_approved_resets_to_draft(store):
    d = store.create("v1")
    store.approve(d["id"])
    store.update(d["id"], text="v2")
    assert store.get(d["id"])["status"] == STATUS_DRAFT
    assert store.get(d["id"])["text"] == "v2"


def test_cannot_edit_published(store):
    d = store.create("done")
    store.approve(d["id"])
    store.mark_published(d["id"], "urn:li:share:1")
    with pytest.raises(DraftError):
        store.update(d["id"], text="nope")


def test_list_filters_by_status(store):
    a = store.create("a")
    store.create("b")
    store.approve(a["id"])
    assert len(store.list()) == 2
    assert len(store.list(status=STATUS_APPROVED)) == 1
    assert len(store.list(status=STATUS_DRAFT)) == 1


def test_delete(store):
    d = store.create("temp")
    store.delete(d["id"])
    assert store.list() == []
    with pytest.raises(DraftError):
        store.delete(d["id"])


def test_update_rejects_unknown_field(store):
    d = store.create("x")
    with pytest.raises(DraftError):
        store.update(d["id"], status="published")
