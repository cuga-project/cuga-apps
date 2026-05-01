"""
Voice Journal store — SQLite + dated Markdown files.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

_DIR     = Path(__file__).parent / "storage"
_DIR.mkdir(exist_ok=True)
_JOURNAL = _DIR / "journal"
_DB_PATH = _DIR / "journal.db"

_CREATE = """
CREATE TABLE IF NOT EXISTS entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date  TEXT    NOT NULL,
    title       TEXT    NOT NULL DEFAULT 'Journal Entry',
    body        TEXT    NOT NULL DEFAULT '',
    summary     TEXT    NOT NULL DEFAULT '',
    tags        TEXT    NOT NULL DEFAULT '',
    source      TEXT    NOT NULL DEFAULT 'text',
    audio_path  TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'ready',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL DEFAULT ''
);
"""

_MIGRATIONS = [
    "ALTER TABLE entries ADD COLUMN summary    TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE entries ADD COLUMN audio_path TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE entries ADD COLUMN status     TEXT NOT NULL DEFAULT 'ready'",
    "ALTER TABLE entries ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''",
]


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    _JOURNAL.mkdir(exist_ok=True)
    (_DIR / "journal" / "audio").mkdir(parents=True, exist_ok=True)
    with _conn() as con:
        con.execute(_CREATE)
        for m in _MIGRATIONS:
            try:
                con.execute(m)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def create_pending_entry(audio_path: str, source: str = "record") -> dict:
    """Insert a placeholder entry with status=processing. Returns {id, status, created_at}."""
    today   = date.today().isoformat()
    now_str = datetime.now().isoformat(timespec="seconds")
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO entries "
            "(entry_date, title, body, summary, tags, source, audio_path, status, created_at, updated_at) "
            "VALUES (?, 'Processing…', '', '', '', ?, ?, 'processing', ?, ?)",
            (today, source, audio_path, now_str, now_str),
        )
        return {"id": cur.lastrowid, "status": "processing", "created_at": now_str}


def update_entry(entry_id: int | str, **kwargs) -> None:
    kwargs["updated_at"] = datetime.now().isoformat(timespec="seconds")
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [int(entry_id)]
    with _conn() as con:
        con.execute(f"UPDATE entries SET {sets} WHERE id=?", vals)


def save_entry(
    body: str,
    title: str = "Journal Entry",
    summary: str = "",
    tags: str = "",
    source: str = "text",
    audio_path: str = "",
    entry_id: int | str | None = None,
    entry_date: str | None = None,
) -> dict[str, Any]:
    today   = entry_date or date.today().isoformat()
    now_str = datetime.now().isoformat(timespec="seconds")

    if entry_id is not None:
        # Update existing pending entry (voice flow)
        update_entry(
            entry_id,
            title=title, body=body, summary=summary,
            tags=tags, status="ready",
        )
        _append_markdown(today, title, body, tags, source)
        return {"id": int(entry_id), "date": today, "title": title, "status": "ready"}

    # Insert new entry (text/chat flow)
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO entries "
            "(entry_date, title, body, summary, tags, source, audio_path, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?)",
            (today, title, body, summary, tags, source, audio_path, now_str, now_str),
        )
        new_id = cur.lastrowid
    _append_markdown(today, title, body, tags, source)
    return {"id": new_id, "date": today, "title": title, "status": "ready"}


def delete_entry(entry_id: int | str) -> None:
    with _conn() as con:
        con.execute("DELETE FROM entries WHERE id=?", (int(entry_id),))


def _append_markdown(entry_date: str, title: str, body: str, tags: str, source: str) -> None:
    md_path = _JOURNAL / f"{entry_date}.md"
    now_str = datetime.now().isoformat(timespec="seconds")
    with open(md_path, "a", encoding="utf-8") as f:
        if md_path.stat().st_size == 0:
            f.write(f"# Journal — {entry_date}\n\n")
        heading  = f"## {title}" if title else f"## Entry at {now_str[11:16]}"
        tag_line = f"\n*Tags: {tags}*" if tags else ""
        src_line = f"\n*Source: {source}*" if source != "text" else ""
        f.write(f"{heading}{src_line}{tag_line}\n\n{body}\n\n---\n\n")


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_entry(entry_id: int | str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM entries WHERE id=?", (int(entry_id),)).fetchone()
    return dict(row) if row else None


def list_entries(
    entry_date: str | None = None,
    since_date: str | None = None,
    until_date: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    with _conn() as con:
        if entry_date:
            rows = con.execute(
                "SELECT * FROM entries WHERE entry_date=? ORDER BY created_at DESC LIMIT ?",
                (entry_date, limit),
            ).fetchall()
        elif since_date or until_date:
            conds, params = [], []
            if since_date:
                conds.append("entry_date >= ?"); params.append(since_date)
            if until_date:
                conds.append("entry_date <= ?"); params.append(until_date)
            params.append(limit)
            rows = con.execute(
                f"SELECT * FROM entries WHERE {' AND '.join(conds)} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM entries ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def search_entries(q: str, limit: int = 50) -> list[dict[str, Any]]:
    like = f"%{q}%"
    with _conn() as con:
        rows = con.execute(
            """SELECT * FROM entries
               WHERE body LIKE ? OR title LIKE ? OR summary LIKE ? OR tags LIKE ?
               ORDER BY created_at DESC LIMIT ?""",
            (like, like, like, like, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def list_dates() -> list[str]:
    with _conn() as con:
        rows = con.execute(
            "SELECT DISTINCT entry_date FROM entries ORDER BY entry_date DESC"
        ).fetchall()
    return [r["entry_date"] for r in rows]
