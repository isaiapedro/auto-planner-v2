"""
One-time Google Calendar OAuth setup for pios_api's backend calendar access.

Run this ONCE on the host machine (needs a real browser — won't work inside
the pios_api container). Writes google_token.json into ./credentials/, which
is bind-mounted into the container and used for all subsequent cron-triggered
calendar reads.

Usage:
    pip install google-auth-oauthlib google-api-python-client
    python3 tools/api/scripts/google_oauth_setup.py
"""
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]

ROOT = Path(__file__).resolve().parents[3]
CLIENT_SECRET_PATH = ROOT / "credentials" / "google_client_secret.json"
TOKEN_PATH = ROOT / "credentials" / "google_token.json"


def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"Token written to {TOKEN_PATH}")


if __name__ == "__main__":
    main()
