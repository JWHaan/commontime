"""Unit tests for commontime (synthetic ICS, no network or credentials)."""
import json
import subprocess
import sys
from datetime import date as ddate
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from icalendar import Calendar, Event

from commontime import find_slots, load_busy

SGT = ZoneInfo("Asia/Singapore")
SCRIPT = Path(__file__).resolve().parent.parent / "commontime.py"
DAYS = [ddate(2026, 9, 14 + i) for i in range(5)]  # Mon-Fri


def make_ics(path, events):
    cal = Calendar()
    cal.add("prodid", "test")
    cal.add("version", "2.0")
    for i, (s, e) in enumerate(events):
        ev = Event()
        ev.add("uid", f"t{i}")
        ev.add("summary", f"ev{i}")
        ev.add("dtstart", s)
        ev.add("dtend", e)
        cal.add_component(ev)
    path.write_bytes(cal.to_ical())
    return str(path)


def dt(d, h, m=0):
    return datetime(2026, 9, d, h, m, tzinfo=SGT)


def busy_for(events):
    return load_busy(events, SGT, DAYS, time(8, 0), time(20, 0))


def test_empty_week_has_full_candidates(tmp_path):
    slots = find_slots(DAYS, busy_for(make_ics(tmp_path / "c.ics", [])),
                       SGT, time(8, 0), time(20, 0), 120, 30)
    assert slots["2026-09-14"][0] == "08:00-10:00"
    assert slots["2026-09-14"][-1] == "18:00-20:00"
    assert len(slots["2026-09-14"]) == 21


def test_busy_from_10am_leaves_single_slot(tmp_path):
    slots = find_slots(DAYS, busy_for(make_ics(tmp_path / "c.ics", [(dt(14, 10), dt(14, 22))])),
                       SGT, time(8, 0), time(20, 0), 120, 30)
    assert slots["2026-09-14"] == ["08:00-10:00"]


def test_all_day_event_blocks_whole_day(tmp_path):
    slots = find_slots(DAYS, busy_for(make_ics(tmp_path / "c.ics", [(ddate(2026, 9, 15), ddate(2026, 9, 16))])),
                       SGT, time(8, 0), time(20, 0), 120, 30)
    assert slots["2026-09-15"] == []


def test_short_evening_gap_yields_no_slot(tmp_path):
    slots = find_slots(DAYS, busy_for(make_ics(tmp_path / "c.ics", [(dt(16, 7), dt(16, 19))])),
                       SGT, time(8, 0), time(20, 0), 120, 30)
    assert slots["2026-09-16"] == []


def test_multiday_event_split_across_days(tmp_path):
    slots = find_slots(DAYS, busy_for(make_ics(tmp_path / "c.ics", [(dt(17, 15), dt(18, 9))])),
                       SGT, time(8, 0), time(20, 0), 120, 30)
    assert slots["2026-09-17"][-1] == "13:00-15:00"
    assert slots["2026-09-18"][0] == "09:00-11:00"


def test_cli_text_output(tmp_path):
    ics = make_ics(tmp_path / "c.ics", [(dt(14, 10), dt(14, 22))])
    r = subprocess.run([sys.executable, str(SCRIPT), "--ics", ics, "--week-start", "2026-09-14"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "Mon 2026-09-14: 08:00-10:00" in r.stdout


def test_cli_json_output(tmp_path):
    ics = make_ics(tmp_path / "c.ics", [])
    r = subprocess.run([sys.executable, str(SCRIPT), "--ics", ics,
                        "--week-start", "2026-09-14", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert json.loads(r.stdout)["week"][0] == "2026-09-14"


def test_cli_rejects_non_monday(tmp_path):
    ics = make_ics(tmp_path / "c.ics", [])
    r = subprocess.run([sys.executable, str(SCRIPT), "--ics", ics, "--week-start", "2026-09-15"],
                       capture_output=True, text=True)
    assert r.returncode != 0


def test_env_example_has_no_secrets():
    text = (Path(__file__).resolve().parent.parent / ".env.example").read_text()
    assert "TIMETREE_EMAIL" in text and "TIMETREE_CALENDAR_CODE" in text
