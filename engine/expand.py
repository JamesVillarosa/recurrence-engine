"""Expansion of recurrence rules into concrete occurrence dates.

The public entry point is :func:`get_occurrences`. The per-pattern generators
below yield the rule's occurrences in strictly increasing date order, starting
at (or after) the rule's start date. ``get_occurrences`` then applies the end
condition and clips the result to the requested window.

Invariant relied upon throughout: every generator yields dates in strictly
ascending order. That lets the consumer stop at the first date past the window
end instead of materialising an unbounded sequence.
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterator
from datetime import date, timedelta

from .models import (
    Count,
    Daily,
    MonthEndPolicy,
    MonthlyByDay,
    OneOff,
    Rule,
    Until,
    Weekly,
)


def get_occurrences(rule: Rule, window_start: date, window_end: date) -> list[date]:
    """Return the rule's occurrences within ``[window_start, window_end]``.

    The result is ordered ascending, de-duplicated, and inclusive of both
    window bounds. An empty list is returned when the window is empty
    (``window_start > window_end``) or contains no occurrences.

    The end condition is evaluated against the rule's own timeline, not the
    window: "after K occurrences" counts the K occurrences from the start
    date, so narrowing the window can never reveal or hide occurrences that
    the rule does not actually produce.
    """
    if window_start > window_end:
        return []

    result: list[date] = []
    emitted = 0
    for occ in _generate(rule):
        # End condition bounds the rule's timeline first.
        if isinstance(rule.end, Until) and occ > rule.end.date:
            break
        if isinstance(rule.end, Count) and emitted >= rule.end.count:
            break
        emitted += 1  # noqa: SIM113 — counts emitted occurrences, not loop position

        # Then clip to the query window. Generators are strictly ascending,
        # so once we pass the window end no later occurrence can qualify.
        if occ > window_end:
            break
        if occ >= window_start:
            result.append(occ)
    return result


def _generate(rule: Rule) -> Iterator[date]:
    """Dispatch to the pattern-specific generator for ``rule``."""
    pattern = rule.pattern
    if isinstance(pattern, OneOff):
        return _generate_oneoff(rule.start)
    if isinstance(pattern, Daily):
        return _generate_daily(rule.start, pattern.interval)
    if isinstance(pattern, Weekly):
        return _generate_weekly(rule.start, pattern.weekdays, pattern.interval)
    if isinstance(pattern, MonthlyByDay):
        return _generate_monthly(
            rule.start, pattern.day, pattern.interval, pattern.month_end_policy
        )
    raise TypeError(f"Unsupported pattern: {type(pattern).__name__}")  # pragma: no cover


def _generate_oneoff(start: date) -> Iterator[date]:
    yield start


def _generate_daily(start: date, interval: int) -> Iterator[date]:
    step = timedelta(days=interval)
    current = start
    while True:
        yield current
        current += step


def _generate_weekly(start: date, weekdays: frozenset[int], interval: int) -> Iterator[date]:
    # Anchor on the Monday of the start week; interval counts whole weeks
    # from that anchor. Within a qualifying week, emit the selected weekdays
    # in ascending order, skipping any that fall before the start date.
    anchor_monday = start - timedelta(days=start.weekday())
    ordered_weekdays = sorted(weekdays)
    week_step = timedelta(weeks=interval)
    monday = anchor_monday
    while True:
        for weekday in ordered_weekdays:
            occ = monday + timedelta(days=weekday)
            if occ >= start:
                yield occ
        monday += week_step


def _generate_monthly(
    start: date, day: int, interval: int, policy: MonthEndPolicy
) -> Iterator[date]:
    year, month = start.year, start.month
    while True:
        days_in_month = monthrange(year, month)[1]
        if day <= days_in_month:
            occ = date(year, month, day)
        elif policy is MonthEndPolicy.CLAMP:
            occ = date(year, month, days_in_month)
        else:  # MonthEndPolicy.SKIP
            occ = None

        if occ is not None and occ >= start:
            yield occ

        year, month = _advance_month(year, month, interval)


def _advance_month(year: int, month: int, months: int) -> tuple[int, int]:
    """Return ``(year, month)`` advanced by ``months`` calendar months."""
    zero_based = (month - 1) + months
    return year + zero_based // 12, (zero_based % 12) + 1
