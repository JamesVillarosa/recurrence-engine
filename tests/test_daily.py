"""Daily patterns, including intervals and window clipping."""

from __future__ import annotations

from datetime import date, timedelta

from engine import Count, Daily, Rule, get_occurrences


def test_every_day() -> None:
    rule = Rule(date(2026, 1, 1), Daily(1))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 1, 5))
    assert result == [date(2026, 1, d) for d in range(1, 6)]


def test_every_three_days_is_anchored_to_start() -> None:
    rule = Rule(date(2026, 1, 1), Daily(3))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 1, 12))
    assert result == [date(2026, 1, 1), date(2026, 1, 4), date(2026, 1, 7), date(2026, 1, 10)]


def test_window_clips_without_shifting_the_phase() -> None:
    # A window that starts mid-sequence must not re-anchor the cadence:
    # occurrences stay on the start-anchored grid (1, 4, 7, 10, 13...).
    rule = Rule(date(2026, 1, 1), Daily(3))
    result = get_occurrences(rule, date(2026, 1, 5), date(2026, 1, 11))
    assert result == [date(2026, 1, 7), date(2026, 1, 10)]


def test_default_interval_is_one() -> None:
    rule = Rule(date(2026, 1, 1), Daily())
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 1, 3))
    assert result == [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]


def test_daily_with_count_crossing_month_boundary() -> None:
    rule = Rule(date(2026, 1, 30), Daily(1), Count(4))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 12, 31))
    assert result == [date(2026, 1, 30) + timedelta(days=i) for i in range(4)]
    assert result[-1] == date(2026, 2, 2)
