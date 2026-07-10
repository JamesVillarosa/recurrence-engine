"""Domain models for recurrence rules.

The engine operates purely on :class:`datetime.date` values. It carries no
notion of time-of-day or timezone by design: recurrence is calendar
arithmetic, and time-of-day/timezone concerns belong at the API boundary
(see ``api/``). Keeping the core timezone-free removes an entire class of
DST bugs from the part of the system where correctness is hardest to verify.

All models are frozen dataclasses: a rule is an immutable value, so expanding
the same rule always yields the same occurrences. That determinism is the
foundation of the test suite and of HTTP response caching in the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

# Weekday convention matches ``datetime.date.weekday()``: Monday == 0 ... Sunday == 6.
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)


class MonthEndPolicy(Enum):
    """How to resolve a monthly day-of-month that does not exist in a month.

    ``CLAMP`` (default) moves "the 31st" to the last valid day of shorter
    months (Feb 28/29, Apr 30). Rationale: a task due at month-end must never
    silently disappear from the schedule; clamping is the least-surprising,
    safest behaviour for a user-facing task planner.

    ``SKIP`` omits months that lack the day entirely. This mirrors the
    iCalendar RRULE ``BYMONTHDAY`` behaviour and is offered for callers that
    need strict calendar semantics rather than the safe default.
    """

    CLAMP = "clamp"
    SKIP = "skip"


# --------------------------------------------------------------------------- #
# Patterns                                                                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class OneOff:
    """A single occurrence on the rule's start date. No recurrence."""


@dataclass(frozen=True, slots=True)
class Daily:
    """Every ``interval`` days, starting from the rule's start date."""

    interval: int = 1

    def __post_init__(self) -> None:
        if self.interval < 1:
            raise ValueError(f"Daily interval must be >= 1, got {self.interval}")


@dataclass(frozen=True, slots=True)
class Weekly:
    """On specific ``weekdays``, every ``interval`` weeks.

    ``weekdays`` uses the ``date.weekday()`` convention (Monday == 0). The
    interval is anchored to the ISO week containing the rule's start date.
    """

    weekdays: frozenset[int]
    interval: int = 1

    def __post_init__(self) -> None:
        if self.interval < 1:
            raise ValueError(f"Weekly interval must be >= 1, got {self.interval}")
        if not self.weekdays:
            raise ValueError("Weekly pattern requires at least one weekday")
        invalid = [d for d in self.weekdays if d < MONDAY or d > SUNDAY]
        if invalid:
            raise ValueError(f"Weekday values must be in 0..6 (Mon..Sun), got {sorted(invalid)}")


@dataclass(frozen=True, slots=True)
class MonthlyByDay:
    """On a fixed ``day`` of the month, every ``interval`` months.

    Months that do not contain ``day`` are resolved via ``month_end_policy``.
    The interval is anchored to the rule's start month.
    """

    day: int
    interval: int = 1
    month_end_policy: MonthEndPolicy = MonthEndPolicy.CLAMP

    def __post_init__(self) -> None:
        if self.day < 1 or self.day > 31:
            raise ValueError(f"Day-of-month must be in 1..31, got {self.day}")
        if self.interval < 1:
            raise ValueError(f"Monthly interval must be >= 1, got {self.interval}")


Pattern = OneOff | Daily | Weekly | MonthlyByDay


# --------------------------------------------------------------------------- #
# End conditions                                                              #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Never:
    """The rule never ends on its own; the query window bounds the output."""


@dataclass(frozen=True, slots=True)
class Until:
    """The rule ends on ``date`` inclusive: occurrences on that date are kept."""

    date: date


@dataclass(frozen=True, slots=True)
class Count:
    """The rule ends after exactly ``count`` occurrences, counted from start.

    The count is always measured from the rule's start date, never from the
    query window. Where you look must not change how many occurrences exist.
    """

    count: int

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError(f"Count must be >= 1, got {self.count}")


EndCondition = Never | Until | Count


# --------------------------------------------------------------------------- #
# Rule                                                                         #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Rule:
    """A recurrence rule: a start date, a pattern, and an end condition."""

    start: date
    pattern: Pattern
    end: EndCondition = field(default_factory=Never)
