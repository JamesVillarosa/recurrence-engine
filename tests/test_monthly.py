"""Monthly patterns, with focus on month-end handling — the headline edge case.

"Monthly on the 31st" must have a defined, consistent behaviour in February.
Two policies are supported and both are pinned down here:

* CLAMP (default): fall back to the last valid day of the month.
* SKIP: omit months that lack the day.
"""

from __future__ import annotations

from datetime import date

from engine import MonthEndPolicy, MonthlyByDay, Rule, get_occurrences


def test_simple_fifteenth_of_each_month() -> None:
    rule = Rule(date(2026, 1, 15), MonthlyByDay(15))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 4, 30))
    assert result == [date(2026, m, 15) for m in (1, 2, 3, 4)]


def test_thirty_first_clamps_to_month_end() -> None:
    # 2026 is not a leap year: February clamps to the 28th, April to the 30th.
    rule = Rule(date(2026, 1, 31), MonthlyByDay(31, month_end_policy=MonthEndPolicy.CLAMP))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 6, 30))
    assert result == [
        date(2026, 1, 31),
        date(2026, 2, 28),  # clamped
        date(2026, 3, 31),
        date(2026, 4, 30),  # clamped
        date(2026, 5, 31),
        date(2026, 6, 30),  # clamped
    ]


def test_clamp_is_the_default_policy() -> None:
    rule = Rule(date(2026, 1, 31), MonthlyByDay(31))
    result = get_occurrences(rule, date(2026, 2, 1), date(2026, 2, 28))
    assert result == [date(2026, 2, 28)]


def test_thirty_first_skips_short_months() -> None:
    rule = Rule(date(2026, 1, 31), MonthlyByDay(31, month_end_policy=MonthEndPolicy.SKIP))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 8, 31))
    # Only months that actually have a 31st (Jan, Mar, May, Jul, Aug within window).
    assert result == [
        date(2026, 1, 31),
        date(2026, 3, 31),
        date(2026, 5, 31),
        date(2026, 7, 31),
        date(2026, 8, 31),
    ]


def test_clamp_hits_feb_29_in_a_leap_year() -> None:
    # 2028 is a leap year: the 29th exists in February.
    rule = Rule(date(2028, 1, 29), MonthlyByDay(29))
    result = get_occurrences(rule, date(2028, 1, 1), date(2028, 3, 31))
    assert result == [date(2028, 1, 29), date(2028, 2, 29), date(2028, 3, 29)]


def test_clamp_falls_to_feb_28_in_a_non_leap_year() -> None:
    rule = Rule(date(2026, 1, 29), MonthlyByDay(29))
    result = get_occurrences(rule, date(2026, 2, 1), date(2026, 2, 28))
    assert result == [date(2026, 2, 28)]


def test_start_day_does_not_match_pattern_day() -> None:
    # Rule says "the 15th" but starts on the 20th: the first occurrence is the
    # next 15th (the following month), never a partial first month.
    rule = Rule(date(2026, 1, 20), MonthlyByDay(15))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 3, 31))
    assert result == [date(2026, 2, 15), date(2026, 3, 15)]


def test_every_two_months() -> None:
    rule = Rule(date(2026, 1, 10), MonthlyByDay(10, interval=2))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 12, 31))
    assert result == [date(2026, m, 10) for m in (1, 3, 5, 7, 9, 11)]


def test_interval_crosses_year_boundary() -> None:
    rule = Rule(date(2026, 11, 5), MonthlyByDay(5, interval=3))
    result = get_occurrences(rule, date(2026, 1, 1), date(2027, 12, 31))
    assert result == [date(2026, 11, 5), date(2027, 2, 5), date(2027, 5, 5),
                      date(2027, 8, 5), date(2027, 11, 5)]
