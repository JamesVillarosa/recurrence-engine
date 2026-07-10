"""Model construction rejects invalid rules at the boundary.

Validation lives in the dataclasses' ``__post_init__`` so an invalid rule can
never be constructed, and therefore can never reach the expansion engine.
"""

from __future__ import annotations

import pytest
from engine import Count, Daily, MonthlyByDay, Weekly


@pytest.mark.parametrize("interval", [0, -1, -10])
def test_daily_interval_must_be_positive(interval: int) -> None:
    with pytest.raises(ValueError, match="Daily interval must be >= 1"):
        Daily(interval)


@pytest.mark.parametrize("interval", [0, -1])
def test_weekly_interval_must_be_positive(interval: int) -> None:
    with pytest.raises(ValueError, match="Weekly interval must be >= 1"):
        Weekly(frozenset({0}), interval)


def test_weekly_requires_at_least_one_weekday() -> None:
    with pytest.raises(ValueError, match="at least one weekday"):
        Weekly(frozenset())


@pytest.mark.parametrize("bad", [7, 8, -1])
def test_weekly_rejects_out_of_range_weekday(bad: int) -> None:
    with pytest.raises(ValueError, match="Weekday values must be in"):
        Weekly(frozenset({0, bad}))


@pytest.mark.parametrize("day", [0, 32, -1, 100])
def test_monthly_day_must_be_in_range(day: int) -> None:
    with pytest.raises(ValueError, match="Day-of-month must be in"):
        MonthlyByDay(day)


@pytest.mark.parametrize("interval", [0, -1])
def test_monthly_interval_must_be_positive(interval: int) -> None:
    with pytest.raises(ValueError, match="Monthly interval must be >= 1"):
        MonthlyByDay(15, interval)


@pytest.mark.parametrize("count", [0, -1, -5])
def test_count_must_be_positive(count: int) -> None:
    with pytest.raises(ValueError, match="Count must be >= 1"):
        Count(count)
