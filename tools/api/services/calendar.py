"""Backend Google Calendar access — used at cron time (no interactive session available).

Reads a token written once by scripts/google_oauth_setup.py (run on the host,
needs a browser). Auto-refreshes the access token on expiry and rewrites it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import settings

SCOPES = ["https://www.googleapis.com/auth/calendar"]

DEFAULT_CALENDAR_ID = settings.google_calendar_ids.split(",")[0].strip()

_WEEKDAY_RRULE = {
    "mon": "MO", "tue": "TU", "wed": "WE", "thu": "TH",
    "fri": "FR", "sat": "SA", "sun": "SU",
}
WEEKDAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


class CalendarAuthenticationError(RuntimeError):
    """The local OAuth grant cannot be used without a host-side re-login."""


def _load_credentials() -> Credentials:
    token_path = Path(settings.google_token_path)
    if not token_path.exists():
        raise RuntimeError(
            f"No Google token at {token_path} — run "
            "tools/api/scripts/google_oauth_setup.py on the host first."
        )

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            raise CalendarAuthenticationError(
                "Google Calendar authorization has expired or been revoked. "
                "Re-authenticate on the host, then try again."
            ) from exc
        # Credentials are mounted read-only.  The refreshed token remains
        # process-local; root-owned credential maintenance persists it.
    return creds


def verify_default_calendar_access() -> None:
    """Fail a batch early when its configured Google grant is unusable.

    This read-only request prevents a revoked token from being retried for
    every routine occurrence.
    """
    creds = _load_credentials()
    service = build("calendar", "v3", credentials=creds)
    service.calendars().get(calendarId=DEFAULT_CALENDAR_ID).execute()


def list_upcoming_events(days_ahead: int = 14) -> list[dict]:
    """Events across all configured calendars, next `days_ahead` days."""
    now = datetime.now(timezone.utc)
    return list_events_in_range(now, now + timedelta(days=days_ahead))


def list_events_in_range(start: datetime, end: datetime) -> list[dict]:
    """Read calendar events in a bounded range without changing them."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("calendar range must include a timezone")
    if end <= start:
        raise ValueError("calendar range end must be after start")

    creds = _load_credentials()
    service = build("calendar", "v3", credentials=creds)

    events: list[dict] = []
    for calendar_id in settings.google_calendar_ids.split(","):
        calendar_id = calendar_id.strip()
        if not calendar_id:
            continue
        page_token = None
        while True:
            resp = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=start.isoformat(),
                    timeMax=end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                )
                .execute()
            )
            for item in resp.get("items", []):
                start_value = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
                end_value = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
                if not start_value or not end_value:
                    continue
                events.append(
                    {
                        "id": item.get("id", ""),
                        "title": item.get("summary", "(no title)"),
                        "start": start_value,
                        "end": end_value,
                        "all_day": "date" in item.get("start", {}),
                    }
                )
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    return sorted(events, key=lambda item: item["start"])


def summarize_busy_windows(days_ahead: int = 14) -> list[dict]:
    """Compact per-day busy ranges — much cheaper to feed an LLM than raw event dumps."""
    events = list_upcoming_events(days_ahead=days_ahead)
    by_day: dict[str, list[tuple[str, str]]] = {}
    for e in events:
        start, end = e.get("start"), e.get("end")
        if not start or not end or "T" not in start:
            continue  # skip all-day events (no dateTime)
        day = start[:10]
        by_day.setdefault(day, []).append((start[11:16], end[11:16]))

    weekday_abbr = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    summary = []
    for day in sorted(by_day):
        windows = sorted(by_day[day])
        merged: list[list[str]] = []
        for s, e in windows:
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        weekday = weekday_abbr[datetime.strptime(day, "%Y-%m-%d").weekday()]
        summary.append({"date": day, "weekday": weekday, "busy": merged})
    return summary


def create_recurring_event(
    title: str,
    start_time: str,
    days: list[str],
    duration_minutes: int,
    calendar_id: str = DEFAULT_CALENDAR_ID,
) -> str:
    """Create a weekly-recurring event (a wizard fixed_block) and return its Google event id."""
    creds = _load_credentials()
    service = build("calendar", "v3", credentials=creds)

    # Anchor DTSTART on the next occurrence of the first requested weekday —
    # Google Calendar includes the literal DTSTART date as an occurrence even
    # when it doesn't match BYDAY, producing a spurious first event otherwise.
    target_weekday = WEEKDAY_INDEX[days[0].lower()[:3]]
    today = datetime.now().date()
    days_until = (target_weekday - today.weekday()) % 7
    anchor_date = today + timedelta(days=days_until)

    hour, minute = (int(p) for p in start_time.split(":"))
    start_dt = datetime.combine(anchor_date, datetime.min.time()).replace(hour=hour, minute=minute)
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    byday = ",".join(_WEEKDAY_RRULE[d.lower()[:3]] for d in days if d.lower()[:3] in _WEEKDAY_RRULE)

    body = {
        "summary": title,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
        "recurrence": [f"RRULE:FREQ=WEEKLY;BYDAY={byday}"] if byday else [],
    }
    created = service.events().insert(calendarId=calendar_id, body=body).execute()
    return created["id"]


def create_event(
    title: str,
    start_iso: str,
    duration_minutes: int,
    calendar_id: str = DEFAULT_CALENDAR_ID,
    description: str | None = None,
) -> str:
    """Create a single (non-recurring) event — used for insight-recommended add blocks."""
    creds = _load_credentials()
    service = build("calendar", "v3", credentials=creds)

    start_dt = datetime.fromisoformat(start_iso)
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    body = {
        "summary": title,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
    }
    if description:
        body["description"] = description
    created = service.events().insert(calendarId=calendar_id, body=body).execute()
    return created["id"]


def update_event_time(
    event_id: str,
    start_iso: str,
    duration_minutes: int | None = None,
    calendar_id: str = DEFAULT_CALENDAR_ID,
) -> None:
    creds = _load_credentials()
    service = build("calendar", "v3", credentials=creds)

    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    start_dt = datetime.fromisoformat(start_iso)
    if duration_minutes is None:
        old_start = datetime.fromisoformat(event["start"]["dateTime"])
        old_end = datetime.fromisoformat(event["end"]["dateTime"])
        duration_minutes = int((old_end - old_start).total_seconds() // 60)
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    event["start"] = {"dateTime": start_dt.isoformat(), "timeZone": "America/Sao_Paulo"}
    event["end"] = {"dateTime": end_dt.isoformat(), "timeZone": "America/Sao_Paulo"}
    service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()


def delete_event(event_id: str, calendar_id: str = DEFAULT_CALENDAR_ID) -> None:
    creds = _load_credentials()
    service = build("calendar", "v3", credentials=creds)
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
