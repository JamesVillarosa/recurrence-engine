"""Automation ingress: the webhook that turns low-stock events into tasks.

An external workflow (n8n, in the reference setup) posts one restock request
per low-stock product to :func:`restock_task`. The endpoint is deliberately
boring and defensive:

* **Authenticated** with a shared secret compared in constant time. A missing
  or wrong secret is a 401; a server that has no secret configured refuses all
  requests with 503 rather than silently running open.
* **Strictly validated** — a bad field yields a 400 that *names* the field, so
  the caller can see exactly what to fix.
* **Idempotent** — the same restock, delivered repeatedly (daily reruns,
  at-least-once retries), creates the task once. See :mod:`api.store`.

Two small unauthenticated read/update routes (``GET /api/tasks`` and
``POST /api/tasks/{id}/complete``) back the bundled playground so created tasks
are visible on screen and the "complete, then a fresh task is created" lifecycle
can be demonstrated live.
"""

from __future__ import annotations

import hmac
import os
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from . import store

router = APIRouter(prefix="/api", tags=["automation"])

_TITLE_MAX = 200
_NOTES_MAX = 2000
_KEY_MAX = 200


class RestockTaskIn(BaseModel):
    """Inbound restock request. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="Task title, e.g. 'Restock: Widget A'.")
    due_date: date = Field(description="Calendar due date, YYYY-MM-DD.")
    notes: str = Field(default="", description="Free-form context for the task.")
    source_key: str | None = Field(
        default=None,
        description=(
            "Stable idempotency key for the underlying restock event. When "
            "omitted, a key is derived from the title."
        ),
    )

    @field_validator("title")
    @classmethod
    def _check_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        if len(v) > _TITLE_MAX:
            raise ValueError(f"must be at most {_TITLE_MAX} characters")
        return v

    @field_validator("notes")
    @classmethod
    def _check_notes(cls, v: str) -> str:
        if len(v) > _NOTES_MAX:
            raise ValueError(f"must be at most {_NOTES_MAX} characters")
        return v

    @field_validator("source_key")
    @classmethod
    def _check_source_key(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > _KEY_MAX:
            raise ValueError(f"must be at most {_KEY_MAX} characters")
        return v


def _require_secret(request: Request) -> None:
    """Enforce the shared-secret header. Raises on any failure.

    503 when the server has no secret configured (fail closed, never open);
    401 when the caller's ``x-webhook-secret`` is missing or does not match.
    The comparison is constant-time to avoid leaking the secret by timing.
    """
    expected = os.environ.get("CADENCE_WEBHOOK_SECRET")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Webhook endpoint is not configured (CADENCE_WEBHOOK_SECRET unset).",
        )
    provided = request.headers.get("x-webhook-secret", "")
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing webhook secret.")


def _derive_source_key(title: str) -> str:
    """Fallback idempotency key when the caller supplies none."""
    return "title:" + title.strip().lower()


@router.post(
    "/webhooks/restock-task",
    summary="Create a restock task from an automation (idempotent)",
    status_code=201,
)
async def restock_task(request: Request) -> JSONResponse:
    _require_secret(request)

    try:
        raw: Any = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Body must be valid JSON.") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object.")

    try:
        data = RestockTaskIn.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = first.get("loc", ())
        field = str(loc[-1]) if loc else "body"
        raise HTTPException(status_code=400, detail=f"{field}: {first['msg']}") from exc

    source_key = data.source_key or _derive_source_key(data.title)
    task, deduplicated = store.create_automation_task(
        title=data.title,
        due_date=data.due_date,
        notes=data.notes,
        source_key=source_key,
    )
    body = {**task, "deduplicated": deduplicated}
    return JSONResponse(status_code=200 if deduplicated else 201, content=body)


@router.get("/tasks", summary="List tasks (for the bundled playground)")
def get_tasks() -> dict[str, Any]:
    tasks = store.list_tasks()
    return {"tasks": tasks, "count": len(tasks)}


@router.post("/tasks/{task_id}/complete", summary="Mark a task completed")
def complete(task_id: int) -> Any:
    task = store.complete_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"No task with id {task_id}.")
    return task
