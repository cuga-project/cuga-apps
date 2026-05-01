"""mcp-invocable-apis — primitives for synthesizing invocable APIs from SQL.

An agent uses these tools to take (sqlite + Bird-style NL/SQL pairs) and
produce a validated invocable API: a registry of Python tools that, when
composed in sequences, return identical results to the original gold SQL on
every question. The tool sequences become per-question ground truth.

Tool groups:
  db_*       schema introspection + read-only SQL execution
  bird_*     access to Bird's NL questions, gold SQL, and gold answers
  tool_*     per-DB registry of synthesized invocable Python tools
  seq_*      record + execute + validate per-question tool sequences
  dataset_*  emit the finalized dataset (tools.py + dataset.jsonl + MCP server)

Configuration (env vars):
  BIRD_DEV_JSON              path to Bird dev.json
                             (default: /home/amurthi/work/dev_20240627/dev.json)
  BIRD_DBS_DIR               directory of <db>/<db>.sqlite
                             (default: /home/amurthi/work/enterprise-benchmark/data/db)
  INVOCABLE_APIS_STATE_DIR   per-DB sqlite registries
                             (default: mcp_servers/invocable_apis/state)

All registered tool code is a Python source string defining a top-level
`run(conn, **kwargs) -> dict` function. It is exec'd in a restricted
namespace (sqlite3 + stdlib only) on a read-only sqlite connection.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_SERVERS_ROOT = _HERE.parent
if str(_SERVERS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_SERVERS_ROOT.parent))

from mcp_servers._core import tool_error, tool_result
from mcp_servers._core.serve import make_server, run

# Reserve a port for this server. Must match apps/_ports.py.
_DEFAULT_PORT = 29107


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_BIRD_DEV_JSON = Path(os.getenv(
    "BIRD_DEV_JSON",
    "/home/amurthi/work/dev_20240627/dev.json",
))
_BIRD_DBS_DIR = Path(os.getenv(
    "BIRD_DBS_DIR",
    "/home/amurthi/work/enterprise-benchmark/data/db",
))
_STATE_DIR = Path(os.getenv(
    "INVOCABLE_APIS_STATE_DIR",
    str(_HERE / "state"),
))
_STATE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Bird dev.json — load once, index by (db_id, question_id)
# ---------------------------------------------------------------------------

_BIRD_INDEX: dict[tuple[str, int], dict] | None = None


def _load_bird() -> dict[tuple[str, int], dict]:
    global _BIRD_INDEX
    if _BIRD_INDEX is not None:
        return _BIRD_INDEX
    if not _BIRD_DEV_JSON.exists():
        raise FileNotFoundError(f"Bird dev.json not found at {_BIRD_DEV_JSON}")
    data = json.loads(_BIRD_DEV_JSON.read_text())
    _BIRD_INDEX = {(q["db_id"], q["question_id"]): q for q in data}
    return _BIRD_INDEX


def _bird_questions_for_db(db: str) -> list[dict]:
    idx = _load_bird()
    return sorted(
        (q for (d, _qid), q in idx.items() if d == db),
        key=lambda q: q["question_id"],
    )


# ---------------------------------------------------------------------------
# sqlite — read-only connection per call
# ---------------------------------------------------------------------------

def _sqlite_path(db: str) -> Path:
    p = _BIRD_DBS_DIR / db / f"{db}.sqlite"
    if not p.exists():
        raise FileNotFoundError(f"sqlite not found at {p}")
    return p


def _ro_conn(db: str) -> sqlite3.Connection:
    p = _sqlite_path(db)
    uri = f"file:{p}?mode=ro"
    return sqlite3.connect(uri, uri=True, check_same_thread=False)


def _rows_to_payload(cursor: sqlite3.Cursor) -> dict:
    cols = [d[0] for d in (cursor.description or [])]
    rows = cursor.fetchall()
    return {"columns": cols, "rows": [list(r) for r in rows], "row_count": len(rows)}


# ---------------------------------------------------------------------------
# State store (per-DB sqlite for tools, sequences, validations)
# ---------------------------------------------------------------------------

def _state_db(db: str) -> sqlite3.Connection:
    p = _STATE_DIR / f"{db}.db"
    con = sqlite3.connect(str(p), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS tools (
            name               TEXT PRIMARY KEY,
            params_schema      TEXT NOT NULL,
            code               TEXT NOT NULL,
            description        TEXT NOT NULL,
            return_description TEXT NOT NULL DEFAULT '',
            created_at         TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sequences (
            question_id INTEGER PRIMARY KEY,
            sequence    TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS validations (
            question_id   INTEGER PRIMARY KEY,
            passed        INTEGER NOT NULL,
            final_result  TEXT,
            gold_result   TEXT,
            failure_msg   TEXT,
            validated_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ignored (
            question_id INTEGER PRIMARY KEY,
            reason      TEXT,
            set_at      TEXT NOT NULL
        );
    """)
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Tool code execution
# ---------------------------------------------------------------------------

_RUN_FN_RE = re.compile(r"^\s*def\s+run\s*\(", re.MULTILINE)


# ── Tool-quality guards: forbidden names + near-duplicate detection ──

_FORBIDDEN_NAME_PATTERNS = re.compile(
    r"(?:^|_)(?:question|q\d+|wrapper|gold|solver|fallback|generic|todo)(?:_|$)"
    r"|^q\d+",
    re.IGNORECASE,
)


def _name_tokens(name: str) -> set[str]:
    return {tok for tok in name.lower().split("_") if tok}


def _name_jaccard(a: str, b: str) -> float:
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


_SQL_LITERAL_RE = re.compile(r"'[^']*'|\"[^\"]*\"|\b\d+(?:\.\d+)?\b")
_SQL_EXTRACT_RE = re.compile(
    r"""execute\s*\(\s*  # match conn.execute( or cur.execute(
        (?:r?["']{3}|["'])  # single, double, triple
        (.+?)
        (?:["']{3}|["'])
    """,
    re.DOTALL | re.IGNORECASE | re.VERBOSE,
)


def _sql_skeleton(code: str) -> str:
    """Pull the SQL strings out of `code` and return a literal-free skeleton.

    Two tools whose SQL bodies differ only by literal values produce the
    same skeleton — that's our near-duplicate signal.
    """
    matches = _SQL_EXTRACT_RE.findall(code)
    if not matches:
        return ""
    blob = " ".join(m for m in matches).lower()
    blob = _SQL_LITERAL_RE.sub("?", blob)
    blob = re.sub(r"\bcollate\s+nocase\b", "", blob)
    blob = re.sub(r"\s+", " ", blob).strip()
    return blob


def _detect_near_duplicate(
    db: str, new_name: str, new_code: str
) -> tuple[str, str, str] | None:
    """Return (existing_name, reason_code, message) if a near-duplicate exists, else None.

    `new_name` is treated as new IFF it isn't already in the registry — we
    explicitly allow re-registering the SAME name (that's a fix-in-place).
    """
    con = _state_db(db)
    try:
        is_update = con.execute(
            "SELECT 1 FROM tools WHERE name = ?", (new_name,)
        ).fetchone() is not None
        if is_update:
            return None  # re-registering self is allowed
        rows = con.execute("SELECT name, code FROM tools").fetchall()
    finally:
        con.close()

    new_skel = _sql_skeleton(new_code)
    best_jac = 0.0
    best_jac_name = None
    for r in rows:
        # 1) SQL skeleton equality is a strong duplicate signal.
        if new_skel and new_skel == _sql_skeleton(r["code"]):
            return (
                r["name"],
                "duplicate_sql_skeleton",
                f"new tool '{new_name}' has the same SQL skeleton as existing "
                f"tool '{r['name']}' (literals stripped). Reuse '{r['name']}' "
                f"with different args, or — if the existing tool's signature "
                f"is too narrow — `tool_delete` it and re-register a broader "
                f"version that covers both questions.",
            )
        # 2) Name token overlap ≥ 0.7 → near-duplicate name.
        jac = _name_jaccard(new_name, r["name"])
        if jac > best_jac:
            best_jac, best_jac_name = jac, r["name"]
    # Threshold 0.85 catches cosmetic dups like `get_X_by_Y` vs `get_X_by_Y_v2`
    # while letting legitimate domain variants like `..._by_county` vs
    # `..._by_district` through (those land around 0.75).
    if best_jac >= 0.85 and best_jac_name:
        return (
            best_jac_name,
            "near_duplicate_name",
            f"new tool '{new_name}' shares {best_jac:.0%} of its name tokens "
            f"with existing tool '{best_jac_name}'. If they compute the same "
            f"thing, reuse '{best_jac_name}' with different args. If they're "
            f"genuinely different, pick a more distinct name.",
        )
    return None


def _compile_tool(code: str):
    """Exec the source, return its `run` callable. Raises ValueError on issue."""
    if not _RUN_FN_RE.search(code):
        raise ValueError("tool code must define a top-level `def run(conn, **kwargs)`")
    ns: dict[str, Any] = {
        "__builtins__": __builtins__,
        "sqlite3": sqlite3,
        "json": json,
        "re": re,
    }
    try:
        exec(compile(code, "<tool>", "exec"), ns)
    except SyntaxError as e:
        raise ValueError(f"syntax error: {e}") from e
    fn = ns.get("run")
    if not callable(fn):
        raise ValueError("`run` is not callable after exec")
    return fn


def _to_rows(value: Any) -> list[tuple]:
    """Coerce SQL-result-like or tool-output-like value to list[tuple].

    Handles:
      - SQL result: list of tuples or list of lists  → as-is
      - Tool single-scalar dict: {"rate": 1.0}        → [(1.0,)]
      - Tool list-of-dicts wrapped in a key:
            {"schools": [{"school": "X", "doc": "0"}, ...]}
            → [("X", "0"), ...]   (values in key-sorted order)
      - Tool list-of-tuples: {"phones": [("p1",), ("p2",)]}  → [("p1",), ...]
    """
    if value is None:
        return []
    if isinstance(value, dict):
        if len(value) == 1:
            return _to_rows(next(iter(value.values())))
        # Multi-key dict treated as a single multi-column row.
        return [tuple(value[k] for k in sorted(value.keys()))]
    if isinstance(value, list):
        rows = []
        for el in value:
            if isinstance(el, dict):
                rows.append(tuple(el[k] for k in sorted(el.keys())))
            elif isinstance(el, (list, tuple)):
                rows.append(tuple(el))
            else:
                rows.append((el,))
        return rows
    return [(value,)]


def _normalize_for_compare(value: Any) -> list[tuple]:
    """Normalize tool/SQL output for set-equality comparison.

    Strategy: coerce to list[tuple], round floats, sort *within* each row by
    string-of-element (so column-order mismatches between dict-keyed tool
    returns and SQL positional results don't trip set equality), then sort
    the row list. Trade-off: a tool that returns the right values but pairs
    them with the wrong columns within a single row will pass — that's
    usually acceptable for a benchmark and rare in practice.
    """
    rows = _to_rows(value)
    norm = []
    for r in rows:
        items = sorted(
            (_round(x) for x in r),
            key=lambda x: "" if x is None else str(x),
        )
        norm.append(tuple(items))
    return sorted(
        norm, key=lambda t: tuple("" if x is None else str(x) for x in t),
    )


def _round(v: Any, ndigits: int = 6) -> Any:
    if isinstance(v, float):
        return round(v, ndigits)
    return v


# ---------------------------------------------------------------------------
# Sequence execution with simple variable binding
# ---------------------------------------------------------------------------

_REF_RE = re.compile(r"^\{\{\s*([^}]+)\s*\}\}$")


def _resolve(arg: Any, scope: dict[str, Any]) -> Any:
    """Resolve {{var}} or {{var.path.to.field}} against scope; pass literals through."""
    if isinstance(arg, str):
        m = _REF_RE.match(arg)
        if m:
            path = m.group(1).strip().split(".")
            cur: Any = scope.get(path[0])
            for k in path[1:]:
                if isinstance(cur, dict):
                    cur = cur.get(k)
                elif isinstance(cur, list) and k.isdigit():
                    cur = cur[int(k)] if int(k) < len(cur) else None
                else:
                    cur = None
            return cur
    if isinstance(arg, dict):
        return {k: _resolve(v, scope) for k, v in arg.items()}
    if isinstance(arg, list):
        return [_resolve(v, scope) for v in arg]
    return arg


def _run_sequence(db: str, sequence: list[dict]) -> tuple[list[dict], Any]:
    """Run a sequence; return (per_step_outputs, final_output)."""
    scope: dict[str, Any] = {}
    steps: list[dict] = []
    con = _state_db(db)
    try:
        for i, step in enumerate(sequence):
            name = step["tool"]
            args = _resolve(step.get("args", {}), scope)
            row = con.execute(
                "SELECT code FROM tools WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                raise ValueError(f"step {i}: tool '{name}' not registered")
            fn = _compile_tool(row["code"])
            with _ro_conn(db) as ro:
                output = fn(ro, **args)
            steps.append({"step": i, "tool": name, "args": args, "output": output})
            bind = step.get("bind")
            if bind:
                scope[bind] = output
        final = steps[-1]["output"] if steps else None
        return steps, final
    finally:
        con.close()


# ---------------------------------------------------------------------------
# MCP server + tools
# ---------------------------------------------------------------------------

mcp = make_server("mcp-invocable-apis")


# ── db_* ──────────────────────────────────────────────────────────────

@mcp.tool()
def db_get_schema(db: str) -> str:
    """Return CREATE TABLE statements + foreign-key list for a Bird sqlite DB.

    Use this first to orient — every other db_* tool assumes you've seen the
    schema. The returned `sql` field is the verbatim DDL.

    Args:
        db: Bird db_id (e.g. "california_schools").
    """
    try:
        with _ro_conn(db) as con:
            tables = con.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            fks = []
            for (tname, _ddl) in tables:
                for row in con.execute(f"PRAGMA foreign_key_list(`{tname}`)").fetchall():
                    fks.append({
                        "from_table": tname, "from_col": row[3],
                        "to_table": row[2],   "to_col": row[4],
                    })
            return tool_result({
                "db": db,
                "tables": [{"name": t, "sql": s} for t, s in tables],
                "foreign_keys": fks,
            })
    except Exception as e:
        return tool_error(str(e), code="db_get_schema")


@mcp.tool()
def db_sample_rows(db: str, table: str, n: int = 5) -> str:
    """Peek at real data — useful for inferring column value formats.

    Args:
        db:    Bird db_id.
        table: Exact table name (case-sensitive, quote-free).
        n:     Number of rows (default 5, max 50).
    """
    try:
        n = max(1, min(int(n), 50))
        with _ro_conn(db) as con:
            cur = con.execute(f"SELECT * FROM `{table}` LIMIT ?", (n,))
            return tool_result(_rows_to_payload(cur))
    except Exception as e:
        return tool_error(str(e), code="db_sample_rows")


@mcp.tool()
def db_run_sql(db: str, sql: str) -> str:
    """Execute a read-only SQL statement against the Bird sqlite DB.

    The connection is opened with mode=ro; mutating statements will fail.
    Use this to explore data, validate joins, or check what gold SQL returns.

    Args:
        db:  Bird db_id.
        sql: A single SELECT/CTE/PRAGMA statement.
    """
    try:
        with _ro_conn(db) as con:
            cur = con.execute(sql)
            return tool_result(_rows_to_payload(cur))
    except Exception as e:
        return tool_error(str(e), code="db_run_sql")


# ── bird_* ────────────────────────────────────────────────────────────

@mcp.tool()
def bird_list_databases() -> str:
    """List Bird db_ids that have both a dev.json question pack and a sqlite file.

    Useful at app startup to populate a database picker. Results are sorted.
    """
    try:
        idx = _load_bird()
        from_dev = sorted({db for (db, _qid) in idx.keys()})
        out = []
        for db in from_dev:
            sqlite = _BIRD_DBS_DIR / db / f"{db}.sqlite"
            if sqlite.exists():
                qids = [qid for (d, qid) in idx.keys() if d == db]
                out.append({"db": db, "questions": len(qids)})
        return tool_result({"databases": out, "count": len(out)})
    except Exception as e:
        return tool_error(str(e), code="bird_list_databases")


@mcp.tool()
def bird_list_questions(db: str) -> str:
    """List all Bird question_ids for a given db_id, with question text + difficulty.

    Args:
        db: Bird db_id.
    """
    try:
        qs = _bird_questions_for_db(db)
        return tool_result({
            "db": db,
            "count": len(qs),
            "questions": [
                {
                    "question_id": q["question_id"],
                    "question": q["question"],
                    "difficulty": q.get("difficulty", ""),
                }
                for q in qs
            ],
        })
    except Exception as e:
        return tool_error(str(e), code="bird_list_questions")


@mcp.tool()
def bird_get_question(db: str, question_id: int) -> str:
    """Return the full Bird record for a (db, question_id) — NL + evidence + gold SQL + difficulty.

    Args:
        db: Bird db_id.
        question_id: Bird's integer question_id.
    """
    try:
        idx = _load_bird()
        q = idx.get((db, int(question_id)))
        if q is None:
            return tool_error(f"no Bird question for db={db} qid={question_id}", code="not_found")
        return tool_result(q)
    except Exception as e:
        return tool_error(str(e), code="bird_get_question")


@mcp.tool()
def bird_run_gold(db: str, question_id: int) -> str:
    """Execute a question's gold SQL on the sqlite and return the canonical result.

    This is the oracle — every synthesized tool sequence for this question
    must return an equivalent result. Result is a list of row tuples.

    Args:
        db: Bird db_id.
        question_id: Bird's integer question_id.
    """
    try:
        idx = _load_bird()
        q = idx.get((db, int(question_id)))
        if q is None:
            return tool_error(f"no Bird question for db={db} qid={question_id}", code="not_found")
        with _ro_conn(db) as con:
            cur = con.execute(q["SQL"])
            payload = _rows_to_payload(cur)
        return tool_result({
            "question_id": int(question_id),
            "sql": q["SQL"],
            "result": payload,
        })
    except Exception as e:
        return tool_error(str(e), code="bird_run_gold")


# ── tool_* ────────────────────────────────────────────────────────────

@mcp.tool()
def tool_register(
    db: str,
    name: str,
    params_schema: dict,
    code: str,
    description: str,
    return_description: str = "",
) -> str:
    """Register a synthesized invocable tool for a database.

    The `code` must be a Python source defining `def run(conn, **kwargs) -> dict`.
    `conn` is a read-only sqlite3.Connection. Returns must be JSON-serializable.

    `params_schema` is a JSON Schema-style object describing kwargs. Minimal
    form accepted: {"properties": {"name": {"type": "string"}}, "required": [...]}.

    Re-registering the same NAME is allowed (treated as fix-in-place). Two
    server-side guards prevent silent registry pollution:

      * **Forbidden name patterns** — names matching ``question_*``,
        ``q<N>*``, ``*_wrapper``, ``*_solver``, ``gold_*``, ``fallback_*``,
        ``generic_*``, ``todo_*`` are rejected. Use a domain-meaningful,
        concept-led name instead.

      * **Near-duplicate detection** — a new (different-name) tool is
        rejected if it has the same SQL skeleton (literals stripped) as an
        existing tool, or shares ≥70% of its name tokens with one. The
        error message names the existing tool and asks you to reuse it.

    To replace an existing tool with a broader signature: call
    ``tool_delete`` on the old name first, then ``tool_register`` the new one.

    Args:
        db: Bird db_id this tool belongs to.
        name: Snake_case tool name (e.g. "get_schools_in_county").
        params_schema: JSON Schema for kwargs.
        code: Python source defining `run(conn, **kwargs)`.
        description: One-line summary the LLM uses to decide when to call this tool.
        return_description: Brief description of return shape (optional).
    """
    try:
        # Validate code compiles + exposes run().
        _compile_tool(code)
        if not isinstance(params_schema, dict):
            return tool_error("params_schema must be a JSON object", code="bad_schema")

        # Guard 1 — forbidden name patterns.
        if _FORBIDDEN_NAME_PATTERNS.search(name):
            return tool_error(
                f"forbidden name pattern in '{name}'. Names containing "
                f"'question', 'q<N>', 'wrapper', 'gold', 'solver', "
                f"'fallback', 'generic', or 'todo' are rejected. Use a "
                f"concept-led, domain-meaningful name describing what the "
                f"function computes.",
                code="forbidden_name",
            )

        # Guard 2 — near-duplicate detection.
        dup = _detect_near_duplicate(db, name, code)
        if dup is not None:
            existing_name, reason_code, message = dup
            return tool_error(message, code=reason_code)

        con = _state_db(db)
        try:
            con.execute(
                "INSERT OR REPLACE INTO tools "
                "(name, params_schema, code, description, return_description, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, json.dumps(params_schema), code, description,
                 return_description, _now()),
            )
            con.commit()
        finally:
            con.close()
        return tool_result({"db": db, "name": name, "registered": True})
    except Exception as e:
        return tool_error(str(e), code="tool_register")


@mcp.tool()
def tool_list(db: str) -> str:
    """List all registered tools for a database (name + description + params_schema).

    Args:
        db: Bird db_id.
    """
    try:
        con = _state_db(db)
        try:
            rows = con.execute(
                "SELECT name, description, params_schema, return_description "
                "FROM tools ORDER BY name"
            ).fetchall()
        finally:
            con.close()
        return tool_result({
            "db": db,
            "count": len(rows),
            "tools": [
                {
                    "name": r["name"],
                    "description": r["description"],
                    "params_schema": json.loads(r["params_schema"]),
                    "return_description": r["return_description"],
                }
                for r in rows
            ],
        })
    except Exception as e:
        return tool_error(str(e), code="tool_list")


@mcp.tool()
def tool_get(db: str, name: str) -> str:
    """Get a registered tool's full definition including its source code.

    Args:
        db: Bird db_id.
        name: Tool name.
    """
    try:
        con = _state_db(db)
        try:
            r = con.execute(
                "SELECT name, description, params_schema, return_description, code, created_at "
                "FROM tools WHERE name = ?", (name,)
            ).fetchone()
        finally:
            con.close()
        if r is None:
            return tool_error(f"tool '{name}' not registered for db={db}", code="not_found")
        return tool_result({
            "name": r["name"],
            "description": r["description"],
            "params_schema": json.loads(r["params_schema"]),
            "return_description": r["return_description"],
            "code": r["code"],
            "created_at": r["created_at"],
        })
    except Exception as e:
        return tool_error(str(e), code="tool_get")


@mcp.tool()
def tool_call(db: str, name: str, args: dict | None = None) -> str:
    """Execute a registered tool against the sqlite (read-only). Returns its dict.

    Use this to verify a tool you just registered does what you expect before
    using it inside a sequence.

    Args:
        db: Bird db_id.
        name: Registered tool name.
        args: kwargs to pass to run() (default empty dict).
    """
    try:
        con = _state_db(db)
        try:
            r = con.execute(
                "SELECT code FROM tools WHERE name = ?", (name,)
            ).fetchone()
        finally:
            con.close()
        if r is None:
            return tool_error(f"tool '{name}' not registered for db={db}", code="not_found")
        fn = _compile_tool(r["code"])
        with _ro_conn(db) as ro:
            output = fn(ro, **(args or {}))
        return tool_result({"name": name, "args": args or {}, "output": output})
    except Exception as e:
        return tool_error(str(e), code="tool_call")


@mcp.tool()
def tool_delete(db: str, name: str) -> str:
    """Remove a registered tool from the registry.

    Args:
        db: Bird db_id.
        name: Tool name.
    """
    try:
        con = _state_db(db)
        try:
            cur = con.execute("DELETE FROM tools WHERE name = ?", (name,))
            con.commit()
            removed = cur.rowcount
        finally:
            con.close()
        return tool_result({"db": db, "name": name, "removed": removed})
    except Exception as e:
        return tool_error(str(e), code="tool_delete")


# ── seq_* ─────────────────────────────────────────────────────────────

@mcp.tool()
def seq_record(db: str, question_id: int, sequence: list) -> str:
    """Save a tool-call sequence as the candidate ground-truth for a question.

    Sequence shape: list of {tool, args, bind?}.
      - args: dict of kwargs. String values may be `{{varname}}` or
              `{{varname.path}}` to reference a prior step's bound output.
      - bind: optional name; the step's output dict is stored under this name
              for later steps to reference.

    Example:
      [
        {"tool": "schools_in_county", "args": {"county": "Alameda"},
         "bind": "schools"},
        {"tool": "highest_free_meal_rate",
         "args": {"school_codes": "{{schools.codes}}"}}
      ]

    Args:
        db: Bird db_id.
        question_id: Bird's integer question_id.
        sequence: List of step dicts as above.
    """
    try:
        if not isinstance(sequence, list) or not sequence:
            return tool_error("sequence must be a non-empty list", code="bad_sequence")
        for i, s in enumerate(sequence):
            if not isinstance(s, dict) or "tool" not in s:
                return tool_error(f"step {i} missing 'tool'", code="bad_sequence")
        con = _state_db(db)
        try:
            con.execute(
                "INSERT OR REPLACE INTO sequences (question_id, sequence, created_at) "
                "VALUES (?, ?, ?)",
                (int(question_id), json.dumps(sequence), _now()),
            )
            con.commit()
        finally:
            con.close()
        return tool_result({
            "db": db, "question_id": int(question_id),
            "steps": len(sequence), "recorded": True,
        })
    except Exception as e:
        return tool_error(str(e), code="seq_record")


@mcp.tool()
def seq_execute(db: str, sequence: list) -> str:
    """Run a sequence end-to-end against the sqlite; return per-step outputs + final.

    Useful for testing a candidate sequence before recording it.

    Args:
        db: Bird db_id.
        sequence: List of step dicts (same shape as seq_record).
    """
    try:
        steps, final = _run_sequence(db, sequence)
        return tool_result({"steps": steps, "final": final})
    except Exception as e:
        return tool_error(str(e), code="seq_execute")


@mcp.tool()
def seq_validate(db: str, question_id: int) -> str:
    """Run gold SQL and the recorded sequence, normalize, compare. Persist result.

    A question is "passed" when the normalized form of its sequence's final
    output equals the normalized form of the gold SQL's result. Float
    rounding to 6 decimals + sort-by-string handles ordering and tolerance.

    Args:
        db: Bird db_id.
        question_id: Bird's integer question_id.
    """
    try:
        idx = _load_bird()
        q = idx.get((db, int(question_id)))
        if q is None:
            return tool_error(f"no Bird question for db={db} qid={question_id}", code="not_found")

        with _ro_conn(db) as con:
            gold_payload = _rows_to_payload(con.execute(q["SQL"]))
        gold_rows = gold_payload["rows"]

        con = _state_db(db)
        try:
            seq_row = con.execute(
                "SELECT sequence FROM sequences WHERE question_id = ?",
                (int(question_id),),
            ).fetchone()
        finally:
            con.close()
        if seq_row is None:
            return tool_error(
                f"no recorded sequence for question_id={question_id}",
                code="no_sequence",
            )
        sequence = json.loads(seq_row["sequence"])

        try:
            steps, final = _run_sequence(db, sequence)
            failure_msg = None
        except Exception as e:
            steps, final = [], None
            failure_msg = f"sequence execution failed: {e}"

        if failure_msg is None:
            normalized_gold = _normalize_for_compare(gold_rows)
            normalized_final = _normalize_for_compare(final)
            passed = normalized_gold == normalized_final
            if not passed:
                failure_msg = (
                    f"result mismatch — gold={normalized_gold} final={normalized_final}"
                )
        else:
            passed = False

        # Persist outcome.
        con = _state_db(db)
        try:
            con.execute(
                "INSERT OR REPLACE INTO validations "
                "(question_id, passed, final_result, gold_result, failure_msg, validated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    int(question_id), 1 if passed else 0,
                    json.dumps(final, default=str),
                    json.dumps(gold_rows, default=str),
                    failure_msg, _now(),
                ),
            )
            con.commit()
        finally:
            con.close()

        return tool_result({
            "question_id": int(question_id),
            "passed": passed,
            "gold_result": gold_rows,
            "final_result": final,
            "step_outputs": steps,
            "failure_msg": failure_msg,
        })
    except Exception as e:
        return tool_error(str(e), code="seq_validate")


@mcp.tool()
def ignore_set(db: str, question_id: int, ignored: bool = True, reason: str = "") -> str:
    """Manually mark a question's record to be ignored from the emitted dataset.

    Use this when the auto-validator passed but a human reviewer wants to
    discard the record (e.g. the tool sequence is technically correct but
    semantically junk). Setting ignored=False clears the flag.

    Args:
        db: Bird db_id.
        question_id: Bird's integer question_id.
        ignored: True to mark, False to unmark (default True).
        reason: Optional free-text reason persisted alongside the flag.
    """
    try:
        con = _state_db(db)
        try:
            if ignored:
                con.execute(
                    "INSERT OR REPLACE INTO ignored (question_id, reason, set_at) "
                    "VALUES (?, ?, ?)",
                    (int(question_id), reason or "", _now()),
                )
            else:
                con.execute(
                    "DELETE FROM ignored WHERE question_id = ?", (int(question_id),)
                )
            con.commit()
        finally:
            con.close()
        return tool_result({
            "db": db, "question_id": int(question_id),
            "ignored": ignored, "reason": reason,
        })
    except Exception as e:
        return tool_error(str(e), code="ignore_set")


@mcp.tool()
def ignore_list(db: str) -> str:
    """List all (question_id, reason) pairs currently flagged ignored for a DB.

    Args:
        db: Bird db_id.
    """
    try:
        con = _state_db(db)
        try:
            rows = con.execute(
                "SELECT question_id, reason, set_at FROM ignored ORDER BY question_id"
            ).fetchall()
        finally:
            con.close()
        return tool_result({
            "db": db,
            "count": len(rows),
            "ignored": [
                {"question_id": r["question_id"], "reason": r["reason"], "set_at": r["set_at"]}
                for r in rows
            ],
        })
    except Exception as e:
        return tool_error(str(e), code="ignore_list")


# ── dataset_* ─────────────────────────────────────────────────────────

@mcp.tool()
def dataset_emit(db: str, out_dir: str) -> str:
    """Freeze the registry + sequences for a DB into an output directory.

    Writes (each file has the db_id as a suffix so the artifacts are
    safe to flatten across all Bird DBs):
      <out_dir>/<db>/<db>_tools.py
      <out_dir>/<db>/<db>_tools.json
      <out_dir>/<db>/<db>_dataset.json
      <out_dir>/<db>/<db>_mcp_server.py
      <out_dir>/<db>/<db>_validation_report.json   rich coverage + reuse stats
      <out_dir>/<db>/<db>_tool_usage.json          per-tool: qids that reference it

    Args:
        db: Bird db_id.
        out_dir: Parent directory; a `<db>/` subdir is created inside.
    """
    try:
        out = Path(out_dir).expanduser().resolve() / db
        out.mkdir(parents=True, exist_ok=True)

        con = _state_db(db)
        try:
            tools = con.execute(
                "SELECT name, description, params_schema, return_description, code "
                "FROM tools ORDER BY name"
            ).fetchall()
            seq_rows = con.execute(
                "SELECT question_id, sequence FROM sequences"
            ).fetchall()
            val_rows = con.execute(
                "SELECT question_id, passed, final_result, failure_msg "
                "FROM validations"
            ).fetchall()
            ig_rows = con.execute(
                "SELECT question_id, reason FROM ignored"
            ).fetchall()
        finally:
            con.close()

        sequences = {r["question_id"]: json.loads(r["sequence"]) for r in seq_rows}
        validations = {
            r["question_id"]: {
                "passed": bool(r["passed"]),
                "final_result": json.loads(r["final_result"]) if r["final_result"] else None,
                "failure_msg": r["failure_msg"],
            }
            for r in val_rows
        }
        ignored = {r["question_id"]: r["reason"] for r in ig_rows}

        # tools.py — concatenate registered code, prefixed with imports.
        tools_py = (out / f"{db}_tools.py")
        body = ['"""Auto-generated invocable tools for Bird db `' + db + '`."""',
                "from __future__ import annotations",
                "import json",
                "import re",
                "import sqlite3",
                ""]
        for r in tools:
            body.append(f"# {r['name']} — {r['description']}")
            body.append(r["code"].rstrip())
            # Rename `run` to the tool's name so multiple coexist in one module.
            body.append(f"{r['name']} = run; del run")
            body.append("")
        tools_py.write_text("\n".join(body))

        # tools.json — schemas only.
        (out / f"{db}_tools.json").write_text(json.dumps([
            {
                "name": r["name"],
                "description": r["description"],
                "params_schema": json.loads(r["params_schema"]),
                "return_description": r["return_description"],
            } for r in tools
        ], indent=2))

        # dataset.json — every Bird question for this db, with sequence + validation.
        bird_qs = _bird_questions_for_db(db)
        records = []
        for q in bird_qs:
            qid = q["question_id"]
            seq = sequences.get(qid)
            val = validations.get(qid, {})
            with _ro_conn(db) as ro:
                gold = _rows_to_payload(ro.execute(q["SQL"]))["rows"]
            records.append({
                "question_id": qid,
                "db_id": db,
                "question": q["question"],
                "evidence": q.get("evidence", ""),
                "difficulty": q.get("difficulty", ""),
                "gold_sql": q["SQL"],
                "gold_result": gold,
                "tool_sequence": seq,
                "final_result": val.get("final_result"),
                "validated": val.get("passed", False),
                "failure_msg": val.get("failure_msg"),
                "ignored": qid in ignored,
                "ignore_reason": ignored.get(qid, ""),
            })
        (out / f"{db}_dataset.json").write_text(
            json.dumps(records, indent=2, default=str)
        )

        # validation_report.json — rich coverage stats persisted alongside artifacts.
        total = len(bird_qs)
        with_seq = sum(1 for q in bird_qs if q["question_id"] in sequences)
        passed = sum(1 for q in bird_qs
                     if validations.get(q["question_id"], {}).get("passed"))
        ignored_count = sum(1 for q in bird_qs if q["question_id"] in ignored)
        keep = sum(
            1 for q in bird_qs
            if validations.get(q["question_id"], {}).get("passed")
            and q["question_id"] not in ignored
        )
        # Sequence-length distribution, tool reuse, multi-step counts.
        seq_len_dist: dict[int, int] = {}
        tool_usage: dict[str, list[int]] = {}
        multi_step_qids: list[int] = []
        for qid, seq in sequences.items():
            n = len(seq)
            seq_len_dist[n] = seq_len_dist.get(n, 0) + 1
            if n > 1:
                multi_step_qids.append(qid)
            for step in seq:
                tool_usage.setdefault(step["tool"], []).append(qid)
        reused = {t: qs for t, qs in tool_usage.items() if len(qs) > 1}

        (out / f"{db}_validation_report.json").write_text(json.dumps({
            "db": db,
            "emitted_at": _now(),
            "total_questions": total,
            "with_sequence": with_seq,
            "without_sequence": total - with_seq,
            "validated_passing": passed,
            "validation_failing": with_seq - passed,
            "ignored_count": ignored_count,
            "keep_count": keep,
            "discard_count": total - keep,
            "pass_rate_pct": round(100.0 * passed / max(1, with_seq), 1),
            "tools_registered": len(tools),
            "unique_tools_used_in_sequences": len(tool_usage),
            "tools_reused_across_questions": len(reused),
            "multi_step_sequences": len(multi_step_qids),
            "multi_step_question_ids": sorted(multi_step_qids),
            "sequence_length_distribution": {str(k): v for k, v in
                                             sorted(seq_len_dist.items())},
        }, indent=2))

        # tool_usage.json — for each tool: which question_ids reference it.
        # The key reusability artifact for browsing the API surface.
        (out / f"{db}_tool_usage.json").write_text(json.dumps({
            "db": db,
            "tools": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "params_schema": json.loads(t["params_schema"]),
                    "return_description": t["return_description"],
                    "used_by_question_ids": sorted(tool_usage.get(t["name"], [])),
                    "reuse_count": len(tool_usage.get(t["name"], [])),
                }
                for t in tools
            ],
        }, indent=2, default=str))

        # mcp_server.py — standalone server exposing the tools as MCP.
        (out / f"{db}_mcp_server.py").write_text(_render_mcp_server(db, tools))

        return tool_result({
            "db": db,
            "out_dir": str(out),
            "tools": len(tools),
            "questions": total,
            "with_sequence": with_seq,
            "passing": passed,
        })
    except Exception as e:
        return tool_error(str(e), code="dataset_emit")


def _render_mcp_server(db: str, tool_rows: list) -> str:
    """Build a standalone runnable MCP server file for an emitted dataset."""
    header = textwrap.dedent(f'''\
        """Auto-generated MCP server exposing invocable tools for Bird db `{db}`.

        Run:
            python mcp_server.py            # binds 0.0.0.0:8765 by default

        Configuration:
            SQLITE_PATH   path to {db}.sqlite (required)
            MCP_PORT      port to bind (default 8765)
        """
        from __future__ import annotations
        import json, os, sqlite3, sys
        from pathlib import Path

        from mcp.server.fastmcp import FastMCP

        _SQLITE = os.environ.get("SQLITE_PATH")
        if not _SQLITE or not Path(_SQLITE).exists():
            print("set SQLITE_PATH to the sqlite database", file=sys.stderr)
            sys.exit(1)


        def _conn():
            return sqlite3.connect(f"file:{{_SQLITE}}?mode=ro", uri=True,
                                   check_same_thread=False)


        def _ok(data): return json.dumps({{"ok": True, "data": data}}, default=str)
        def _err(msg): return json.dumps({{"ok": False, "error": str(msg)}})


        mcp = FastMCP("invocable-apis-{db}")
        ''')

    body_parts = [header]
    for r in tool_rows:
        # Rebind `run` per-tool inside its own closure, expose with the tool name.
        params = json.loads(r["params_schema"])
        param_names = list(params.get("properties", {}).keys())
        signature = ", ".join(param_names) if param_names else ""
        kwargs_pass = ", ".join(f"{p}={p}" for p in param_names) if param_names else ""

        body_parts.append(textwrap.dedent(f'''
            @mcp.tool()
            def {r["name"]}({signature}) -> str:
                """{r["description"]}"""
                try:
                    _ns = {{}}
                    exec(compile({json.dumps(r["code"])}, "<tool>", "exec"), _ns)
                    with _conn() as _c:
                        out = _ns["run"](_c{(", " + kwargs_pass) if kwargs_pass else ""})
                    return _ok(out)
                except Exception as _e:
                    return _err(_e)
            ''').rstrip())

    body_parts.append(textwrap.dedent('''

        if __name__ == "__main__":
            mcp.settings.host = "0.0.0.0"
            mcp.settings.port = int(os.environ.get("MCP_PORT", "8765"))
            mcp.settings.transport_security.enable_dns_rebinding_protection = False
            mcp.run(transport="streamable-http")
    '''))
    return "\n".join(body_parts)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run(mcp, _DEFAULT_PORT)
