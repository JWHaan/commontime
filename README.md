# CommonTime

Find the time everyone is free — shared meeting slots from a TimeTree calendar, for humans and AI agents.

Defaults: weekdays Mon–Fri, hard window 08:00–20:00, Asia/Singapore. A time counts as
free only if **no event** overlaps it. Three ways to use it: CLI, MCP server, or scheduled digest.

> TimeTree shut down its official API in December 2023. CommonTime exports via the
> community [`timetree-exporter`](https://github.com/eoleedi/TimeTree-Exporter)
> (unofficial web API) and computes free windows locally.

## Quickstart

```bash
pip install commontime   # or: pip install -e ".[dev]" from source
cp .env.example .env   # fill in — never commit .env
set -a; source .env; set +a

commontime                     # next Mon–Fri, 2h slots, 8am–8pm
commontime --week-start 2026-09-14 --json
```

Example output:

```
Week of 2026-09-14 - 2026-09-18 (Asia/Singapore, 08:00-20:00, 120min)
Mon 2026-09-14: 08:00-10:00
Tue 2026-09-15: 08:00-10:00
Wed 2026-09-16: no 2h slot
```

## For agents (MCP)

Any MCP-compatible agent (Claude, Hermes, …) gets two tools over stdio:

| Tool | What |
|---|---|
| `find_free_slots` | Free meeting windows for a week (same defaults/flags as the CLI) |
| `list_calendars` | Discover calendar names + codes for the login |

Client config:

```json
{ "mcpServers": { "commontime": {
    "command": "commontime-mcp",
    "env": {
      "TIMETREE_EMAIL": "you@example.com",
      "TIMETREE_PASSWORD": "secret",
      "TIMETREE_CALENDAR_CODE": "xxxxxx"
    } } } }
```

## Configuration

| Variable | Required | Purpose |
|---|---|---|
| `TIMETREE_EMAIL` / `TIMETREE_PASSWORD` | yes (private calendar) | TimeTree login |
| `TIMETREE_CALENDAR_CODE` | yes (unless `--ics`) | Code from the calendar page URL — or the code printed when running `timetree-exporter` without `-c` |
| `SLOT_TIMEZONE` / `SLOT_DAY_START` / `SLOT_DAY_END` / `SLOT_DURATION_MIN` | no | Defaults `Asia/Singapore`, `08:00`, `20:00`, `120` |

Public calendars need no login: use the id from the share URL with `--public-calendar`
(or `public_calendar: true` on the MCP tool).

CLI flags: `--week-start YYYY-MM-DD` (a Monday), `--duration`, `--step`,
`--timezone`, `--day-start/--day-end`, `--ics` (reuse an exported file, no login),
`--json`.

## Weekly digest

Run it on a schedule and have the result messaged to you — e.g. cron:

```cron
0 21 * * SUN TIMETREE_EMAIL=... TIMETREE_PASSWORD=... TIMETREE_CALENDAR_CODE=... commontime
```

## Limits

- Unofficial API: may break or rate-limit if polled aggressively. Weekly use is fine.
- Any event counts as busy; all-day events block the whole day window.
- Candidate starts step every 30 min by default (`--step`).

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

MIT licensed. Contributions welcome.
