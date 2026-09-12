"""Find shared meeting slots on any supported calendar (TimeTree, Google).

Weekdays Mon-Fri, hard day window 08:00-20:00 (default Asia/Singapore).
Give one or more member calendars: a slot is free only if free on ALL of them.

Usage:
    commontime --source timetree --calendar 7X9fYzh41yRx
    commontime --source google --calendar alice@example.com --calendar bob@example.com
    commontime --source google --calendar primary --duration 60 --week-start 2026-09-14
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from icalendar import Calendar as ICalendar
except ImportError:  # pragma: no cover
    print("Missing dependency: pip install -r requirements.txt", file=sys.stderr)
    raise

DAY_START = time(8, 0)
DAY_END = time(20, 0)
SLOT_MINUTES = 120
STEP_MINUTES = 30


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Find shared meeting slots (Mon-Fri, hard day window).")
    p.add_argument("--source", default=os.environ.get("COMMONTIME_SOURCE", "timetree"),
                   choices=["timetree", "google"],
                   help="Calendar platform (default: timetree).")
    p.add_argument("--calendar", action="append", default=None, dest="calendars",
                   help="Member calendar: TimeTree code or Google calendar id/email. "
                        "Repeat for each member; free = free on ALL. "
                        "Defaults: TIMETREE_CALENDAR_CODE, or GOOGLE_CALENDARS (comma-separated).")
    p.add_argument("--week-start", default=None,
                   help="Monday of the week to check (YYYY-MM-DD). Default: next Monday in --timezone.")
    p.add_argument("--timezone", default=os.environ.get("SLOT_TIMEZONE", "Asia/Singapore"))
    p.add_argument("--day-start", default=os.environ.get("SLOT_DAY_START", "08:00"))
    p.add_argument("--day-end", default=os.environ.get("SLOT_DAY_END", "20:00"))
    p.add_argument("--duration", type=int, default=int(os.environ.get("SLOT_DURATION_MIN", "120")),
                   help="Meeting length in minutes (default 120).")
    p.add_argument("--step", type=int, default=30, help="Candidate start granularity in minutes (default 30).")
    p.add_argument("--calendar-code", default=os.environ.get("TIMETREE_CALENDAR_CODE"),
                   help="Deprecated alias for --calendar (TimeTree).")
    p.add_argument("--public-calendar", action="store_true",
                   help="Treat the TimeTree calendar as a public id (no login).")
    p.add_argument("--client-secrets", default=os.environ.get("GOOGLE_CLIENT_SECRETS"),
                   help="Google OAuth desktop-client JSON (first run only; token is cached).")
    p.add_argument("--token-file", default=os.environ.get("GOOGLE_TOKEN_FILE"),
                   help="Google token cache path.")
    p.add_argument("--ics", default=None, help="Use an existing .ics file instead of fetching (TimeTree shape).")
    p.add_argument("--json", action="store_true", dest="as_json", help="Output JSON.")
    return p.parse_args()


def monday_of_week(ref: date) -> date:
    return ref - timedelta(days=ref.weekday())


def resolve_week(week_start: str | None, tz: ZoneInfo) -> list[date]:
    if week_start:
        mon = date.fromisoformat(week_start)
        if mon.weekday() != 0:
            raise SystemExit("--week-start must be a Monday (YYYY-MM-DD).")
    else:
        today = datetime.now(tz).date()
        # Next Monday (if today is Sat/Sun/any weekday, take upcoming Monday;
        # if today IS Monday, check this week)
        delta = (0 - today.weekday()) % 7
        mon = today + timedelta(days=delta)
    return [mon + timedelta(days=i) for i in range(5)]  # Mon-Fri


def export_ics(code: str, dest: str, public: bool = False) -> None:
    from timetree_exporter.api.auth import login
    from timetree_exporter.api.calendar import TimeTreeCalendar
    from timetree_exporter.calendar import Calendar
    from timetree_exporter.exporter import Exporter

    if public:
        calendar = Calendar(TimeTreeCalendar(""), {
            "id": code, "name": f"Public Calendar {code}",
            "alias_code": code, "public": True,
        })
    else:
        email = os.environ.get("TIMETREE_EMAIL")
        password = os.environ.get("TIMETREE_PASSWORD")
        if not email or not password:
            raise SystemExit("Set TIMETREE_EMAIL and TIMETREE_PASSWORD (see .env.example).")
        session_id = login(email, password)
        api = TimeTreeCalendar(session_id)
        metas = [m for m in api.get_metadata() if m.get("deactivated_at") is None]
        match = [m for m in metas if m.get("alias_code") == code] if code else []
        if not match:
            available = ", ".join(f"{m.get('name')} ({m.get('alias_code')})" for m in metas) or "none"
            raise SystemExit(f"Calendar code {code!r} not found. Available: {available}")
        calendar = Calendar(api, match[0])
    Exporter(calendar, dest).export()


def _as_tz(dt, tz: ZoneInfo) -> datetime:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt.astimezone(tz)
    raise TypeError


def clip_range_to_days(ss: datetime, ee: datetime, days: list[date], day_set: set[date],
                       tz: ZoneInfo, day_start: time, day_end: time,
                       busy: dict[date, list[tuple[datetime, datetime]]]) -> None:
    """Clip a [start, end) range into per-day windowed busy intervals (multi-day aware)."""
    cur = ss.date()
    while cur <= ee.date():
        if cur in day_set:
            w0 = datetime.combine(cur, day_start, tz)
            w1 = datetime.combine(cur, day_end, tz)
            b0, b1 = max(ss, w0), min(ee, w1)
            if b0 < b1:
                busy[cur].append((b0, b1))
        cur += timedelta(days=1)


def merge_intervals(blocks: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[list[datetime]] = []
    for b0, b1 in sorted(blocks):
        if merged and b0 <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b1)
        else:
            merged.append([b0, b1])
    return [(a, b) for a, b in merged]


def load_busy(ics_path: str, tz: ZoneInfo, days: list[date],
              day_start: time, day_end: time) -> dict[date, list[tuple[datetime, datetime]]]:
    with open(ics_path, "rb") as f:
        cal = ICalendar.from_ical(f.read())
    busy: dict[date, list[tuple[datetime, datetime]]] = defaultdict(list)
    day_set = set(days)
    for comp in cal.walk():
        if comp.name != "VEVENT":
            continue
        s = comp.get("dtstart").dt
        e = comp.get("dtend").dt if comp.get("dtend") else s
        if isinstance(s, datetime) and isinstance(e, datetime):
            clip_range_to_days(_as_tz(s, tz), _as_tz(e, tz), days, day_set,
                               tz, day_start, day_end, busy)
        else:  # all-day DATE (or date-like): blocks whole window that day
            cur = s if isinstance(s, date) else None
            end = e if isinstance(e, date) else cur
            if cur is None:
                continue
            d = cur
            while d < end if end and end > cur else d <= cur:
                if d in day_set:
                    busy[d].append((datetime.combine(d, day_start, tz),
                                    datetime.combine(d, day_end, tz)))
                d += timedelta(days=1)
    for d in busy:
        busy[d] = merge_intervals(busy[d])
    return busy


def find_slots(days: list[date], busy: dict[date, list[tuple[datetime, datetime]]],
               tz: ZoneInfo, day_start: time, day_end: time,
               duration_min: int, step_min: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    dur = timedelta(minutes=duration_min)
    for d in days:
        w0 = datetime.combine(d, day_start, tz)
        w1 = datetime.combine(d, day_end, tz)
        blocks = busy.get(d, [])
        opts: list[str] = []
        t = w0
        while t + dur <= w1:
            cand_end = t + dur
            if not any(t < b1 and cand_end > b0 for b0, b1 in blocks):
                opts.append(f"{t.strftime('%H:%M')}-{cand_end.strftime('%H:%M')}")
            t += timedelta(minutes=step_min)
        out[d.isoformat()] = opts
    return out


def resolve_calendars(args: argparse.Namespace) -> list[str]:
    """Member calendars from --calendar (repeatable), legacy --calendar-code, or env."""
    if args.calendars:
        return args.calendars
    if args.source == "google":
        env = os.environ.get("GOOGLE_CALENDARS", "")
        cals = [c.strip() for c in env.split(",") if c.strip()]
        return cals or ["primary"]
    if args.calendar_code:
        return [args.calendar_code]
    return []


def main() -> int:
    args = parse_args()
    tz = ZoneInfo(args.timezone)
    day_start = time(*map(int, args.day_start.split(":")))
    day_end = time(*map(int, args.day_end.split(":")))
    days = resolve_week(args.week_start, tz)

    calendars = resolve_calendars(args)
    busy: dict[date, list[tuple[datetime, datetime]]]
    tmp = None
    if args.ics:
        busy = load_busy(args.ics, tz, days, day_start, day_end)
    elif args.source == "google":
        from providers import google_busy
        busy = google_busy(calendars, days, tz, day_start, day_end,
                           client_secrets=args.client_secrets, token_file=args.token_file)
    else:
        if not calendars:
            print("Set TIMETREE_CALENDAR_CODE or pass --calendar / --ics.", file=sys.stderr)
            return 2
        tmp = tempfile.NamedTemporaryFile(suffix=".ics", delete=False)
        tmp.close()
        export_ics(calendars[0], tmp.name, public=args.public_calendar)
        try:
            busy = load_busy(tmp.name, tz, days, day_start, day_end)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    slots = find_slots(days, busy, tz, day_start, day_end, args.duration, args.step)

    if args.as_json:
        print(json.dumps({"source": args.source, "calendars": calendars,
                          "week": [d.isoformat() for d in days], "timezone": args.timezone,
                          "window": f"{args.day_start}-{args.day_end}",
                          "duration_min": args.duration, "slots": slots}, indent=2))
    else:
        who = f" [{', '.join(calendars)}]" if calendars else ""
        print(f"Week of {days[0]} - {days[-1]} ({args.timezone}, "
              f"{args.day_start}-{args.day_end}, {args.duration}min){who}")
        for d in days:
            opts = slots[d.isoformat()]
            label = d.strftime("%a %Y-%m-%d")
            print(f"{label}: " + (", ".join(opts) if opts else f"no {args.duration}min slot"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
