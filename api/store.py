"""Minimal SQLite-backed task store for the automation ingress.

The recurrence engine is pure and stateless; the webhook layer, by contrast,
needs somewhere to persist the tasks that inbound automations create. This
module is that store and nothing more: a single ``tasks`` table reached through
short-lived stdlib :mod:`sqlite3` connections. No ORM, no migration framework,
because there is exactly one table and its shape is created idempotently with
``CREATE TABLE IF NOT EXISTS`` on startup.

Idempotency for automation-created tasks is enforced *in the database*, not in
application code, by a partial unique index over ``source_key`` restricted to
open (incomplete) rows. That makes de-duplication race-safe: two concurrent
identical webhook deliveries cannot both insert; the loser gets an
``IntegrityError`` which :func:`create_automation_task` turns into a
"deduplicated" response. Once a task is completed it leaves the index's scope,
so the next low-stock event is free to create a fresh task.

Storage note: the default database lives on the local filesystem. On an
ephemeral host (e.g. Render's free tier) that file does not survive a restart;
point ``CADENCE_DB_PATH`` at a persistent volume for durable storage.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

Task = dict[str, Any]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    due_date     TEXT    NOT NULL,
    notes        TEXT    NOT NULL DEFAULT '',
    source       TEXT    NOT NULL DEFAULT 'manual'
                 CHECK (source IN ('manual', 'automation')),
    source_key   TEXT,
    completed_at TEXT,
    created_at   TEXT    NOT NULL
);

-- Race-safe idempotency: at most one OPEN task may exist per source_key.
-- Completed rows (completed_at IS NOT NULL) and manual rows (source_key IS
-- NULL) are excluded, so completing a task frees its key for a fresh one.
CREATE UNIQUE INDEX IF NOT EXISTS ux_tasks_open_source_key
    ON tasks (source_key)
    WHERE completed_at IS NULL AND source_key IS NOT NULL;
"""


def db_path() -> str:
    """Return the configured database path (env ``CADENCE_DB_PATH``)."""
    return os.environ.get("CADENCE_DB_PATH", "cadence.db")


def _connect() -> sqlite3.Connection:
    path = db_path()
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the ``tasks`` table and its indexes if they do not exist."""
    conn = _connect()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_task(row: sqlite3.Row) -> Task:
    return {
        "id": row["id"],
        "title": row["title"],
        "due_date": row["due_date"],
        "notes": row["notes"],
        "source": row["source"],
        "source_key": row["source_key"],
        "completed": row["completed_at"] is not None,
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
    }


def list_tasks() -> list[Task]:
    """Return every task, open ones first, newest within each group first."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY (completed_at IS NOT NULL), id DESC"
        ).fetchall()
        return [_to_task(r) for r in rows]
    finally:
        conn.close()


def get_task(task_id: int) -> Task | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _to_task(row) if row is not None else None
    finally:
        conn.close()


def complete_task(task_id: int) -> Task | None:
    """Mark a task completed. Returns the updated task, or ``None`` if absent.

    Completing is idempotent: an already-completed task keeps its original
    ``completed_at`` timestamp.
    """
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE tasks SET completed_at = ? "
            "WHERE id = ? AND completed_at IS NULL",
            (_now_iso(), task_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return _to_task(row) if row is not None else None
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return _to_task(row)
    finally:
        conn.close()


def create_manual_task(title: str, due_date: date, notes: str = "") -> Task:
    """Insert a one-off manual task (no idempotency key)."""
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO tasks (title, due_date, notes, source, source_key, created_at) "
            "VALUES (?, ?, ?, 'manual', NULL, ?)",
            (title, due_date.isoformat(), notes, _now_iso()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _to_task(row)
    finally:
        conn.close()


def create_automation_task(
    title: str, due_date: date, notes: str, source_key: str
) -> tuple[Task, bool]:
    """Insert an automation task, or return the existing open one.

    Returns ``(task, deduplicated)``. When an OPEN task with the same
    ``source_key`` already exists, no row is created and the existing task is
    returned with ``deduplicated=True``. The partial unique index makes this
    safe under concurrent deliveries: a losing insert raises ``IntegrityError``,
    which we resolve by fetching the open task the winner created.
    """
    conn = _connect()
    try:
        # Retry once to close the tiny window where the conflicting open task is
        # completed between our failed insert and the follow-up lookup.
        for _ in range(2):
            existing = conn.execute(
                "SELECT * FROM tasks "
                "WHERE source_key = ? AND completed_at IS NULL",
                (source_key,),
            ).fetchone()
            if existing is not None:
                return _to_task(existing), True
            try:
                cur = conn.execute(
                    "INSERT INTO tasks "
                    "(title, due_date, notes, source, source_key, created_at) "
                    "VALUES (?, ?, ?, 'automation', ?, ?)",
                    (title, due_date.isoformat(), notes, source_key, _now_iso()),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                continue
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return _to_task(row), False
        # Both attempts lost the race to a concurrent writer; return its task.
        existing = conn.execute(
            "SELECT * FROM tasks WHERE source_key = ? AND completed_at IS NULL",
            (source_key,),
        ).fetchone()
        if existing is not None:
            return _to_task(existing), True
        raise RuntimeError("could not create or find automation task")  # pragma: no cover
    finally:
        conn.close()
