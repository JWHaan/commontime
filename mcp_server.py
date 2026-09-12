"""MCP server exposing TimeTree availability as tools any agent can call.

Transport: stdio. Configure your MCP client with:

    { "mcpServers": { "timetree-availability": {
        "command": "timetree-availability-mcp",
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

from timetree_slots import export_ics, find_slots, load_busy, resolve_week

mcp = FastMCP("timetree-availability")


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
    calendar_code: str | None = None,
    public_calendar: bool = False,
) -> dict:
    """Find free meeting slots on the TimeTree calendar (Mon-Fri, hard day window).

    Args:
        week_start: Monday of the week to check (YYYY-MM-DD). Default: next Monday.
        duration_min: Meeting length in minutes.
        day_start/day_end: Hard daily window (HH:MM). Slots never fall outside it.
        timezone: IANA timezone for days and output.
        step_min: Candidate start granularity in minutes.
        calendar_code: TimeTree calendar code (default: TIMETREE_CALENDAR_CODE env).
        public_calendar: Set true to use a public calendar id without login.
    """
    tz = ZoneInfo(timezone)
    code = calendar_code or os.environ.get("TIMETREE_CALENDAR_CODE")
    if not code:
        raise ValueError("No calendar: pass calendar_code or set TIMETREE_CALENDAR_CODE.")
    days = resolve_week(week_start, tz)
    tmp = tempfile.NamedTemporaryFile(suffix=".ics", delete=False)
    tmp.close()
    try:
        export_ics(code, tmp.name, public=public_calendar)
        busy = load_busy(tmp.name, tz, days, _parse_hhmm(day_start), _parse_hhmm(day_end))
        slots = find_slots(days, busy, tz, _parse_hhmm(day_start), _parse_hhmm(day_end),
                           duration_min, step_min)
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    return {"week": [d.isoformat() for d in days], "timezone": timezone,
            "window": f"{day_start}-{day_end}", "duration_min": duration_min,
            "slots": slots}


@mcp.tool()
def list_calendars() -> list[dict]:
    """List TimeTree calendars (name + code) visible to the login in env vars."""
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
