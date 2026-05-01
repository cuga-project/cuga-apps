"""SQLite-backed tool registry.

Phase 1: just enough schema to record what tools exist and where they came from.
Phase 3 fills in acquired-tool rows; phase 5 adds health-check timestamps.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "registry.sqlite"


@dataclass
class ToolRecord:
    id: str           # stable id, "{source}:{name}"
    name: str
    source: str       # 'mcp_server' | 'acquired_openapi' | 'acquired_browser' | ...
    description: str
    spec: dict        # free-form metadata (server name, URL, schema, etc.)
    health: str = "unknown"     # 'ok' | 'failing' | 'quarantined' | 'unknown'
    installed_at: str = ""
    last_probed_at: str | None = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tools (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    source          TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    spec_json       TEXT NOT NULL,
    health          TEXT NOT NULL DEFAULT 'unknown',
    installed_at    TEXT NOT NULL,
    last_probed_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_tools_source ON tools(source);
"""


class ToolRegistry:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def upsert(self, rec: ToolRecord) -> None:
        if not rec.installed_at:
            rec.installed_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO tools (id, name, source, description, spec_json, health, installed_at, last_probed_at)
            VALUES (:id, :name, :source, :description, :spec_json, :health, :installed_at, :last_probed_at)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                source=excluded.source,
                description=excluded.description,
                spec_json=excluded.spec_json,
                health=excluded.health,
                last_probed_at=excluded.last_probed_at
            """,
            {
                "id": rec.id,
                "name": rec.name,
                "source": rec.source,
                "description": rec.description,
                "spec_json": json.dumps(rec.spec),
                "health": rec.health,
                "installed_at": rec.installed_at,
                "last_probed_at": rec.last_probed_at,
            },
        )
        self._conn.commit()

    def upsert_many(self, recs: Iterable[ToolRecord]) -> None:
        for r in recs:
            self.upsert(r)

    def all(self) -> list[ToolRecord]:
        rows = self._conn.execute("SELECT * FROM tools ORDER BY source, name").fetchall()
        return [self._row_to_rec(r) for r in rows]

    def by_source(self, source: str) -> list[ToolRecord]:
        rows = self._conn.execute(
            "SELECT * FROM tools WHERE source = ? ORDER BY name", (source,)
        ).fetchall()
        return [self._row_to_rec(r) for r in rows]

    def replace_source(self, source: str, recs: list[ToolRecord]) -> None:
        """Delete all rows for a source then insert the given recs.

        Used by discovery: every startup re-scans the live MCP catalog and
        replaces 'mcp_server' rows. Acquired tools (other sources) untouched.
        """
        self._conn.execute("DELETE FROM tools WHERE source = ?", (source,))
        self._conn.commit()
        self.upsert_many(recs)

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row_to_rec(row: sqlite3.Row) -> ToolRecord:
        return ToolRecord(
            id=row["id"],
            name=row["name"],
            source=row["source"],
            description=row["description"],
            spec=json.loads(row["spec_json"]),
            health=row["health"],
            installed_at=row["installed_at"],
            last_probed_at=row["last_probed_at"],
        )
