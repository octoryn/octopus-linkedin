"""OAuth 2.0 (3-legged) for LinkedIn.

Run this once to authorize and cache a token:

    python -m linkedin.auth

It opens your browser, you log in and approve, and the access token is saved
to token.json in the project root. The MCP server reads that file.

LinkedIn member access tokens last ~60 days. Refresh tokens are only issued to
approved apps; if you have one it's used automatically, otherwise just re-run
this command when the token expires.
"""

from __future__ import annotations

import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

TOKEN_PATH = Path(__file__).resolve().parent.parent / "token.json"


def _cfg() -> dict[str, str]:
    cid = os.getenv("LINKEDIN_CLIENT_ID")
    secret = os.getenv("LINKEDIN_CLIENT_SECRET")
    redirect = os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/callback")
    scopes = os.getenv("LINKEDIN_SCOPES", "openid profile email w_member_social")
    if not cid or not secret:
        raise RuntimeError(
            "LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET are not set. "
            "Copy .env.example to .env and fill them in."
        )
    return {"cid": cid, "secret": secret, "redirect": redirect, "scopes": scopes}


# LinkedIn member tokens last ~60 days; assume that if a response omits
# expires_in so we don't treat a valid token as already expired.
DEFAULT_EXPIRES_IN = 60 * 24 * 3600


def save_token(payload: dict) -> None:
    """Persist the token response, stamping an absolute expiry time."""
    if not payload.get("access_token"):
        raise RuntimeError(
            f"Token response has no access_token: {payload!r}. Not saving."
        )
    payload = dict(payload)
    expires_in = int(payload.get("expires_in") or DEFAULT_EXPIRES_IN)
    payload["obtained_at"] = int(time.time())
    payload["expires_at"] = int(time.time()) + expires_in
    TOKEN_PATH.write_text(json.dumps(payload, indent=2))
    TOKEN_PATH.chmod(0o600)


def load_token() -> dict | None:
    if not TOKEN_PATH.exists():
        return None
    return json.loads(TOKEN_PATH.read_text())


def get_access_token() -> str:
    """Return a valid access token, refreshing or erroring with guidance."""
    tok = load_token()
    if not tok:
        raise RuntimeError(
            "No token found. Run `python -m linkedin.auth` to authorize first."
        )
    # 5-minute safety margin
    if tok.get("expires_at", 0) > int(time.time()) + 300:
        return tok["access_token"]

    refresh = tok.get("refresh_token")
    if refresh:
        cfg = _cfg()
        try:
            resp = httpx.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                    "client_id": cfg["cid"],
                    "client_secret": cfg["secret"],
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            resp.raise_for_status()
            new = resp.json()
        except httpx.HTTPError as e:
            raise RuntimeError(
                "Token refresh failed; run `python -m linkedin.auth` to "
                f"re-authorize. ({e})"
            ) from e
        new.setdefault("refresh_token", refresh)
        save_token(new)  # validates access_token is present
        return new["access_token"]

    raise RuntimeError(
        "Access token expired and no refresh token available. "
        "Run `python -m linkedin.auth` again to re-authorize."
    )


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Captures the ?code=... redirect from LinkedIn."""

    code: str | None = None
    state: str | None = None
    error: str | None = None

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != urllib.parse.urlparse(_CallbackHandler.expected_path).path:
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        _CallbackHandler.code = qs.get("code", [None])[0]
        _CallbackHandler.state = qs.get("state", [None])[0]
        _CallbackHandler.error = qs.get("error_description", qs.get("error", [None]))[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        body = (
            "<h2>LinkedIn authorization complete.</h2>"
            "<p>You can close this tab and return to the terminal.</p>"
            if _CallbackHandler.error is None
            else f"<h2>Authorization failed</h2><p>{_CallbackHandler.error}</p>"
        )
        self.wfile.write(body.encode())

    def log_message(self, *args):  # silence the default request logging
        pass


def authorize() -> dict:
    """Run the full 3-legged flow and cache the token."""
    cfg = _cfg()
    parsed_redirect = urllib.parse.urlparse(cfg["redirect"])
    host = parsed_redirect.hostname or "localhost"
    port = parsed_redirect.port or 8000
    _CallbackHandler.expected_path = cfg["redirect"]

    state = secrets.token_urlsafe(16)
    auth_url = (
        AUTHORIZE_URL
        + "?"
        + urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": cfg["cid"],
                "redirect_uri": cfg["redirect"],
                "state": state,
                "scope": cfg["scopes"],
            }
        )
    )

    server = http.server.HTTPServer((host, port), _CallbackHandler)
    # Serve continuously (not just one request) so stray browser hits like
    # /favicon.ico don't consume our single shot before the real callback.
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print("Opening browser to authorize. If it doesn't open, visit:\n", auth_url)
    webbrowser.open(auth_url)

    deadline = time.time() + 300
    while time.time() < deadline:
        if _CallbackHandler.code or _CallbackHandler.error:
            break
        time.sleep(0.5)
    server.shutdown()
    server.server_close()

    if _CallbackHandler.error:
        raise RuntimeError(f"Authorization failed: {_CallbackHandler.error}")
    if not _CallbackHandler.code:
        raise RuntimeError("Timed out waiting for the LinkedIn redirect.")
    if _CallbackHandler.state != state:
        raise RuntimeError("State mismatch — possible CSRF, aborting.")

    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": _CallbackHandler.code,
            "redirect_uri": cfg["redirect"],
            "client_id": cfg["cid"],
            "client_secret": cfg["secret"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()
    save_token(token)
    print(f"\nToken saved to {TOKEN_PATH}")
    print(f"Scopes granted: {token.get('scope', cfg['scopes'])}")
    return token


if __name__ == "__main__":
    authorize()
