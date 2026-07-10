# Design notes

Extended rationale behind the engine. The README has the summary; this is the
"why", including the trade-offs and the failure modes I deliberately guarded
against.

## 1. A pure, date-only core

The engine is a pure function: `(rule, window) -> list[date]`. No I/O, no clock,
no globals, no mutation. Three consequences fall out for free:

- **Testability.** The same inputs always yield the same output, so every test
  is a plain equality assertion and property-based testing is trivial.
- **Cacheability.** Determinism is what lets the API attach a strong `ETag` and
  let CDNs cache responses indefinitely.
- **No timezone/DST bugs in the hard part.** Recurrence is calendar math. A
  "daily at 09:00" task is really "each of these dates, interpreted at 09:00 in
  some timezone." Keeping the dates separate from the localisation means the
  DST edge cases live in one small, obvious place at the boundary instead of
  being threaded through every pattern.

## 2. Occurrences are a property of the rule, not the window

The single most important correctness principle. `Count(K)` is measured from the
rule's start; `Until(d)` bounds the rule's own timeline. The query window only
*filters* what the rule already produces — it can never change it.

The **window-split invariance** property test is the formal statement of this:
for any split point `m`,

```
get_occurrences(rule, a, b) == get_occurrences(rule, a, m) + get_occurrences(rule, m+1, b)
```

If any pattern re-anchored itself to the window start, or counted from the
window instead of the rule start, this property would fail. It holds across
thousands of randomised cases.

## 3. Generators + a strict ordering invariant

Each pattern is a generator yielding dates in strictly ascending order from the
start. `get_occurrences` consumes the generator, applies the end condition, and
stops at the first date past the window end. Because the sequence is monotonic,
that early stop is safe and the whole thing is `O(occurrences in window)` — no
unbounded materialisation, no infinite loops even for `Never` rules (the window
end is always finite and always terminates the walk).

## 4. Month-end policy

| Policy | "31st" in Feb 2026 | Use it when |
|--------|--------------------|-------------|
| `CLAMP` (default) | Feb 28 | A task must fire every month, month-end included. |
| `SKIP` | (no occurrence) | You need strict `RRULE`/`BYMONTHDAY` semantics. |

`CLAMP` is the default because dropping a month-end task silently is the more
dangerous failure for the users this is built for. The choice is explicit and
per-rule, not a global toggle, so two rules in the same system can differ.

Leap years are covered by construction: clamping uses `calendar.monthrange`, so
Feb 29 appears in leap years and Feb 28 otherwise.

## 5. Weekly interval anchoring

"Every 2 weeks on Monday" needs an anchor, or "which weeks count?" is undefined.
The anchor is the Monday of the ISO week containing the rule's start. Interval
`N` then selects every `N`-th week from that anchor. Weekdays within a selected
week are emitted in ascending order; any that fall before the start date are
skipped, so a mid-week start never produces a phantom earlier occurrence.

## 6. Validation at the edges

Invalid rules cannot be constructed: dataclass `__post_init__` rejects
non-positive intervals, empty weekday sets, out-of-range weekdays/days, and
non-positive counts. The API mirrors these as Pydantic constraints, so malformed
requests fail with a structured `422` before touching the engine, and the engine
raise is a defensive backstop.

## 7. What I deliberately left out

- **No persistence / scheduler.** The brief is the expansion problem. A real
  scheduler would store rules in Postgres, materialise upcoming occurrences via
  a worker, and dedupe with an idempotency key `(rule_id, date)`. That's a
  storage and orchestration problem layered *on top of* this function, not a
  change to it — keeping them separate is the point.
- **No `datetime`/timezone in the core.** Covered above; it's a boundary
  concern.

## 8. Extension sketch: "2nd Tuesday of each month"

Add a pattern and a generator; nothing else changes.

```python
@dataclass(frozen=True, slots=True)
class MonthlyByWeekday:
    ordinal: int      # 1..4, or -1 for "last"
    weekday: int      # Mon=0 .. Sun=6

def _generate_monthly_by_weekday(start, ordinal, weekday, interval):
    # For each selected month, find the ordinal-th `weekday` (or the last when
    # ordinal == -1); yield it if >= start. Months where the ordinal doesn't
    # exist (e.g. a 5th Tuesday) are simply skipped.
    ...
```

The dispatcher in `expand.py`, the end-condition logic, and the windowing are
all generic over the pattern, so only the generator is new.
