"""
Minimal SQLite todo store — no ORM, no dependencies beyond stdlib.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "storage" / "todos.db"
DB_PATH.parent.mkdir(exist_ok=True)

_CREATE = """
CREATE TABLE IF NOT EXISTS todos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    content        TEXT    NOT NULL,
    todo_type      TEXT    NOT NULL DEFAULT 'todo',   -- todo | reminder | note
    priority       TEXT    NOT NULL DEFAULT 'medium', -- high | medium | low
    tags           TEXT    NOT NULL DEFAULT '[]',     -- JSON array
    due_date       TEXT,                              -- ISO-8601 or NULL
    delivery_email TEXT,                              -- per-item recipient, or NULL
    status         TEXT    NOT NULL DEFAULT 'active', -- active | done
    created_at     TEXT    NOT NULL
);
"""


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _conn() as con:
        con.execute(_CREATE)
        # Migrate existing DBs that predate the delivery_email column.
        try:
            con.execute("ALTER TABLE todos ADD COLUMN delivery_email TEXT")
        except Exception:
            pass  # column already exists


def save(
    content: str,
    todo_type: str = "todo",
    priority: str = "medium",
    tags: list[str] | None = None,
    due_date: str | None = None,
    delivery_email: str | None = None,
) -> dict[str, Any]:
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO todos
               (content, todo_type, priority, tags, due_date, delivery_email, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'active', ?)""",
            (
                content,
                todo_type,
                priority,
                json.dumps(tags or []),
                due_date,
                delivery_email,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return get(cur.lastrowid)


def get(todo_id: int) -> dict[str, Any] | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
        return _row(row) if row else None


def list_all(status: str = "active") -> list[dict[str, Any]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM todos WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
        return [_row(r) for r in rows]


def list_due(now: datetime | None = None) -> list[dict[str, Any]]:
    """Return active reminders whose due_date is at or before `now`."""
    cutoff = (now or datetime.now()).isoformat(timespec="seconds")
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM todos
               WHERE status = 'active'
                 AND todo_type = 'reminder'
                 AND due_date IS NOT NULL
                 AND due_date <= ?
               ORDER BY due_date ASC""",
            (cutoff,),
        ).fetchall()
        return [_row(r) for r in rows]


def mark_done(todo_id: int) -> None:
    with _conn() as con:
        con.execute("UPDATE todos SET status = 'done' WHERE id = ?", (todo_id,))


def _row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d
