"""HTTP contract tests for the FastAPI layer.

These exercise the boundary: request validation, the domain translation,
error mapping, and conditional-caching headers. The engine's own correctness
is covered exhaustively by the unit and property suites.
"""

from __future__ import annotations

import pytest
from api import app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_info_metadata(client: TestClient) -> None:
    resp = client.get("/info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "cadence"
    assert body["component"] == "recurrence-engine"


def test_root_serves_playground(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Cadence" in resp.text


def test_expand_weekly_with_count(client: TestClient) -> None:
    resp = client.post(
        "/v1/occurrences",
        json={
            "rule": {
                "start": "2026-01-06",  # a Tuesday
                "pattern": {"type": "weekly", "weekdays": [0, 2, 4]},
                "end": {"type": "count", "count": 5},
            },
            "window_start": "2026-01-01",
            "window_end": "2026-12-31",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 5
    assert body["occurrences"][0] == "2026-01-07"  # first match after Tuesday


def test_expand_monthly_clamp(client: TestClient) -> None:
    resp = client.post(
        "/v1/occurrences",
        json={
            "rule": {
                "start": "2026-01-31",
                "pattern": {"type": "monthly", "day": 31, "month_end_policy": "clamp"},
                "end": {"type": "count", "count": 2},
            },
            "window_start": "2026-01-01",
            "window_end": "2026-12-31",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["occurrences"] == ["2026-01-31", "2026-02-28"]


def test_default_end_is_never(client: TestClient) -> None:
    resp = client.post(
        "/v1/occurrences",
        json={
            "rule": {"start": "2026-01-01", "pattern": {"type": "daily"}},
            "window_start": "2026-01-01",
            "window_end": "2026-01-05",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 5


def test_invalid_weekday_is_rejected(client: TestClient) -> None:
    resp = client.post(
        "/v1/occurrences",
        json={
            "rule": {
                "start": "2026-01-01",
                "pattern": {"type": "weekly", "weekdays": []},
            },
            "window_start": "2026-01-01",
            "window_end": "2026-01-31",
        },
    )
    assert resp.status_code == 422


def test_unknown_pattern_type_is_rejected(client: TestClient) -> None:
    resp = client.post(
        "/v1/occurrences",
        json={
            "rule": {"start": "2026-01-01", "pattern": {"type": "yearly"}},
            "window_start": "2026-01-01",
            "window_end": "2026-01-31",
        },
    )
    assert resp.status_code == 422


def test_etag_enables_conditional_304(client: TestClient) -> None:
    request = {
        "rule": {"start": "2026-01-01", "pattern": {"type": "daily"}},
        "window_start": "2026-01-01",
        "window_end": "2026-01-05",
    }
    first = client.post("/v1/occurrences", json=request)
    etag = first.headers["ETag"]
    assert first.headers["Cache-Control"] == "public, max-age=86400"

    second = client.post("/v1/occurrences", json=request, headers={"If-None-Match": etag})
    assert second.status_code == 304
