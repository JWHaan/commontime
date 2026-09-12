"""Calendar providers for CommonTime.

Each provider returns busy intervals clipped to the day window, merged per day::

    dict[date, list[(start, end)]]

When several member calendars are given, busy intervals are UNIONED — a slot is
free only if it is free on every member's calendar.
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
DEFAULT_TOKEN_FILE = Path.home() / ".config" / "commontime" / "google_token.json"


def google_service(client_secrets: str | None = None, token_file: str | None = None):
    """Build an authenticated Google Calendar API service (OAuth, cached token)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    secrets = client_secrets or os.environ.get("GOOGLE_CLIENT_SECRETS")
    token_path = Path(token_file or os.environ.get("GOOGLE_TOKEN_FILE", DEFAULT_TOKEN_FILE))
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not secrets:
                raise SystemExit(
                    "Google source needs GOOGLE_CLIENT_SECRETS (OAuth desktop-client JSON) "
                    "on first run. The token is cached at GOOGLE_TOKEN_FILE for later runs."
                )
            flow = InstalledAppFlow.from_client_secrets_file(secrets, SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def google_busy(calendar_ids: list[str], days: list[date], tz: ZoneInfo,
                day_start: time, day_end: time,
                service=None, client_secrets: str | None = None,
                token_file: str | None = None) -> dict[date, list[tuple[datetime, datetime]]]:
    """Busy intervals unioned across member calendars via the freebusy API."""
    from commontime import clip_range_to_days, merge_intervals

    svc = service or google_service(client_secrets, token_file)
    time_min = datetime.combine(days[0], time(0, 0), tz).isoformat()
    time_max = datetime.combine(days[-1] + timedelta(days=1), time(0, 0), tz).isoformat()
    resp = svc.freebusy().query(body={
        "timeMin": time_min, "timeMax": time_max, "timeZone": str(tz),
        "items": [{"id": c} for c in calendar_ids],
    }).execute()
    busy: dict[date, list[tuple[datetime, datetime]]] = defaultdict(list)
    day_set = set(days)
    for cal in resp.get("calendars", {}).values():
        for block in cal.get("busy", []):
            ss = datetime.fromisoformat(block["start"]).astimezone(tz)
            ee = datetime.fromisoformat(block["end"]).astimezone(tz)
            clip_range_to_days(ss, ee, days, day_set, tz, day_start, day_end, busy)
    return {d: merge_intervals(busy[d]) for d in busy}


def google_calendars(service=None, client_secrets: str | None = None,
                     token_file: str | None = None) -> list[dict]:
    """List calendars visible to the Google login (id + name)."""
    svc = service or google_service(client_secrets, token_file)
    items, page_token = [], None
    while True:
        resp = svc.calendarList().list(pageToken=page_token).execute()
        items.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return [{"id": c.get("id"), "name": c.get("summary")} for c in items]
