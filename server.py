"""Octopus LinkedIn — MCP server.

A governed LinkedIn marketing tool over MCP: draft, review/approve, publish,
comment, and read engagement — all via the official LinkedIn API.

The drafting workflow keeps a human in the loop: writing and approving a draft
is local-only, and `publish_draft` refuses to send anything that hasn't been
explicitly approved. Direct-publish tools (create_post, share_link, share_image)
exist too, for when you don't need the gate.

Run:        python server.py
Authorize:  python -m linkedin.auth   (one time)
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from linkedin import content, llm, scheduler
from linkedin.client import LinkedInClient, LinkedInError
from linkedin.content import ContentError
from linkedin.drafts import DraftError, DraftStore
from linkedin.llm import LLMError
from linkedin.voice import VoiceProfile

mcp = FastMCP("octopus-linkedin")
_client: LinkedInClient | None = None
_drafts = DraftStore()
_voice = VoiceProfile()


def client() -> LinkedInClient:
    global _client
    if _client is None:
        _client = LinkedInClient()
    return _client


def _safe(fn):
    """Wrap a tool body so any error returns as data, not an MCP crash."""
    try:
        return fn()
    except (LinkedInError, DraftError, ContentError, LLMError) as e:
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001 - surface unexpected errors as data
        return {"error": f"{type(e).__name__}: {e}"}


# === identity =============================================================


@mcp.tool()
def get_profile() -> dict:
    """Get the authenticated LinkedIn member's identity (name, URN, email).

    Doubles as a connectivity check that your token and scopes work.
    """

    def go():
        p = client().get_profile()
        return {
            "name": p.get("name"),
            "email": p.get("email"),
            "urn": f"urn:li:person:{p.get('sub')}",
            "locale": p.get("locale"),
        }

    return _safe(go)


# === direct publishing ====================================================


@mcp.tool()
def create_post(text: str, visibility: str = "PUBLIC") -> dict:
    """Publish a text post to your feed. visibility: PUBLIC | CONNECTIONS.

    Returns the post URN and its feed URL.
    """
    return _safe(lambda: client().create_post(text, visibility=visibility))


@mcp.tool()
def share_link(
    text: str,
    url: str,
    title: str = "",
    description: str = "",
    visibility: str = "PUBLIC",
) -> dict:
    """Publish a post that shares a URL with an auto-generated preview card.

    Args:
        text: Your commentary above the link.
        url: The link to share.
        title / description: Optional overrides for the preview card.
    """
    return _safe(
        lambda: client().share_link(
            text,
            url,
            title=title or None,
            description=description or None,
            visibility=visibility,
        )
    )


@mcp.tool()
def share_image(
    text: str,
    image_path: str,
    title: str = "",
    alt_text: str = "",
    visibility: str = "PUBLIC",
) -> dict:
    """Publish a post with a local image attached.

    Args:
        text: Post body.
        image_path: Absolute path to a local image file.
        title: Optional image title.
        alt_text: Optional accessibility description.
    """
    return _safe(
        lambda: client().share_image(
            text,
            image_path,
            title=title or None,
            alt_text=alt_text or None,
            visibility=visibility,
        )
    )


@mcp.tool()
def share_images(
    text: str,
    image_paths: list[str],
    visibility: str = "PUBLIC",
) -> dict:
    """Publish a post with multiple local images (up to 9).

    Args:
        text: Post body.
        image_paths: Absolute paths to local image files.
    """
    return _safe(
        lambda: client().share_images(text, image_paths, visibility=visibility)
    )


@mcp.tool()
def delete_post(post_urn: str) -> dict:
    """Delete one of your posts by its URN."""
    return _safe(lambda: client().delete_post(post_urn))


# === comments =============================================================


@mcp.tool()
def list_comments(post_urn: str, count: int = 20) -> dict:
    """List comments on one of your posts."""
    return _safe(lambda: client().list_comments(post_urn, count=count))


@mcp.tool()
def reply_comment(post_urn: str, text: str) -> dict:
    """Add a comment to a post you control (e.g. reply under your own post).

    Note: the official API only allows commenting on content you have access to
    (your own posts, or an org page you administer) — not arbitrary posts.
    """
    return _safe(lambda: client().reply_comment(post_urn, text))


# === analytics ============================================================


@mcp.tool()
def get_post_stats(post_urn: str) -> dict:
    """Return engagement counts (likes, comments) for a post.

    Reading engagement may require extra permissions depending on your app;
    a LinkedIn 403 is surfaced as an error if so.
    """
    return _safe(lambda: client().get_post_stats(post_urn))


# === drafts & review workflow =============================================


@mcp.tool()
def create_draft(
    text: str,
    visibility: str = "PUBLIC",
    media_type: str = "none",
    link_url: str = "",
    image_path: str = "",
    title: str = "",
    description: str = "",
) -> dict:
    """Save a post as a local draft (nothing is sent to LinkedIn).

    media_type: "none" | "link" | "image". For "link" pass link_url; for
    "image" pass image_path. Returns the draft including its id.
    """
    return _safe(
        lambda: _drafts.create(
            text,
            visibility=visibility,
            media_type=media_type,
            link_url=link_url or None,
            image_path=image_path or None,
            title=title or None,
            description=description or None,
        )
    )


@mcp.tool()
def list_drafts(status: str = "") -> dict:
    """List drafts, optionally filtered by status (draft | approved | published)."""
    return _safe(lambda: {"drafts": _drafts.list(status=status or None)})


@mcp.tool()
def get_draft(draft_id: str) -> dict:
    """Fetch a single draft by id."""
    return _safe(lambda: _drafts.get(draft_id))


@mcp.tool()
def update_draft(
    draft_id: str,
    text: str = "",
    visibility: str = "",
    link_url: str = "",
    image_path: str = "",
    title: str = "",
    description: str = "",
) -> dict:
    """Edit a draft's fields. Editing an approved draft resets it to 'draft'
    so it must be re-approved before publishing. Only non-empty args are applied.
    """
    fields = {
        k: v
        for k, v in {
            "text": text,
            "visibility": visibility,
            "link_url": link_url,
            "image_path": image_path,
            "title": title,
            "description": description,
        }.items()
        if v
    }
    return _safe(lambda: _drafts.update(draft_id, **fields))


@mcp.tool()
def approve_draft(draft_id: str, note: str = "") -> dict:
    """Approve a draft, marking it ready to publish. This is the review gate."""
    return _safe(lambda: _drafts.approve(draft_id, note=note or None))


@mcp.tool()
def delete_draft(draft_id: str) -> dict:
    """Delete a local draft."""
    return _safe(lambda: _drafts.delete(draft_id))


@mcp.tool()
def publish_draft(draft_id: str) -> dict:
    """Publish an APPROVED draft to LinkedIn.

    Refuses to publish unless the draft's status is 'approved' — call
    approve_draft first. On success the draft is marked published and stamped
    with the resulting post URN.
    """

    # publish_one atomically claims the draft (approved -> publishing), so the
    # gate is enforced even against a concurrent scheduler or second call.
    return _safe(
        lambda: scheduler.publish_one(client(), _drafts, _drafts.get(draft_id))
    )


@mcp.tool()
def schedule_draft(draft_id: str, when: str) -> dict:
    """Schedule an approved draft to publish at a future time (ISO 8601, UTC).

    Example `when`: "2026-07-02T09:00:00Z". Scheduling does not approve the
    draft; only approved drafts are published when due. Run the scheduler
    (`octopus-linkedin run-scheduler`) or call publish_due to actually send.
    """
    return _safe(lambda: _drafts.schedule(draft_id, when))


@mcp.tool()
def unschedule_draft(draft_id: str) -> dict:
    """Remove a draft's scheduled publish time."""
    return _safe(lambda: _drafts.unschedule(draft_id))


@mcp.tool()
def publish_due() -> dict:
    """Publish every approved draft whose scheduled time has arrived, now."""
    return _safe(lambda: {"published": scheduler.publish_due(client(), _drafts)})


# === content intelligence (LLM-backed) ====================================


@mcp.tool()
def llm_info() -> dict:
    """Show the active LLM provider/model — a config/connectivity check."""
    return _safe(llm.provider_info)


@mcp.tool()
def generate_draft(brief: str, visibility: str = "PUBLIC") -> dict:
    """Write a LinkedIn post from a short brief and save it as a draft.

    Uses your configured LLM, conditioned on your brand voice. The result is a
    local draft (status 'draft') — review and approve before publishing.
    """

    def go():
        text = content.generate_draft(brief, _voice)
        return _drafts.create(text, visibility=visibility)

    return _safe(go)


@mcp.tool()
def polish_text(text: str) -> dict:
    """Polish copy for clarity and flow (returns text; publishes nothing)."""
    return _safe(lambda: {"text": content.polish(text, _voice)})


@mcp.tool()
def optimize_text(text: str) -> dict:
    """Rework copy for engagement: hook, structure, CTA (returns text)."""
    return _safe(lambda: {"text": content.optimize(text, _voice)})


@mcp.tool()
def polish_draft(draft_id: str) -> dict:
    """Polish a draft's text in place (resets approval; never publishes)."""

    def go():
        d = _drafts.get(draft_id)
        return _drafts.update(draft_id, text=content.polish(d["text"], _voice))

    return _safe(go)


@mcp.tool()
def optimize_draft(draft_id: str) -> dict:
    """Optimize a draft's text for engagement in place (resets approval)."""

    def go():
        d = _drafts.get(draft_id)
        return _drafts.update(draft_id, text=content.optimize(d["text"], _voice))

    return _safe(go)


@mcp.tool()
def ab_variants(text: str, n: int = 3) -> dict:
    """Generate n distinct A/B variants of a post (returns a list of texts)."""
    return _safe(lambda: {"variants": content.ab_variants(text, n, _voice)})


@mcp.tool()
def repurpose_url(url: str, angle: str = "", visibility: str = "PUBLIC") -> dict:
    """Turn an article/page URL into an original post, saved as a draft.

    Only public http(s) URLs are fetched (private/loopback hosts are refused).
    """

    def go():
        text = content.repurpose_url(url, angle=angle, voice=_voice)
        return _drafts.create(text, visibility=visibility)

    return _safe(go)


@mcp.tool()
def triage_comments(post_urn: str, count: int = 30) -> dict:
    """Classify comments on your own post and draft suggested replies.

    Returns each comment with a category, priority, and a suggested_reply.
    Nothing is sent — use reply_comment after you review a suggestion.
    """

    def go():
        raw = client().list_comments(post_urn, count=count)
        comments = [
            {
                "author": el.get("actor"),
                "text": (el.get("message") or {}).get("text", ""),
            }
            for el in raw.get("elements", [])
        ]
        return {"triaged": content.triage_comments(comments, _voice)}

    return _safe(go)


@mcp.tool()
def get_voice() -> dict:
    """Get your brand-voice profile (tone, audience, examples, banned phrases)."""
    return _safe(_voice.get)


@mcp.tool()
def set_voice(
    tone: str = "",
    audience: str = "",
    examples: list[str] | None = None,
    banned_phrases: list[str] | None = None,
) -> dict:
    """Update your brand-voice profile. Only non-empty fields are changed.

    This conditions every generate/polish/optimize/repurpose operation.
    """
    return _safe(
        lambda: _voice.set(
            tone=tone or None,
            audience=audience or None,
            examples=examples,
            banned_phrases=banned_phrases,
        )
    )


# === MCP prompts (reusable templates the client can invoke) ===============


@mcp.prompt()
def draft_post(topic: str, goal: str = "engagement") -> str:
    """A prompt for drafting a LinkedIn post about a topic with a stated goal."""
    return (
        f"Draft a LinkedIn post about: {topic}\n"
        f"Goal: {goal}\n"
        "Open with a strong first line, keep it authentic and specific, use short "
        "scannable lines, and end with a question or call to action. Plain text. "
        "Then call create_draft to save it for review."
    )


@mcp.prompt()
def repurpose_article(url: str) -> str:
    """A prompt for repurposing an article URL into an original post."""
    return (
        f"Use the repurpose_url tool on {url} to turn it into an original LinkedIn "
        "post written from my perspective with a clear takeaway. Show me the draft "
        "before approving."
    )


@mcp.prompt()
def reply_to_comments(post_urn: str) -> str:
    """A prompt for triaging and replying to comments on your post."""
    return (
        f"Run triage_comments on {post_urn}. Summarize the questions and leads "
        "worth answering, propose replies for the high-priority ones, and wait for "
        "my approval before calling reply_comment."
    )


# === MCP resources (read-only context the client can pull in) =============


@mcp.resource("voice://profile")
def voice_resource() -> str:
    """The current brand-voice profile as JSON."""
    import json

    return json.dumps(_voice.get(), indent=2, ensure_ascii=False)


@mcp.resource("drafts://list")
def drafts_resource() -> str:
    """All local drafts as JSON."""
    import json

    return json.dumps(_drafts.list(), indent=2, ensure_ascii=False)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
