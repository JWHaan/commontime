"""Tests for the Google provider (stubbed service — no network or credentials)."""
from datetime import date as ddate
from datetime import time
from zoneinfo import ZoneInfo

from commontime import find_slots
from providers import google_busy

SGT = ZoneInfo("Asia/Singapore")
DAYS = [ddate(2026, 9, 14 + i) for i in range(5)]


class _Query:
    def __init__(self, resp):
        self.resp = resp

    def execute(self):
        return self.resp


class _FreeBusy:
    def __init__(self, resp):
        self.resp = resp
        self.seen_body = None

    def query(self, body):
        self.seen_body = body
        return _Query(self.resp)


class _StubService:
    def __init__(self, resp):
        self._fb = _FreeBusy(resp)

    def freebusy(self):
        return self._fb


def _busy(start, end):
    return {"start": f"2026-09-14T{start}:00+08:00", "end": f"2026-09-14T{end}:00+08:00"}


def test_union_across_members():
    """A slot must be free on EVERY member calendar."""
    resp = {"calendars": {
        "alice": {"busy": [_busy("09:00", "11:00")]},
        "bob": {"busy": [_busy("10:00", "12:00")]},
    }}
    svc = _StubService(resp)
    busy = google_busy(["alice", "bob"], DAYS, SGT, time(8, 0), time(20, 0), service=svc)
    merged = busy[ddate(2026, 9, 14)]
    assert len(merged) == 1  # 09-11 + 10-12 merged to 09-12
    slots = find_slots(DAYS, busy, SGT, time(8, 0), time(20, 0), 120, 30)
    mon = slots["2026-09-14"]
    assert "08:00-10:00" not in mon  # bob? no—alice busy 9-11 blocks it
    assert "12:00-14:00" in mon
    # other days untouched
    assert slots["2026-09-15"][0] == "08:00-10:00"


def test_freebusy_query_window_and_members():
    resp = {"calendars": {"a": {"busy": []}}}
    svc = _StubService(resp)
    google_busy(["a", "b"], DAYS, SGT, time(8, 0), time(20, 0), service=svc)
    body = svc._fb.seen_body
    assert body is not None
    assert body["timeMin"].startswith("2026-09-14T00:00")
    assert body["timeMax"].startswith("2026-09-19T00:00")
    assert body["items"] == [{"id": "a"}, {"id": "b"}]


def test_out_of_window_busy_ignored():
    resp = {"calendars": {"a": {"busy": [_busy("21:00", "23:00")]}}}
    svc = _StubService(resp)
    busy = google_busy(["a"], DAYS, SGT, time(8, 0), time(20, 0), service=svc)
    assert busy.get(ddate(2026, 9, 14), []) == []
