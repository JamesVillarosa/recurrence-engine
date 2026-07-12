"""Contract tests for the automation ingress webhook.

These exercise the boundary the same way ``test_api.py`` does: auth, strict
validation with field-named 400s, and — the point of the endpoint — that
repeated deliveries of the same restock are idempotent while a fresh low-stock
event after completion creates a new task.

Each test gets an isolated on-disk SQLite database via a temp path and a known
webhook secret, both wired through environment variables.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from api import app
from fastapi.testclient import TestClient

SECRET = "test-secret-value"


@pytest.fixture
def client(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CADENCE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("CADENCE_DB_PATH", str(tmp_path) + "/cadence-test.db")  # type: ignore[operator]
    with TestClient(app) as c:  # `with` triggers the lifespan → init_db()
        yield c


def _post(client: TestClient, body: dict[str, object], secret: str | None = SECRET) -> object:
    headers = {"x-webhook-secret": secret} if secret is not None else {}
    return client.post("/api/webhooks/restock-task", json=body, headers=headers)


def _valid_body() -> dict[str, object]:
    return {
        "title": "Restock: Widget A",
        "due_date": "2026-07-13",
        "notes": "stock 3 < reorder 10",
        "source_key": "restock:widget-a",
    }


# --------------------------------------------------------------------------- #
# Happy path                                                                  #
# --------------------------------------------------------------------------- #
def test_happy_path_creates_task(client: TestClient) -> None:
    resp = _post(client, _valid_body())
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Restock: Widget A"
    assert body["due_date"] == "2026-07-13"
    assert body["source"] == "automation"
    assert body["completed"] is False
    assert body["deduplicated"] is False

    listing = client.get("/api/tasks").json()
    assert listing["count"] == 1


# --------------------------------------------------------------------------- #
# Auth                                                                        #
# --------------------------------------------------------------------------- #
def test_wrong_secret_is_401(client: TestClient) -> None:
    resp = _post(client, _valid_body(), secret="nope")
    assert resp.status_code == 401


def test_missing_secret_is_401(client: TestClient) -> None:
    resp = _post(client, _valid_body(), secret=None)
    assert resp.status_code == 401


def test_unconfigured_server_is_503(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CADENCE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("CADENCE_DB_PATH", str(tmp_path) + "/unconfigured.db")  # type: ignore[operator]
    with TestClient(app) as c:
        resp = c.post(
            "/api/webhooks/restock-task",
            json=_valid_body(),
            headers={"x-webhook-secret": "anything"},
        )
    assert resp.status_code == 503


# --------------------------------------------------------------------------- #
# Validation → 400 naming the field                                           #
# --------------------------------------------------------------------------- #
def test_empty_title_is_400(client: TestClient) -> None:
    body = _valid_body()
    body["title"] = "   "
    resp = _post(client, body)
    assert resp.status_code == 400
    assert "title" in resp.json()["detail"]


def test_missing_title_is_400(client: TestClient) -> None:
    body = _valid_body()
    del body["title"]
    resp = _post(client, body)
    assert resp.status_code == 400
    assert "title" in resp.json()["detail"]


def test_malformed_due_date_is_400(client: TestClient) -> None:
    body = _valid_body()
    body["due_date"] = "13-07-2026"
    resp = _post(client, body)
    assert resp.status_code == 400
    assert "due_date" in resp.json()["detail"]


def test_oversized_notes_is_400(client: TestClient) -> None:
    body = _valid_body()
    body["notes"] = "x" * 2001
    resp = _post(client, body)
    assert resp.status_code == 400
    assert "notes" in resp.json()["detail"]


def test_unknown_field_is_400(client: TestClient) -> None:
    body = _valid_body()
    body["priority"] = "high"
    resp = _post(client, body)
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# Idempotency                                                                 #
# --------------------------------------------------------------------------- #
def test_duplicate_post_is_deduplicated(client: TestClient) -> None:
    first = _post(client, _valid_body())
    assert first.status_code == 201
    assert first.json()["deduplicated"] is False

    second = _post(client, _valid_body())
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["id"] == first.json()["id"]

    listing = client.get("/api/tasks").json()
    assert listing["count"] == 1


def test_new_task_created_after_completion(client: TestClient) -> None:
    first = _post(client, _valid_body()).json()

    done = client.post(f"/api/tasks/{first['id']}/complete")
    assert done.status_code == 200
    assert done.json()["completed"] is True

    second = _post(client, _valid_body())
    assert second.status_code == 201
    assert second.json()["deduplicated"] is False
    assert second.json()["id"] != first["id"]

    listing = client.get("/api/tasks").json()
    assert listing["count"] == 2


def test_source_key_falls_back_to_title(client: TestClient) -> None:
    body = _valid_body()
    del body["source_key"]

    first = _post(client, body)
    assert first.status_code == 201
    second = _post(client, body)
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
