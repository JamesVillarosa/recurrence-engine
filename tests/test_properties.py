"""Property-based tests: invariants that must hold for *every* rule and window.

Example-based tests prove specific cases; these prove classes of cases.
Hypothesis searches thousands of randomised rules and windows for a
counterexample to each invariant. The window-split invariance property in
particular kills a whole family of off-by-one and re-anchoring bugs.
"""

from __future__ import annotations

from datetime import date, timedelta
from itertools import pairwise

from engine import (
    Count,
    Daily,
    EndCondition,
    MonthEndPolicy,
    MonthlyByDay,
    Never,
    OneOff,
    Pattern,
    Rule,
    Until,
    Weekly,
    get_occurrences,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Bound the calendar space so windows stay small enough to expand quickly while
# still exercising leap years, month-ends, and multi-year spans.
MIN_DATE = date(2020, 1, 1)
MAX_DATE = date(2030, 12, 31)

dates = st.dates(min_value=MIN_DATE, max_value=MAX_DATE)


@st.composite
def patterns(draw: st.DrawFn) -> Pattern:
    kind = draw(st.sampled_from(["oneoff", "daily", "weekly", "monthly"]))
    if kind == "oneoff":
        return OneOff()
    if kind == "daily":
        return Daily(draw(st.integers(min_value=1, max_value=30)))
    if kind == "weekly":
        weekdays = draw(st.frozensets(st.integers(min_value=0, max_value=6), min_size=1))
        return Weekly(weekdays, draw(st.integers(min_value=1, max_value=6)))
    return MonthlyByDay(
        draw(st.integers(min_value=1, max_value=31)),
        draw(st.integers(min_value=1, max_value=6)),
        draw(st.sampled_from(list(MonthEndPolicy))),
    )


@st.composite
def end_conditions(draw: st.DrawFn) -> EndCondition:
    kind = draw(st.sampled_from(["never", "until", "count"]))
    if kind == "never":
        return Never()
    if kind == "until":
        return Until(draw(dates))
    return Count(draw(st.integers(min_value=1, max_value=50)))


@st.composite
def rules(draw: st.DrawFn) -> Rule:
    return Rule(draw(dates), draw(patterns()), draw(end_conditions()))


@st.composite
def rules_and_windows(draw: st.DrawFn) -> tuple[Rule, date, date]:
    rule = draw(rules())
    a = draw(dates)
    b = draw(dates)
    window_start, window_end = min(a, b), max(a, b)
    return rule, window_start, window_end


slow_ok = settings(max_examples=400, suppress_health_check=[HealthCheck.too_slow], deadline=None)


@slow_ok
@given(rules_and_windows())
def test_output_is_strictly_ascending(case: tuple[Rule, date, date]) -> None:
    rule, start, end = case
    result = get_occurrences(rule, start, end)
    assert all(a < b for a, b in pairwise(result))


@slow_ok
@given(rules_and_windows())
def test_output_is_unique(case: tuple[Rule, date, date]) -> None:
    rule, start, end = case
    result = get_occurrences(rule, start, end)
    assert len(result) == len(set(result))


@slow_ok
@given(rules_and_windows())
def test_output_lies_within_the_window(case: tuple[Rule, date, date]) -> None:
    rule, start, end = case
    for occ in get_occurrences(rule, start, end):
        assert start <= occ <= end


@slow_ok
@given(rules_and_windows())
def test_no_occurrence_precedes_the_rule_start(case: tuple[Rule, date, date]) -> None:
    rule, start, end = case
    for occ in get_occurrences(rule, start, end):
        assert occ >= rule.start


@slow_ok
@given(rules_and_windows())
def test_count_is_never_exceeded(case: tuple[Rule, date, date]) -> None:
    rule, _start, _end = case
    if isinstance(rule.end, Count):
        # Query the widest possible window so nothing is hidden by clipping.
        full = get_occurrences(rule, MIN_DATE, MAX_DATE)
        assert len(full) <= rule.end.count


@slow_ok
@given(rules_and_windows(), st.data())
def test_window_split_invariance(case: tuple[Rule, date, date], data: st.DataObject) -> None:
    # Splitting the query window at any interior point and concatenating the
    # two halves must reproduce the single-window result exactly. This is the
    # strongest guarantee that occurrences are a property of the rule alone,
    # independent of how the window is chosen.
    rule, start, end = case
    whole = get_occurrences(rule, start, end)
    if start == end:
        return
    split = data.draw(st.dates(min_value=start, max_value=end - timedelta(days=1)))
    left = get_occurrences(rule, start, split)
    right = get_occurrences(rule, split + timedelta(days=1), end)
    assert left + right == whole
