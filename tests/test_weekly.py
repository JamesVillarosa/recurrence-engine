"""Weekly patterns: weekday selection, interval anchoring, start alignment."""

from __future__ import annotations

from datetime import date

from engine import Rule, Weekly, get_occurrences

# Weekday constants (Monday == 0), mirroring date.weekday().
MON, TUE, WED, THU, FRI = 0, 1, 2, 3, 4


def test_mon_wed_fri_starting_on_a_non_matching_tuesday() -> None:
    # 2026-01-06 is a Tuesday, which is not in {Mon, Wed, Fri}. The first
    # occurrence must be the next matching weekday: Wednesday 2026-01-07.
    rule = Rule(date(2026, 1, 6), Weekly(frozenset({MON, WED, FRI})))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 1, 18))
    assert result == [
        date(2026, 1, 7),  # Wed
        date(2026, 1, 9),  # Fri
        date(2026, 1, 12),  # Mon
        date(2026, 1, 14),  # Wed
        date(2026, 1, 16),  # Fri
    ]


def test_start_on_a_matching_weekday_is_included() -> None:
    # 2026-01-05 is a Monday and is selected, so it is the first occurrence.
    rule = Rule(date(2026, 1, 5), Weekly(frozenset({MON, WED})))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 1, 11))
    assert result == [date(2026, 1, 5), date(2026, 1, 7)]


def test_every_two_weeks_is_anchored_to_start_week() -> None:
    # Start Monday 2026-01-05. Bi-weekly Mondays: 01-05, 01-19, 02-02...
    rule = Rule(date(2026, 1, 5), Weekly(frozenset({MON}), interval=2))
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 2, 15))
    assert result == [date(2026, 1, 5), date(2026, 1, 19), date(2026, 2, 2)]


def test_occurrences_are_ordered_within_each_week() -> None:
    # Weekdays supplied out of order must still be emitted ascending.
    rule = Rule(date(2026, 1, 5), Weekly(frozenset({FRI, MON, WED})))
    result = get_occurrences(rule, date(2026, 1, 5), date(2026, 1, 9))
    assert result == [date(2026, 1, 5), date(2026, 1, 7), date(2026, 1, 9)]


def test_single_weekday() -> None:
    rule = Rule(date(2026, 1, 1), Weekly(frozenset({THU})))  # 2026-01-01 is Thursday
    result = get_occurrences(rule, date(2026, 1, 1), date(2026, 1, 31))
    assert result == [date(2026, 1, d) for d in (1, 8, 15, 22, 29)]
