"""Request/response schemas for the HTTP API.

These Pydantic models are the API's contract, deliberately decoupled from the
internal engine dataclasses. Wire-level patterns and end conditions are
tagged unions discriminated by a ``type`` field, so the request body is
self-describing and OpenAPI documents each variant precisely.

Validation constraints mirror the engine's invariants, so malformed input is
rejected at the boundary with a structured 422 rather than reaching the core.
``to_domain`` translates a validated request into engine models.
"""

from __future__ import annotations

from datetime import date as _Date
from typing import Annotated, Literal

from engine import (
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
from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Patterns                                                                     #
# --------------------------------------------------------------------------- #
class OneOffPattern(_Model):
    type: Literal["one_off"]

    def to_domain(self) -> Pattern:
        return OneOff()


class DailyPattern(_Model):
    type: Literal["daily"]
    interval: int = Field(default=1, ge=1, description="Every N days.")

    def to_domain(self) -> Pattern:
        return Daily(self.interval)


class WeeklyPattern(_Model):
    type: Literal["weekly"]
    weekdays: list[int] = Field(
        min_length=1, description="Weekdays, Monday=0 .. Sunday=6."
    )
    interval: int = Field(default=1, ge=1, description="Every N weeks.")

    def to_domain(self) -> Pattern:
        return Weekly(frozenset(self.weekdays), self.interval)


class MonthlyPattern(_Model):
    type: Literal["monthly"]
    day: int = Field(ge=1, le=31, description="Day of month, 1..31.")
    interval: int = Field(default=1, ge=1, description="Every N months.")
    month_end_policy: Literal["clamp", "skip"] = Field(
        default="clamp",
        description="How to handle months without the day: clamp to last day, or skip.",
    )

    def to_domain(self) -> Pattern:
        return MonthlyByDay(self.day, self.interval, MonthEndPolicy(self.month_end_policy))


PatternIn = Annotated[
    OneOffPattern | DailyPattern | WeeklyPattern | MonthlyPattern,
    Field(discriminator="type"),
]


# --------------------------------------------------------------------------- #
# End conditions                                                              #
# --------------------------------------------------------------------------- #
class NeverEnd(_Model):
    type: Literal["never"]

    def to_domain(self) -> EndCondition:
        return Never()


class UntilEnd(_Model):
    type: Literal["until"]
    date: _Date = Field(description="Inclusive last date the rule may produce.")

    def to_domain(self) -> EndCondition:
        return Until(self.date)


class CountEnd(_Model):
    type: Literal["count"]
    count: int = Field(ge=1, description="Total occurrences from the start date.")

    def to_domain(self) -> EndCondition:
        return Count(self.count)


EndIn = Annotated[
    NeverEnd | UntilEnd | CountEnd,
    Field(discriminator="type"),
]


# --------------------------------------------------------------------------- #
# Rule + request/response                                                      #
# --------------------------------------------------------------------------- #
class RuleIn(_Model):
    start: _Date = Field(description="Anchor date of the rule.")
    pattern: PatternIn
    end: EndIn = Field(default_factory=lambda: NeverEnd(type="never"))

    def to_domain(self) -> Rule:
        return Rule(self.start, self.pattern.to_domain(), self.end.to_domain())


class OccurrencesRequest(_Model):
    rule: RuleIn
    window_start: _Date = Field(description="Inclusive start of the query window.")
    window_end: _Date = Field(description="Inclusive end of the query window.")

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "rule": {
                    "start": "2026-01-05",
                    "pattern": {"type": "weekly", "weekdays": [0, 2, 4], "interval": 1},
                    "end": {"type": "count", "count": 5},
                },
                "window_start": "2026-01-01",
                "window_end": "2026-12-31",
            }
        },
    )


class OccurrencesResponse(_Model):
    occurrences: list[_Date]
    count: int = Field(description="Number of occurrences returned in the window.")
