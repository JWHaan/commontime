"""MCP server exposing TimeTree availability as tools any agent can call.

Transport: stdio. Configure your MCP client with:

    { "mcpServers": { "commontime": {
        "command": "commontime-mcp",
        "env": {
          "TIMETREE_EMAIL": "you@example.com",
          "TIMETREE_PASSWORD": "secret",
          "TIMETREE_CALENDAR_CODE": "xxxxxx"
        } } } }

Tools:
  - find_free_slots: free meeting windows, Mon-Fri, 08:00-20:00 by default.
  - list_calendars: discover calendar names and codes for the login.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

from commontime import find_slots, resolve_week

mcp = FastMCP("commontime")


def _parse_hhmm(value: str):
    h, m = value.split(":")
    from datetime import time as dtime
    return dtime(int(h), int(m))


@mcp.tool()
def find_free_slots(
    week_start: str | None = None,
    duration_min: int = 120,
    day_start: str = "08:00",
    day_end: str = "20:00",
    timezone: str = "Asia/Singapore",
    step_min: int = 30,
    source: str = "timetree",
    calendars: list[str] | None = None,
    calendar_code: str | None = None,
    public_calendar: bool = False,
) -> dict:
    """Find meeting slots free on ALL member calendars (Mon-Fri, hard day window).

    Args:
        week_start: Monday of the week to check (YYYY-MM-DD). Default: next Monday.
        duration_min: Meeting length in minutes — any length the user wants.
        day_start/day_end: Hard daily window (HH:MM). Slots never fall outside it.
        timezone: IANA timezone for days and output.
        step_min: Candidate start granularity in minutes.
        source: 'timetree' or 'google'.
        calendars: Member calendars (TimeTree codes or Google ids/emails).
            Defaults: TIMETREE_CALENDAR_CODE, or GOOGLE_CALENDARS env.
        calendar_code: Deprecated alias for a single TimeTree calendar.
        public_calendar: Set true to use a public TimeTree id without login.
    """
    from commontime import resolve_week

    tz = ZoneInfo(timezone)
    cals = list(calendars or [])
    if not cals:
        if source == "google":
            env = os.environ.get("GOOGLE_CALENDARS", "")
            cals = [c.strip() for c in env.split(",") if c.strip()] or ["primary"]
        else:
            cals = [calendar_code or os.environ.get("TIMETREE_CALENDAR_CODE")]
    if not cals or not cals[0]:
        raise ValueError("No calendar: pass calendars or set TIMETREE_CALENDAR_CODE / GOOGLE_CALENDARS.")
    cals = [c for c in cals if c]
    days = resolve_week(week_start, tz)
    ds, de = _parse_hhmm(day_start), _parse_hhmm(day_end)
    if source == "google":
        from providers import google_busy
        busy = google_busy(cals, days, tz, ds, de)
    else:
        from commontime import export_ics, load_busy
        tmp = tempfile.NamedTemporaryFile(suffix=".ics", delete=False)
        tmp.close()
        try:
            export_ics(cals[0], tmp.name, public=public_calendar)
            busy = load_busy(tmp.name, tz, days, ds, de)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    slots = find_slots(days, busy, tz, ds, de, duration_min, step_min)
    return {"source": source, "calendars": cals,
            "week": [d.isoformat() for d in days], "timezone": timezone,
            "window": f"{day_start}-{day_end}", "duration_min": duration_min,
            "slots": slots}


@mcp.tool()
def list_calendars(source: str = "timetree") -> list[dict]:
    """List calendars (name + id/code) visible to the login in env vars.

    Args:
        source: 'timetree' or 'google'.
    """
    if source == "google":
        from providers import google_calendars
        return google_calendars()
    from timetree_exporter.api.auth import login
    from timetree_exporter.api.calendar import TimeTreeCalendar

    email = os.environ.get("TIMETREE_EMAIL")
    password = os.environ.get("TIMETREE_PASSWORD")
    if not email or not password:
        raise ValueError("Set TIMETREE_EMAIL and TIMETREE_PASSWORD.")
    api = TimeTreeCalendar(login(email, password))
    return [{"name": m.get("name"), "alias_code": m.get("alias_code")}
            for m in api.get_metadata() if m.get("deactivated_at") is None]


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
