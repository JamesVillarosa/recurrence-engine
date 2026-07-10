"""End conditions must be exact: "after K" and "until D" both pinned down.

The subtle, high-value property here: the count is measured from the rule's
start, not from the query window. A window that begins mid-sequence must not
let the rule "leak" extra occurrences beyond its K-th.
"""

from __future__ import annotations

from datetime import date

from engine import Count, Daily, MonthlyByDay, Never, Rule, Until, get_occurrences


def test_count_yields_exactly_k_occurrences() -> None:
    rule = Rule(date(2026, 1, 1), Daily(1), Count(5))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 12, 31))
    assert result == [date(2026, 1, d) for d in range(1, 6)]


def test_count_is_measured_from_start_not_from_window() -> None:
    # Rule produces exactly 5 daily occurrences: Jan 1..5. A window that opens
    # on Jan 3 must return Jan 3,4,5 only — never Jan 6,7 (which do not exist).
    rule = Rule(date(2026, 1, 1), Daily(1), Count(5))
    result = get_occurrences(rule, date(2026, 1, 3), date(2026, 12, 31))
    assert result == [date(2026, 1, 3), date(2026, 1, 4), date(2026, 1, 5)]


def test_count_of_one_is_a_single_occurrence() -> None:
    rule = Rule(date(2026, 1, 1), Daily(1), Count(1))
    assert get_occurrences(rule, date(2026, 1, 1), date(2026, 12, 31)) == [date(2026, 1, 1)]


def test_until_is_inclusive_of_the_end_date() -> None:
    rule = Rule(date(2026, 1, 1), Daily(1), Until(date(2026, 1, 5)))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 12, 31))
    assert result == [date(2026, 1, d) for d in range(1, 6)]
    assert result[-1] == date(2026, 1, 5)


def test_until_excludes_occurrences_after_the_end_date() -> None:
    # End date falls between occurrences (every 2 days): last kept is 01-05.
    rule = Rule(date(2026, 1, 1), Daily(2), Until(date(2026, 1, 6)))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 12, 31))
    assert result == [date(2026, 1, 1), date(2026, 1, 3), date(2026, 1, 5)]


def test_count_and_until_diverge_for_the_same_pattern() -> None:
    start = date(2026, 1, 1)
    pattern = Daily(1)
    end_of_year = date(2026, 12, 31)
    by_count = get_occurrences(Rule(start, pattern, Count(3)), start, end_of_year)
    by_until = get_occurrences(Rule(start, pattern, Until(date(2026, 1, 10))), start, end_of_year)
    assert len(by_count) == 3
    assert len(by_until) == 10


def test_never_is_bounded_only_by_the_window() -> None:
    rule = Rule(date(2026, 1, 1), Daily(1), Never())
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 1, 10))
    assert len(result) == 10


def test_count_with_monthly_clamp_counts_clamped_months() -> None:
    # Each clamped month still consumes one of the K occurrences.
    rule = Rule(date(2026, 1, 31), MonthlyByDay(31), Count(3))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 12, 31))
    assert result == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
