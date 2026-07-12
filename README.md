# Cadence — Team Scheduling

[![CI](https://github.com/JamesVillarosa/recurrence-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/JamesVillarosa/recurrence-engine/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%20%E2%80%93%203.13-blue)
![Coverage](https://img.shields.io/badge/engine%20branch%20coverage-100%25-brightgreen)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**▶ Live demo: https://cadence-5vxj.onrender.com** &nbsp;·&nbsp; [API docs](https://cadence-5vxj.onrender.com/docs)

> Hosted on Render's free tier — the first request after idle may take ~50s to wake.

**Cadence** is a team scheduling workspace for recurring and one-off tasks — a
ClickUp-style task calendar with a Slack-style chat beside it. Its scheduling
core is a **recurrence engine**: a deterministic function that expands a
**recurrence rule** into concrete, ordered, de-duplicated **task occurrences**
within a query window — the piece of a scheduler where correctness is hardest
and matters most. That engine is the focus of this repository, built and tested
to production standard; the workspace UI shows how it fits into the product.

```python
from datetime import date
from engine import Rule, Weekly, Count, get_occurrences

rule = Rule(
    start=date(2026, 1, 6),                              # a Tuesday
    pattern=Weekly(frozenset({0, 2, 4})),               # Mon / Wed / Fri
    end=Count(5),                                        # first 5 occurrences
)
get_occurrences(rule, date(2026, 1, 1), date(2026, 12, 31))
# [2026-01-07, 2026-01-09, 2026-01-12, 2026-01-14, 2026-01-16]
#   Wed         Fri         Mon         Wed         Fri
```

The start date is a Tuesday, which is **not** in the pattern — the first
occurrence is correctly the next matching weekday (Wednesday), not the start.

---

## What's in the box

| Layer | Path | What it is |
|-------|------|-----------|
| **Engine** | [`engine/`](engine/) | Pure, dependency-free rule expansion. The product. |
| **Tests** | [`tests/`](tests/) | Unit + property-based suite, 100% engine branch coverage. |
| **API** | [`api/`](api/) | Thin FastAPI layer: validation, rate limiting, ETag caching. |
| **Workspace** | [`web/`](web/) | Cadence UI — scheduler (rule builder + calendar) in a ClickUp/Slack-style shell. |
| **Automation** | [`automation/`](automation/) | n8n workflows: a daily ops brief to Slack + idempotent restock tasks into Cadence. |
| **CI/CD** | [`.github/`](.github/), [`render.yaml`](render.yaml), [`vercel.json`](vercel.json), [`Dockerfile`](Dockerfile) | Test matrix and one-click deploys. |

## Supported rules

- **Patterns:** one-off · daily every *N* days · weekly on chosen weekdays every
  *N* weeks · monthly on a day-of-month every *N* months.
- **End conditions:** never · until a date (inclusive) · after *K* occurrences.

---

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[api,dev]"

pytest --cov=engine --cov-report=term-missing        # run the suite
uvicorn api:app --reload                              # serve everything at :8000
```

One process serves both the API and the playground. Open:

- <http://127.0.0.1:8000/> — the interactive playground
- <http://127.0.0.1:8000/docs> — the OpenAPI docs
- `POST http://127.0.0.1:8000/v1/occurrences` — the API

> If port 8000 is unavailable, pick another: `uvicorn api:app --port 8123`.

---

## Design decisions

Every one of these is a deliberate, documented choice — the behaviour is pinned
down by a named test.

### Month-end handling — the headline case

**"Monthly on the 31st" in February** is resolved by an explicit, configurable
policy on the pattern:

- **`CLAMP`** (default): fall back to the last valid day — Feb 28 (or 29 in a
  leap year), Apr 30, and so on. Rationale: in a task planner a "month-end"
  task must **never silently vanish**; clamping is the safe, least-surprising
  behaviour for people running a business off the schedule.
- **`SKIP`**: omit months that lack the day, matching iCalendar `RRULE`
  `BYMONTHDAY` semantics, for callers that need strict calendar behaviour.

Both are tested across February and leap years
([`tests/test_monthly.py`](tests/test_monthly.py)).

### End conditions are exact — and counted from the start

`Count(K)` always means "the K occurrences the rule produces from its start
date." A query window that opens mid-sequence returns the occurrences that fall
inside it, but can never make the rule leak a K+1-th. *Where you look does not
change what exists.* `Until(d)` is inclusive of `d`. See
[`tests/test_end_conditions.py`](tests/test_end_conditions.py).

### A start date that doesn't match the pattern

The start **anchors** the cycle; the first occurrence is the first pattern match
at or after the start. Weekly Mon/Wed/Fri starting on a Tuesday begins on
Wednesday; monthly-on-the-15th starting on the 20th begins the following month.

### Inclusive, order-guaranteed window

`get_occurrences` includes both window bounds, returns dates in strictly
ascending order, and is de-duplicated by construction. An empty or reversed
window returns `[]`.

### Date-only core

The engine speaks `datetime.date`, never `datetime` — no time-of-day, no
timezone. Recurrence is calendar arithmetic; entangling it with timezones is how
DST bugs get in. Localisation is a boundary concern (see below), which keeps the
core exhaustively testable.

---

## How correctness is verified

> Luke's brief: *"whether you verify correctness with tests instead of assuming
> it."* This is the part that matters.

Two complementary layers, gated at **100% branch coverage** of the engine in CI:

1. **Example tests** pin exact expected dates for every pattern × end condition,
   month-end policy across February and leap years, count-from-start exactness,
   and non-matching start dates.
2. **Property-based tests** ([Hypothesis](https://hypothesis.readthedocs.io/)) assert
   invariants over thousands of randomised rules and windows:
   - output is strictly ascending, unique, and within the window;
   - `Count(K)` is never exceeded, for any window;
   - **window-split invariance** — expanding `[a, b]` equals expanding `[a, m]`
     concatenated with `[m+1, b]` for any split point. This single property
     rules out an entire family of off-by-one and re-anchoring bugs.

```bash
pytest -q                       # 85 tests
pytest --cov=engine             # enforces 100% branch coverage
ruff check . && mypy engine api # lint + strict types
```

---

## HTTP API

`POST /v1/occurrences`

```json
{
  "rule": {
    "start": "2026-01-05",
    "pattern": { "type": "weekly", "weekdays": [0, 2, 4], "interval": 1 },
    "end": { "type": "count", "count": 5 }
  },
  "window_start": "2026-01-01",
  "window_end": "2026-12-31"
}
```

Returns `{ "occurrences": ["2026-01-05", ...], "count": 5 }`. Responses carry a
strong `ETag` and `Cache-Control` because expansion is deterministic; invalid
input is rejected with a structured `422`. Per-client rate limiting is applied
via slowapi. `GET /healthz` is the liveness probe.

---

## Automation layer

An automation can create tasks in Cadence over HTTP. The reference setup is an
[n8n](https://n8n.io/) workflow that runs daily, reads e-commerce inventory,
computes metrics, has Claude write a plain-English brief to Slack, and posts
low-stock items to Cadence so restock tasks are created automatically. Both
halves live in this repo: the ingress endpoint (in [`api/`](api/)) and the
importable workflows (in [`automation/`](automation/)).

### Endpoint contract — `POST /api/webhooks/restock-task`

| | |
|---|---|
| **Method** | `POST` |
| **Headers** | `x-webhook-secret: <CADENCE_WEBHOOK_SECRET>` · `content-type: application/json` |
| **Body** | `{ "title": string, "due_date": "YYYY-MM-DD", "notes": string, "source_key": string? }` |

`title` (1–200 chars after trimming) and `due_date` are required; `notes`
(≤2000 chars) defaults to `""`; `source_key` (≤200 chars) is the idempotency key
and, when omitted, is derived from the title. Unknown fields are rejected.

| Status | When | Body |
|--------|------|------|
| **201 Created** | A new task was created | the task, `"deduplicated": false` |
| **200 OK** | An open task with the same `source_key` already exists | the existing task, `"deduplicated": true` |
| **400 Bad Request** | Validation failed | `{ "detail": "<field>: <reason>" }` — names the offending field |
| **401 Unauthorized** | `x-webhook-secret` missing or wrong | `{ "detail": ... }` |
| **503 Service Unavailable** | Server has no `CADENCE_WEBHOOK_SECRET` configured | fails closed, never open |

The secret is compared in constant time. Created tasks carry `source: "automation"`
and show an **Automated** badge in the workspace UI. Two small read/update routes —
`GET /api/tasks` and `POST /api/tasks/{id}/complete` — back that UI.

### Why the endpoint is idempotent

The workflow runs **every day**, and n8n delivers HTTP requests with
**at-least-once** semantics (a node that retries on failure can send the same
request more than once). So if a product stays below its reorder point for a
week, this endpoint receives the *same* restock request many times. Without
idempotency that means seven duplicate "Restock: Widget A" tasks — noise that
buries the one task a human needs to action.

Idempotency is enforced **in the database**, not in application code, by a
partial unique index over `source_key` restricted to *open* (incomplete) tasks:

```sql
CREATE UNIQUE INDEX ux_tasks_open_source_key ON tasks (source_key)
    WHERE completed_at IS NULL AND source_key IS NOT NULL;
```

- A repeat delivery while a task is still open cannot insert a second row — the
  losing write hits the index and is resolved into a `200 deduplicated` response.
  This is **race-safe**: two concurrent identical deliveries can't both win.
- Once the task is **completed** it leaves the index's scope, so the *next*
  low-stock event is free to create a fresh task. Completing something doesn't
  mean it can never recur — it means the recurrence starts a new task.

### End-to-end flow

```mermaid
flowchart TD
    T1[Manual Trigger] --> H
    T2[Schedule Trigger<br/>08:00 Europe/Istanbul] --> H
    H[HTTP: fetch inventory CSV] --> C[Code: compute metrics & flags<br/>revenue · margin · top 3 · low-stock]
    C --> AI[HTTP: Claude writes brief<br/>from the computed numbers]
    AI --> P[Code: prepend hard numbers] --> S1[HTTP: post brief to Slack]
    C --> R[Code: one item per low-stock product]
    R --> W[HTTP: POST /api/webhooks/restock-task<br/>x-webhook-secret]
    W --> DB[(Cadence tasks<br/>idempotent by source_key)]
    C -. on any failure .-> E
    AI -. on any failure .-> E
    W -. on any failure .-> E[Error Trigger workflow]
    E --> S2[HTTP: post alert to Slack]
```

### Importing the workflows

1. In n8n: **Workflows → Import from File** → select
   [`automation/error-handler.json`](automation/error-handler.json), then
   [`automation/daily-ops-brief.json`](automation/daily-ops-brief.json).
2. In the daily workflow, replace the clearly-marked placeholders:

   | Placeholder | Set to |
   |---|---|
   | `YOUR_SHEET_ID` | Your Google Sheet ID (published so `/gviz/tq?tqx=out:csv` works). Columns: `product_name, units_sold_yesterday, unit_price, unit_cost, stock_level, reorder_point`. |
   | `YOUR_ANTHROPIC_API_KEY` | Your Anthropic API key (better: move it into an n8n credential). |
   | `YOUR_SLACK_WEBHOOK_URL_DAILY_OPS` | Slack Incoming Webhook for the brief channel. |
   | `YOUR_SLACK_WEBHOOK_URL_ALERTS` | Slack Incoming Webhook for the alerts channel. |
   | `YOUR_CADENCE_URL` | Your deployed base URL, e.g. `https://cadence-5vxj.onrender.com`. |
   | `YOUR_CADENCE_WEBHOOK_SECRET` | Same value as the server's `CADENCE_WEBHOOK_SECRET`. |

3. **Settings → Error Workflow** on the daily workflow → select **Cadence — Error
   Handler**, so failures are announced in Slack rather than failing silently.
4. Set `CADENCE_WEBHOOK_SECRET` on the server (see [`.env.example`](.env.example);
   on Render, set it in the dashboard). Use **Execute Workflow** for the live demo,
   or leave the schedule enabled for the daily 08:00 run.

---

## Extending it

The architecture is shaped for the trickier rules Luke mentioned:

- **"2nd Tuesday of each month"** is a new `MonthlyByWeekday(ordinal, weekday)`
  pattern with its own generator (compute the *n*-th weekday of the month, or
  the last when `ordinal == -1`). It slots in beside the existing generators in
  [`engine/expand.py`](engine/expand.py) — the dispatch, end-condition handling,
  and windowing are already generic over the pattern.
- **Timezones / DST.** The core stays date-only. At the boundary you attach a
  time-of-day and an IANA timezone and localise each date — e.g. `9:00 America/
  New_York`. Because occurrences are calendar dates, a rule fires at 9 AM local
  on both sides of a DST change; you never get a "10 AM after the clocks
  shifted" bug. If a wall-clock time lands in a spring-forward gap, that
  resolution is an explicit boundary decision, made once, in one place — not
  smeared through the recurrence math.

See [`DESIGN.md`](DESIGN.md) for the full rationale.

---

## Deployment

One service serves everything — the API **and** the playground it hosts at `/`
— so a single deploy gives you one working URL. Pick either target:

[![Deploy to Render](https://img.shields.io/badge/Deploy%20to-Render-46E3B7?logo=render&logoColor=white)](https://render.com/deploy?repo=https://github.com/JamesVillarosa/recurrence-engine)
[![Deploy with Vercel](https://img.shields.io/badge/Deploy%20with-Vercel-000000?logo=vercel&logoColor=white)](https://vercel.com/new/clone?repository-url=https://github.com/JamesVillarosa/recurrence-engine)

- **Render (recommended):** the [`render.yaml`](render.yaml) Blueprint configures
  build, start command, and `/healthz` check automatically. Click the button,
  sign in, confirm — the live URL serves the playground and the API together.
- **Vercel:** [`vercel.json`](vercel.json) routes all traffic to the FastAPI
  app running as a Python serverless function (entry [`api/index.py`](api/index.py)).
- **Docker (anywhere):** [`Dockerfile`](Dockerfile) builds a portable non-root
  image: `docker build -t recurrence-engine . && docker run -p 8000:8000 recurrence-engine`,
  then open <http://localhost:8000>.

Once deployed, the site root is the interactive playground; `/docs` is the
OpenAPI UI and `/v1/occurrences` is the API.

## License

MIT — see [`LICENSE`](LICENSE).
