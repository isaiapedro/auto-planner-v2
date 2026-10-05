"""Create the host-owned Google Calendar OAuth token used by Planner.

Run this on the host, not in the API container. It opens a browser-based
Google consent flow and writes only the ignored credentials token file.
"""
from __future__ import annotations

import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/calendar"]
PLANNER_ROOT = Path(__file__).resolve().parents[4]
CREDENTIALS_DIR = PLANNER_ROOT / "environment" / "credentials"
CLIENT_SECRET_PATH = CREDENTIALS_DIR / "google_client_secret.json"
TOKEN_PATH = CREDENTIALS_DIR / "google_token.json"


def main() -> None:
    if not CLIENT_SECRET_PATH.is_file():
        raise SystemExit(f"Google OAuth client secret not found at {CLIENT_SECRET_PATH}")

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    credentials = flow.run_local_server(port=0, open_browser=True)
    TOKEN_PATH.write_text(credentials.to_json() + "\n", encoding="utf-8")
    os.chmod(TOKEN_PATH, 0o600)
    print(f"Google Calendar authorization saved to {TOKEN_PATH}")


if __name__ == "__main__":
    main()
