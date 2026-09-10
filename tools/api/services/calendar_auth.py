"""Interactive Google OAuth flow, triggerable from the API itself.

Replaces the standalone `credentials/auth.py` script (run manually on a host with a
browser, tokens copy-pasted by hand). Instead:

1. POST /calendar/auth/start   -> returns a Google consent URL + a state token.
2. User opens that URL in any browser on the same machine/network as this API
   (network_mode: host means the loopback callback server below is reachable
   from the host's browser).
3. POST /calendar/auth/wait/{state} blocks until Google redirects back to our
   local callback server, then exchanges the code and writes
   settings.google_token_path automatically. No manual copy-paste.

The redirect URI is a fixed loopback port with an empty path (http://localhost:8765/)
because the registered OAuth client is a "Desktop" client — Google only allows the
special loopback redirect matching for http://localhost with no custom path.
"""
from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from google_auth_oauthlib.flow import Flow

from config import settings
from services.calendar import SCOPES

_CALLBACK_PORT = 8765
_REDIRECT_URI = f"http://localhost:{_CALLBACK_PORT}/"

_pending: dict[str, dict] = {}
_server: HTTPServer | None = None
_server_lock = threading.Lock()


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — required name by BaseHTTPRequestHandler
        qs = parse_qs(urlparse(self.path).query)
        state = qs.get("state", [None])[0]
        entry = _pending.get(state) if state else None

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        if entry is None:
            self.wfile.write(b"<html><body>Unknown or expired auth session. You can close this tab.</body></html>")
            return

        entry["code"] = qs.get("code", [None])[0]
        entry["error"] = qs.get("error", [None])[0]
        entry["event"].set()
        self.wfile.write(b"<html><body>Google Calendar connected. You can close this tab.</body></html>")

    def log_message(self, format: str, *args) -> None:  # noqa: A002 — silence default access log
        pass


def _ensure_server_running() -> None:
    global _server
    with _server_lock:
        if _server is not None:
            return
        _server = HTTPServer(("127.0.0.1", _CALLBACK_PORT), _CallbackHandler)
        threading.Thread(target=_server.serve_forever, daemon=True).start()


def build_auth_url() -> tuple[str, str]:
    """Start a new OAuth session. Returns (auth_url, state) — open auth_url in a browser."""
    _ensure_server_running()
    flow = Flow.from_client_secrets_file(
        settings.google_credentials_path,
        scopes=SCOPES,
        redirect_uri=_REDIRECT_URI,
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    _pending[state] = {"event": threading.Event(), "code": None, "error": None, "flow": flow}
    return auth_url, state


async def wait_for_token(state: str, timeout: float = 300.0) -> dict:
    """Block off the event loop until consent completes, then persist the token to disk."""
    entry = _pending.get(state)
    if entry is None:
        raise ValueError(f"Unknown or already-consumed auth state: {state}")

    def _wait_and_exchange() -> dict:
        if not entry["event"].wait(timeout):
            raise TimeoutError("Timed out waiting for Google OAuth consent")
        if entry["error"]:
            raise RuntimeError(f"Google OAuth error: {entry['error']}")

        flow: Flow = entry["flow"]
        flow.fetch_token(code=entry["code"])
        creds = flow.credentials
        Path(settings.google_token_path).write_text(creds.to_json())
        return {"expiry": str(creds.expiry), "scopes": creds.scopes}

    try:
        return await asyncio.to_thread(_wait_and_exchange)
    finally:
        _pending.pop(state, None)
