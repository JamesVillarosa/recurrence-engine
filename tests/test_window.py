"""Window semantics: bounds, emptiness, ordering, and de-duplication."""

from __future__ import annotations

from datetime import date

from engine import Daily, MonthlyByDay, OneOff, Rule, Weekly, get_occurrences


def test_empty_window_returns_empty_list() -> None:
    rule = Rule(date(2026, 1, 1), Daily(1))
    assert get_occurrences(rule, date(2026, 6, 1), date(2026, 5, 1)) == []


def test_window_before_first_occurrence_is_empty() -> None:
    rule = Rule(date(2026, 6, 1), Daily(1))
    assert get_occurrences(rule, date(2026, 1, 1), date(2026, 5, 31)) == []


def test_single_day_window_that_matches() -> None:
    rule = Rule(date(2026, 1, 1), Daily(1))
    assert get_occurrences(rule, date(2026, 1, 10), date(2026, 1, 10)) == [date(2026, 1, 10)]


def test_single_day_window_that_misses() -> None:
    rule = Rule(date(2026, 1, 1), Daily(2))  # even offsets from Jan 1 -> Jan 11 is odd
    assert get_occurrences(rule, date(2026, 1, 10), date(2026, 1, 10)) == []


def test_window_bounds_are_both_inclusive() -> None:
    rule = Rule(date(2026, 1, 1), Daily(1))
    result = get_occurrences(rule, date(2026, 1, 5), date(2026, 1, 8))
    assert result[0] == date(2026, 1, 5)
    assert result[-1] == date(2026, 1, 8)


def test_results_are_sorted_and_unique() -> None:
    rule = Rule(date(2026, 1, 5), Weekly(frozenset({0, 2, 4})))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 3, 31))
    assert result == sorted(result)
    assert len(result) == len(set(result))


def test_oneoff_outside_window_stays_empty() -> None:
    rule = Rule(date(2026, 1, 1), OneOff())
    assert get_occurrences(rule, date(2026, 2, 1), date(2026, 2, 28)) == []


def test_monthly_window_starting_mid_stream() -> None:
    rule = Rule(date(2026, 1, 15), MonthlyByDay(15))
    result = get_occurrences(rule, date(2026, 6, 1), date(2026, 8, 31))
    assert result == [date(2026, 6, 15), date(2026, 7, 15), date(2026, 8, 15)]
