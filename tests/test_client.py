"""Tests for client helpers and MCP tool wiring (no network calls)."""

from __future__ import annotations

import asyncio

from linkedin.client import post_url


def test_post_url():
    urn = "urn:li:share:7477760936473423872"
    assert post_url(urn) == f"https://www.linkedin.com/feed/update/{urn}"


def test_all_tools_registered():
    import server

    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    expected = {
        "get_profile",
        "create_post",
        "share_link",
        "share_image",
        "share_images",
        "delete_post",
        "list_comments",
        "reply_comment",
        "get_post_stats",
        "create_draft",
        "list_drafts",
        "get_draft",
        "update_draft",
        "approve_draft",
        "delete_draft",
        "publish_draft",
        "schedule_draft",
        "unschedule_draft",
        "publish_due",
        "llm_info",
        "generate_draft",
        "polish_text",
        "optimize_text",
        "polish_draft",
        "optimize_draft",
        "ab_variants",
        "repurpose_url",
        "triage_comments",
        "get_voice",
        "set_voice",
    }
    assert expected <= names
