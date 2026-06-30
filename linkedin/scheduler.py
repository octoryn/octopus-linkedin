"""Publish approved drafts when their scheduled time arrives.

The MCP server is on-demand, not a long-running daemon, so scheduling is split:

- `schedule` a draft (stores a future `scheduled_at`).
- `publish_due` publishes every approved + due draft right now. Call it from
  the MCP tool of the same name, from the CLI (`octopus-linkedin publish-due`),
  or on a timer (`octopus-linkedin run-scheduler`, or cron).

Only drafts that are BOTH approved AND past their scheduled time are published,
so an unreviewed or future draft is never sent.
"""

from __future__ import annotations

import time
from typing import Any

from .client import LinkedInClient
from .drafts import DraftError, DraftStore


def publish_one(client: LinkedInClient, store: DraftStore, draft: dict) -> dict:
    """Publish a single draft. Atomically claims it first (approved ->
    publishing) so it can never be sent twice; on failure it's reverted to
    approved for a later retry.
    """
    claimed = store.claim_for_publish(draft["id"])
    try:
        mt = claimed.get("media_type", "none")
        if mt == "link":
            res = client.share_link(
                claimed["text"],
                claimed["link_url"],
                title=claimed.get("title"),
                description=claimed.get("description"),
                visibility=claimed["visibility"],
            )
        elif mt == "image":
            res = client.share_image(
                claimed["text"],
                claimed["image_path"],
                title=claimed.get("title"),
                alt_text=claimed.get("description"),
                visibility=claimed["visibility"],
            )
        else:
            res = client.create_post(claimed["text"], visibility=claimed["visibility"])
    except Exception:
        store.revert_to_approved(claimed["id"])
        raise
    store.mark_published(claimed["id"], res["post_urn"])
    return {**res, "draft_id": claimed["id"]}


def publish_due(
    client: LinkedInClient | None = None, store: DraftStore | None = None
) -> list[dict[str, Any]]:
    """Publish all approved, due drafts. Returns a result per draft."""
    client = client or LinkedInClient()
    store = store or DraftStore()
    results = []
    for draft in store.due():
        try:
            results.append(publish_one(client, store, draft))
        except DraftError:
            # Lost the claim race (another runner grabbed it) — skip quietly.
            continue
        except Exception as e:  # keep going; one bad draft shouldn't block others
            results.append({"draft_id": draft["id"], "error": str(e)})
    return results


def run_loop(interval_seconds: int = 60, store: DraftStore | None = None) -> None:
    """Block forever, publishing due drafts every `interval_seconds`."""
    client = LinkedInClient()
    store = store or DraftStore()
    print(f"Scheduler running; checking every {interval_seconds}s. Ctrl-C to stop.")
    try:
        while True:
            for r in publish_due(client, store):
                if "error" in r:
                    print(f"  ! {r['draft_id']}: {r['error']}")
                else:
                    print(f"  ✓ published {r['draft_id']} -> {r['url']}")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nScheduler stopped.")
