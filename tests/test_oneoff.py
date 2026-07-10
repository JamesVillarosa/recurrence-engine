"""One-off rules: a single occurrence on the start date, no recurrence."""

from __future__ import annotations

from datetime import date

from engine import Count, Never, OneOff, Rule, Until, get_occurrences


def test_single_occurrence_inside_window() -> None:
    rule = Rule(date(2026, 3, 15), OneOff())
    assert get_occurrences(rule, date(2026, 1, 1), date(2026, 12, 31)) == [date(2026, 3, 15)]


def test_occurrence_on_window_boundaries_is_inclusive() -> None:
    rule = Rule(date(2026, 3, 15), OneOff())
    assert get_occurrences(rule, date(2026, 3, 15), date(2026, 3, 15)) == [date(2026, 3, 15)]


def test_window_entirely_before_start_is_empty() -> None:
    rule = Rule(date(2026, 3, 15), OneOff())
    assert get_occurrences(rule, date(2026, 1, 1), date(2026, 3, 14)) == []


def test_window_entirely_after_start_is_empty() -> None:
    rule = Rule(date(2026, 3, 15), OneOff())
    assert get_occurrences(rule, date(2026, 3, 16), date(2026, 12, 31)) == []


def test_end_condition_does_not_add_occurrences() -> None:
    # A one-off yields exactly once regardless of the declared end condition.
    for end in (Never(), Until(date(2027, 1, 1)), Count(5)):
        rule = Rule(date(2026, 3, 15), OneOff(), end)
        assert get_occurrences(rule, date(2026, 1, 1), date(2026, 12, 31)) == [date(2026, 3, 15)]
