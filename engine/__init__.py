"""Deterministic recurrence-rule expansion engine.

Expand a :class:`~engine.models.Rule` into concrete, ordered, de-duplicated
occurrence dates within a query window::

    from datetime import date
    from engine import Rule, Weekly, Count, get_occurrences

    rule = Rule(
        start=date(2026, 1, 5),
        pattern=Weekly(weekdays=frozenset({0, 2, 4}), interval=1),  # Mon/Wed/Fri
        end=Count(5),
    )
    get_occurrences(rule, date(2026, 1, 1), date(2026, 12, 31))
"""

from __future__ import annotations

from .expand import get_occurrences
from .models import (
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
)

__all__ = [
    "Count",
    "Daily",
    "EndCondition",
    "MonthEndPolicy",
    "MonthlyByDay",
    "Never",
    "OneOff",
    "Pattern",
    "Rule",
    "Until",
    "Weekly",
    "get_occurrences",
]

__version__ = "1.0.0"
