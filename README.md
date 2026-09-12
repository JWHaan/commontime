# TimeTree Meeting Slot Finder

Find 2-hour meeting slots where everyone is free, from a TimeTree calendar.
Defaults: weekdays Mon–Fri, hard window 08:00–20:00, Asia/Singapore. Free = no overlapping event.

> TimeTree killed its official API (Dec 2023). This uses the community
> [`timetree-exporter`](https://github.com/eoleedi/TimeTree-Exporter) (unofficial
> web scraping) to export to `.ics`, then finds free windows locally.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # fill in, never commit it
export $(cat .env | xargs)  # or use direnv
```

Env vars:

| Var | Required | What |
|---|---|---|
| `TIMETREE_EMAIL` / `TIMETREE_PASSWORD` | yes (private cal) | TimeTree login |
| `TIMETREE_CALENDAR_CODE` | yes (unless `--ics`) | Code in the calendar page URL, or the code printed when running `timetree-exporter` without `-c` |
| `SLOT_TIMEZONE` | no | Default `Asia/Singapore` |
| `SLOT_DAY_START` / `SLOT_DAY_END` | no | Default `08:00` / `20:00` |
| `SLOT_DURATION_MIN` | no | Default `120` |

Share link: yes — if TimeTree's share gives you a public URL
(`timetreeapp.com/public_calendars/...`), use that id with `--public-calendar`
(no login needed). For a private calendar page URL, the code in the URL is
`TIMETREE_CALENDAR_CODE`.

## Use

```bash
# Next Mon–Fri, 2h slots, 8am–8pm SGT
python timetree_slots.py

# A specific week (must be a Monday)
python timetree_slots.py --week-start 2026-09-14

# JSON output / different length / public calendar / cached ics
python timetree_slots.py --json
python timetree_slots.py --duration 60 --step 15
python timetree_slots.py --public-calendar --calendar-code <public_id>
python timetree_slots.py --ics path/to/calendar.ics
```

Example output:

```
Week of 2026-09-14 - 2026-09-18 (Asia/Singapore, 08:00-20:00, 120min)
Mon 2026-09-14: 08:00-10:00
Tue 2026-09-15: 08:00-10:00
Wed 2026-09-16: no 2h slot
...
```

## Notes / limits

- Unofficial API: can break or rate-limit if run too often. Once a week is fine.
- Any event counts as busy; all-day events block the whole 8am–8pm window.
- Times are candidate starts every 30 min by default (`--step`).
