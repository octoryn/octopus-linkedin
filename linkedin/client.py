"""Thin wrapper over the LinkedIn REST API.

Endpoints used (all work with the w_member_social + openid scopes):
  - GET  /v2/userinfo                          OpenID Connect identity
  - POST /v2/ugcPosts                           create a share (text/link/image)
  - DELETE /v2/ugcPosts/{urn}                   delete a share
  - POST /v2/assets?action=registerUpload       register an image upload
  - PUT  {uploadUrl}                            upload the image bytes
  - GET  /v2/socialActions/{urn}                engagement summary (analytics)
  - GET  /v2/socialActions/{urn}/comments       read comments
  - POST /v2/socialActions/{urn}/comments       comment / reply
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

import httpx

from .auth import get_access_token

API_BASE = "https://api.linkedin.com"

# Max bytes for an uploaded image. LinkedIn's own limit is ~36MB; cap lower to
# avoid reading huge/unexpected files fully into memory.
MAX_IMAGE_BYTES = 20 * 1024 * 1024


class LinkedInError(RuntimeError):
    """Raised when the LinkedIn API returns an error response."""


def _safe_media_path(image_path: str) -> Path:
    """Resolve a user-supplied media path, with guards.

    - Must exist and be a regular file.
    - Must be within LINKEDIN_MEDIA_DIR when that env var is set (so an MCP
      client can't be steered into uploading arbitrary local files).
    - Must be under the size cap.
    """
    path = Path(image_path).expanduser().resolve()
    if not path.is_file():
        raise LinkedInError(f"Media file not found: {path}")
    base = os.getenv("LINKEDIN_MEDIA_DIR")
    if base:
        base_resolved = Path(base).expanduser().resolve()
        if not path.is_relative_to(base_resolved):
            raise LinkedInError(
                f"Media path {path} is outside LINKEDIN_MEDIA_DIR ({base_resolved})"
            )
    size = path.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise LinkedInError(
            f"Media file too large ({size} bytes > {MAX_IMAGE_BYTES} limit)"
        )
    return path


def post_url(post_urn: str) -> str:
    """Build the human-facing feed URL for a share/ugcPost URN."""
    return f"https://www.linkedin.com/feed/update/{post_urn}"


class LinkedInClient:
    def __init__(self) -> None:
        self._cached_urn: str | None = None

    # -- internal -----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {get_access_token()}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    def _check(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            detail: object = resp.text
            try:
                detail = resp.json()
            except Exception:
                pass
            raise LinkedInError(
                f"LinkedIn API {resp.status_code} on {resp.request.method} "
                f"{resp.request.url}: {detail}"
            )

    def _ugc_post(self, share_content: dict, visibility: str) -> dict:
        body = {
            "author": self.author_urn(),
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": visibility},
        }
        with httpx.Client(timeout=60) as c:
            resp = c.post(f"{API_BASE}/v2/ugcPosts", headers=self._headers(), json=body)
        self._check(resp)
        urn = resp.headers.get("x-restli-id")
        if not urn:
            try:
                urn = resp.json().get("id", "")
            except ValueError:
                urn = ""
        if not urn:
            raise LinkedInError(
                "Post may have been created but LinkedIn returned no post URN; "
                "verify on your feed before retrying to avoid a duplicate."
            )
        return {"post_urn": urn, "url": post_url(urn), "status": "PUBLISHED"}

    # -- identity -----------------------------------------------------------

    def get_profile(self) -> dict:
        """Return the authenticated member's OpenID profile."""
        with httpx.Client(timeout=30) as c:
            resp = c.get(f"{API_BASE}/v2/userinfo", headers=self._headers())
        self._check(resp)
        return resp.json()

    def author_urn(self) -> str:
        """The `urn:li:person:{id}` used as post/comment author."""
        if self._cached_urn is None:
            sub = self.get_profile().get("sub")
            if not sub:
                raise LinkedInError(
                    "Could not read member id (sub) from /userinfo. "
                    "Is the 'openid profile' scope granted?"
                )
            self._cached_urn = f"urn:li:person:{sub}"
        return self._cached_urn

    # -- posting ------------------------------------------------------------

    def create_post(self, text: str, visibility: str = "PUBLIC") -> dict:
        """Publish a plain-text share to the member's feed.

        visibility: PUBLIC | CONNECTIONS
        """
        return self._ugc_post(
            {"shareCommentary": {"text": text}, "shareMediaCategory": "NONE"},
            visibility,
        )

    def share_link(
        self,
        text: str,
        url: str,
        title: str | None = None,
        description: str | None = None,
        visibility: str = "PUBLIC",
    ) -> dict:
        """Share a URL with an auto-generated preview card."""
        media: dict = {"status": "READY", "originalUrl": url}
        if title:
            media["title"] = {"text": title}
        if description:
            media["description"] = {"text": description}
        return self._ugc_post(
            {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "ARTICLE",
                "media": [media],
            },
            visibility,
        )

    def _register_and_upload(self, path: Path, recipe: str) -> str:
        """Register an upload for `recipe`, PUT the bytes, return the asset URN."""
        register_body = {
            "registerUploadRequest": {
                "recipes": [recipe],
                "owner": self.author_urn(),
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }
        with httpx.Client(timeout=120) as c:
            reg = c.post(
                f"{API_BASE}/v2/assets?action=registerUpload",
                headers=self._headers(),
                json=register_body,
            )
            self._check(reg)
            value = reg.json()["value"]
            asset = value["asset"]
            upload_url = value["uploadMechanism"][
                "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
            ]["uploadUrl"]
            # Only send the bearer token to a LinkedIn host, in case the
            # register response is ever tampered with or misdirected.
            host = urllib.parse.urlparse(upload_url).hostname or ""
            if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
                raise LinkedInError(f"Refusing to upload to non-LinkedIn host: {host}")
            put = c.put(
                upload_url,
                headers={"Authorization": f"Bearer {get_access_token()}"},
                content=path.read_bytes(),
            )
            self._check(put)
        return asset

    def upload_image(self, image_path: str) -> str:
        """Register and upload an image, returning its digitalmediaAsset URN."""
        path = _safe_media_path(image_path)
        return self._register_and_upload(
            path, "urn:li:digitalmediaRecipe:feedshare-image"
        )

    def share_image(
        self,
        text: str,
        image_path: str,
        title: str | None = None,
        alt_text: str | None = None,
        visibility: str = "PUBLIC",
    ) -> dict:
        """Upload a local image and publish it as a feed post."""
        return self.share_images(
            text,
            [image_path],
            visibility=visibility,
            titles=[title] if title else None,
            alt_texts=[alt_text] if alt_text else None,
        )

    def share_images(
        self,
        text: str,
        image_paths: list[str],
        titles: list[str] | None = None,
        alt_texts: list[str] | None = None,
        visibility: str = "PUBLIC",
    ) -> dict:
        """Upload several local images and publish them as one feed post.

        LinkedIn allows up to 9 images per post.
        """
        if not image_paths:
            raise LinkedInError("share_images requires at least one image path")
        if len(image_paths) > 9:
            raise LinkedInError("LinkedIn allows at most 9 images per post")
        media = []
        for i, p in enumerate(image_paths):
            asset = self.upload_image(p)
            item: dict = {"status": "READY", "media": asset}
            if titles and i < len(titles) and titles[i]:
                item["title"] = {"text": titles[i]}
            if alt_texts and i < len(alt_texts) and alt_texts[i]:
                item["description"] = {"text": alt_texts[i]}
            media.append(item)
        return self._ugc_post(
            {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "IMAGE",
                "media": media,
            },
            visibility,
        )

    def delete_post(self, post_urn: str) -> dict:
        """Delete one of your shares/ugcPosts."""
        encoded = urllib.parse.quote(post_urn, safe="")
        with httpx.Client(timeout=30) as c:
            resp = c.delete(
                f"{API_BASE}/v2/ugcPosts/{encoded}", headers=self._headers()
            )
        self._check(resp)
        return {"post_urn": post_urn, "status": "DELETED"}

    # -- comments -----------------------------------------------------------

    def list_comments(self, post_urn: str, count: int = 20) -> dict:
        """List comments on a post/share you have access to."""
        encoded = urllib.parse.quote(post_urn, safe="")
        with httpx.Client(timeout=30) as c:
            resp = c.get(
                f"{API_BASE}/v2/socialActions/{encoded}/comments",
                headers=self._headers(),
                params={"count": count},
            )
        self._check(resp)
        return resp.json()

    def reply_comment(self, post_urn: str, text: str) -> dict:
        """Add a comment to a post/share (e.g. reply under your own post)."""
        encoded = urllib.parse.quote(post_urn, safe="")
        body = {"actor": self.author_urn(), "message": {"text": text}}
        with httpx.Client(timeout=30) as c:
            resp = c.post(
                f"{API_BASE}/v2/socialActions/{encoded}/comments",
                headers=self._headers(),
                json=body,
            )
        self._check(resp)
        return resp.json()

    # -- analytics ----------------------------------------------------------

    def get_post_stats(self, post_urn: str) -> dict:
        """Return engagement counts (likes, comments) for a post.

        Uses the legacy /v2/socialActions endpoint. Reading social actions may
        require additional permissions (e.g. r_member_social) depending on your
        app; if so this returns a LinkedIn 403 you can surface to the user.
        Organic impressions/reach are NOT available here — those need the
        partner-gated memberCreatorPostAnalytics endpoint.
        """
        encoded = urllib.parse.quote(post_urn, safe="")
        with httpx.Client(timeout=30) as c:
            resp = c.get(
                f"{API_BASE}/v2/socialActions/{encoded}", headers=self._headers()
            )
        self._check(resp)
        data = resp.json()
        likes = data.get("likesSummary", {}) or {}
        comments = data.get("commentsSummary", {}) or {}
        return {
            "post_urn": post_urn,
            "url": post_url(post_urn),
            "likes": likes.get("totalLikes", likes.get("aggregatedTotalLikes", 0)),
            "comments": comments.get(
                "aggregatedTotalComments", comments.get("count", 0)
            ),
        }
