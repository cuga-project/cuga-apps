"""Persistent record of which catalog entries the user has approved.

Backend reads this on startup and merges with the always-on baseline (the
adapter's `MCP_SERVERS` env) before issuing a `/agent/reload`.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "activations.sqlite"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS activations (
    catalog_id    TEXT PRIMARY KEY,
    approved_at   TEXT NOT NULL,
    enabled       INTEGER NOT NULL DEFAULT 1
);
"""


class ActivationStore:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def approve(self, catalog_id: str) -> None:
        self._conn.execute(
            """
            INSERT INTO activations (catalog_id, approved_at, enabled)
            VALUES (?, ?, 1)
            ON CONFLICT(catalog_id) DO UPDATE SET enabled = 1
            """,
            (catalog_id, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def disable(self, catalog_id: str) -> None:
        self._conn.execute(
            "UPDATE activations SET enabled = 0 WHERE catalog_id = ?",
            (catalog_id,),
        )
        self._conn.commit()

    def active_ids(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT catalog_id FROM activations WHERE enabled = 1 ORDER BY approved_at"
        ).fetchall()
        return [r["catalog_id"] for r in rows]

    def close(self) -> None:
        self._conn.close()
