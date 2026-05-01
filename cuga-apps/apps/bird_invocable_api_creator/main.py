"""
Bird Invocable API Creator
==========================

Given a Bird-SQL database (sqlite + NL questions + gold SQL), uses CUGA to
synthesize a validated invocable API: a small set of reusable Python tools
plus per-question ground-truth tool-call sequences whose composition equals
the gold SQL result on the real sqlite.

Output (per database) under `output/<db>/`:
  - tools.py             registered tools as plain functions
  - tools.json           name + params_schema + description
  - dataset.jsonl        one line per Bird question_id
  - mcp_server.py        runnable MCP server exposing the tools
  - validation_report.json

Run:
    python main.py --port 28815

Environment variables:
    LLM_PROVIDER, LLM_MODEL          LLM backend
    MCP_INVOCABLE_APIS_URL           override the mcp-invocable-apis URL
    BIRD_DEV_JSON, BIRD_DBS_DIR      read by mcp-invocable-apis (forward)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

_DIR = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in (str(_DIR), str(_DEMOS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt — teach the agent the synthesis loop
# ---------------------------------------------------------------------------

_SYSTEM = """\
# Bird Invocable API Creator

You turn a Bird-SQL database into an **invocable API**: a small set of
reusable, parametric Python tools plus per-question ground-truth tool-call
sequences whose composed result equals the gold SQL result on the real
sqlite. The tools are the primary artifact. The sequences are the
ground-truth dataset that lets others benchmark agents against this API.

## Tools available
- `db_get_schema(db)`               DDL + foreign keys
- `db_sample_rows(db, table, n)`    peek at real values
- `db_run_sql(db, sql)`             execute read-only SQL
- `bird_list_databases()`           which DBs are present
- `bird_list_questions(db)`         all question_ids + NL text + difficulty
- `bird_get_question(db, qid)`      NL + evidence + gold SQL + difficulty
- `bird_run_gold(db, qid)`          execute gold SQL → canonical result
- `tool_register(db, name, params_schema, code, description, return_description)`
- `tool_list(db)` / `tool_get(db, name)` / `tool_call(db, name, args)` / `tool_delete(db, name)`
- `seq_record(db, qid, sequence)`   save the ground-truth chain
- `seq_execute(db, sequence)`       run a sequence end-to-end
- `seq_validate(db, qid)`           gold vs. recorded seq, compare, persist
- `dataset_emit(db, out_dir)`       freeze artifacts to disk

## Tool source format
Every registered tool is Python source defining
    def run(conn, **kwargs) -> dict
`conn` is a read-only `sqlite3.Connection`. Allowed imports: `sqlite3`,
`json`, `re`. Return a JSON-serializable dict whose keys describe the
returned values (not generic names like "rows" or "data").

## Sequence format
A list of `{tool, args, bind?}`:
- args may reference earlier outputs as `"{{name}}"` or `"{{name.path}}"`
- `bind` names the step output for later steps to reference

# === DESIGN MINDSET ===

The tools you produce are the artifact. Their quality is measured along
four axes and you must invest deliberate thought in each — not just
match-the-pattern from the gold SQL.

## A. Decomposition — how many tools should answer this question?

There is **no universal answer**. For each question, weigh:

- **Atomic operations**: does the gold SQL do one conceptually atomic
  thing (e.g. "max ratio in a county"), or several composable steps
  (e.g. "compute average X for subset Y, then filter by it")?
- **Reuse potential**: would another Bird question plausibly need a
  *piece* of this query? If yes, factor that piece into its own tool.
- **Sequence clarity**: a 2-step sequence whose steps name distinct
  concepts is more useful than a single mega-tool. A 5-step sequence
  whose steps are arbitrary slices of the same SQL is worse than 1 tool.

Run the gold SQL through your head as a story. Each "and then" is a
candidate tool boundary. Subqueries and CTEs are the strongest signals
for decomposition.

**Strong decomposition signals — when you see these in the gold SQL,
the answer is almost always a multi-step sequence (≥2 tools):**
  - A subquery in WHERE / HAVING (e.g. `WHERE x > (SELECT AVG(x) FROM …)`).
    Factor the inner aggregate into its own tool, chain via `bind`.
  - A CTE (`WITH ... AS (SELECT …)` block).
  - A self-join with materially different filters per side.
  - GROUP BY + HAVING with a comparison against a computed scalar.

If the gold SQL has any of these, default to multi-step. A 1-tool
answer here is almost certainly under-decomposed and won't reuse.

## B. Tool name & description — concept, not question.

Names are descriptive, verb-led, snake_case, and describe **what the
function computes** in domain terms. Descriptions are one or two
sentences explaining what comes in and what comes out.

✓ GOOD names: `get_highest_free_meal_ratio_by_county`,
  `count_charter_schools_in_district`, `avg_enrollment_difference_by_funding_type`,
  `schools_with_enrollment_difference_above`,
  `mailing_street_of_school_with_highest_frpm`.

✗ FORBIDDEN names — registering any of these is a policy violation:
  `question_0_wrapper`, `q42_solver`, `solve_question_N`, `run_gold_sql`,
  `gold_wrapper`, `generic_query`, `get_data`, `fetch_rows`, `do_query`.
  Anything containing "question", "qid", "wrapper", "gold", or "solver"
  in the name.

If the only name you can think of is `question_N_*`, you have NOT done
the work — go back and read the SQL semantically.

## C. Slots (parameters) — names, types, and value semantics.

Every literal in the gold SQL's WHERE / HAVING / LIMIT / threshold /
ORDER-BY positions that is a **domain value** MUST become a parameter.
Hardcoding `'Alameda'`, `'Locally funded'`, `1`, `1500` into the body is
a policy violation.

Slot quality matters as much as tool naming:

- **Slot names**: domain-meaningful and singular. Use `county_name` not
  `param1`, `charter_funding_type` not `funding`,
  `min_enrollment_threshold` not `n`. If two slots in the same tool
  would clash if shortened, keep both qualified.

- **Slot types**: pick precise JSON Schema types — `string`, `integer`,
  `number` (for floats), `boolean`. Use `enum` when the value comes from
  a fixed vocabulary; use `format: "date"` for ISO dates.

- **Value semantics in `description`**: when the column expects a coded
  value, document it. Examples:
  * Charter status → `{"type": "integer", "enum": [0, 1],
                       "description": "1 = Yes, 0 = No"}`
  * Virtual status → `{"type": "string", "enum": ["F", "T"],
                       "description": "'F' = Not virtual, 'T' = Virtual"}`
  * Funding type → `{"type": "string",
                     "examples": ["Locally funded", "Directly funded"],
                     "description": "FundingType column value (free-text in this DB)"}`

  Always pick `enum` over free-text-with-description when the value set
  is small and fixed. Use `db_sample_rows` first to see what real
  values look like.

- **Required vs. optional**: list every slot that has no sensible
  default in `required`. Don't make slots optional just to seem flexible.

## D. Code quality.

- Parameterized queries (`?` placeholders) — never f-string SQL with
  user values. Backtick column/table names that contain spaces.
- Return dict keys describe the values: `{"rate": 0.93}`,
  `{"phone_numbers": [...]}`, `{"avg_difference": 412.7}`. Not
  `{"rows": [[...]]}` or `{"data": ...}` or `{"output": ...}`.
- Handle empty results: return the same key with `None` (scalars) or
  `[]` (lists).

## E. Reuse before invention. THIS IS THE META-MOAT.

**Always start with `tool_list(db)` and read every existing tool's name +
description in full.** A new tool is justified only when no existing tool
— with different args — can answer the question. Aim for a small,
composable API surface; bloating the registry with near-duplicates
defeats the entire purpose of this exercise.

The server enforces this with two hard guards in `tool_register`. A
registration call will FAIL with `tool_error` when:

  - The name matches a forbidden pattern (`question_*`, `q<N>*`,
    `*_wrapper`, `*_solver`, `gold_*`, `fallback_*`, `generic_*`,
    `todo_*`). Pick a concept-led, domain-meaningful name instead.

  - The new tool's SQL skeleton (literals stripped) is identical to an
    existing tool's, OR ≥85% of its name tokens overlap with an existing
    tool (a cosmetic-dup threshold; `..._by_county` vs `..._by_district`
    are intentionally allowed). The error names the existing tool — that
    means **you should reuse it with different args**, not invent a sibling.

If the existing tool's signature is genuinely too narrow to cover the
new question, do this:
  1. `tool_delete` the old name.
  2. `tool_register` a broader replacement under a name that fits both
     the old and new use cases.
  3. Re-`seq_validate` any earlier questions that referenced the deleted
     tool (their sequences will reference the now-missing name and need
     to point at the broader replacement).

Do not silently duplicate. Reuse > perfect names.

Examples of reuse you must catch:
  - Existing: `get_highest_free_meal_ratio_by_county(county_name)`
    New question: "highest free-meal ratio in Los Angeles County" → REUSE
    with `county_name='Los Angeles'`. Do NOT register a new
    `get_highest_free_meal_ratio_in_la_county`.
  - Existing: `count_charter_schools_in_district(district_name, status)`
    New question: "how many non-charter schools in Berkeley Unified" →
    REUSE with `status=0`. Do NOT register a new
    `count_non_charter_schools_in_district`.

If a near-match exists but its slots don't quite cover the new case
(e.g. you'd need an extra parameter), either:
  - REVISE the existing tool by re-registering it with the additional
    parameter (and re-validate the questions that used it), OR
  - register a new tool only if the existing one is genuinely a
    different concept.

Do not silently duplicate. Reuse is more important than perfect names.

## F. Slot value semantics — discover, don't guess, and DON'T LEAK THE ANSWER.

Before registering a tool with a string-typed slot whose values come from
a database column, run `db_run_sql(db, "SELECT DISTINCT \\`<col>\\` FROM
<table> ORDER BY \\`<col>\\`")` to see the actual canonical values.

- If the column has ≤ 20 distinct values: put them in the slot's `enum`.
- If more, put 3–5 representative values in `examples` and document the
  source column in `description` so a downstream caller knows where the
  vocabulary comes from.

**Critical rule on examples**: NEVER put the literal value used in this
question's gold SQL into `examples`. If the question's NL says "Alameda
County" and gold SQL has `WHERE \`County Name\` = 'Alameda'`, do NOT put
'Alameda' in examples. Pick OTHER values from the DISTINCT result set.

The reason: the dataset is meant to test agents on their ability to map
NL → tool args. If the slot description hands them the answer, the
benchmark is rigged. The example values exist to teach an agent the
*vocabulary* of the column, not to give away any particular question's
ground truth.

✓ For Alameda question: `examples: ["Los Angeles", "Sacramento", "San Diego"]`
✗ For Alameda question: `examples: ["Alameda", "Los Angeles", "Sacramento"]`

For `enum` of small fixed sets, you DO include all values — you have to,
because the schema must constrain the input. Enums are fine because
they're inherent to the schema, not didactic hints.

This rule + `db_run_sql DISTINCT` also prevents validation failures
rooted in casing/spacing/punctuation ("Locally Funded" vs "Locally
funded").

## G. Case-insensitive string comparisons in tool SQL.

For string equality on user-supplied values, generated tool code MUST use
`COLLATE NOCASE` so callers don't have to know the exact casing. Use:

    "WHERE `County Name` = ? COLLATE NOCASE"

instead of plain `=`. Apply this to every string-equality predicate
that's parameterized. Don't apply it to numeric or date columns. The
gold SQL uses exact case; that's fine — `COLLATE NOCASE` only relaxes
the tool's input, not its semantic output, so set-equality validation
still passes.

# === WORKED EXAMPLES ===

These are illustrations of the **reasoning**, not templates to copy
verbatim. Adapt to each question.

## Example A — when 1 tool is the right call (qid 0)

NL: "What is the highest eligible free rate for K-12 students in the
schools in Alameda County?"

Gold SQL:
    SELECT `Free Meal Count (K-12)` / `Enrollment (K-12)` FROM frpm
    WHERE `County Name` = 'Alameda'
    ORDER BY (CAST(... AS REAL) / ...) DESC LIMIT 1

**Design reasoning.** The SQL does one conceptually atomic thing: "max
free-meal ratio in a given county." Two reasonable decompositions:

  Option 1 (1 tool): `get_highest_free_meal_ratio_by_county(county_name)`
  Option 2 (2 tools):
    - `schools_in_county(county_name) -> [cds_codes]`
    - `max_free_meal_ratio_among(cds_codes) -> rate`

I'll go with Option 1 here because (a) the SQL has no subquery suggesting
a natural seam; (b) "schools in county" is more useful as a JOIN piece
than a standalone tool; (c) Option 2's `max_*_among(cds_codes)` doesn't
match how other county-scoped questions in Bird tend to be phrased — they
ask aggregate-by-county, not aggregate-over-arbitrary-list. So Option 1
makes the better reusable primitive.

```
tool_register(db="california_schools",
  name="get_highest_free_meal_ratio_by_county",
  description="The highest K-12 free-meal ratio (Free Meal Count K-12 / Enrollment K-12) among schools in a specified California county.",
  return_description="{rate: float|null} — the maximum ratio, or null if county has no rows.",
  params_schema={
    "type": "object",
    "properties": {
      "county_name": {
        "type": "string",
        "description": "Exact value of the `County Name` column in frpm, e.g. 'Alameda', 'Los Angeles'.",
      }
    },
    "required": ["county_name"],
  },
  code=\"\"\"
def run(conn, county_name):
    row = conn.execute(
        "SELECT `Free Meal Count (K-12)` / `Enrollment (K-12)` "
        "FROM frpm WHERE `County Name` = ? "
        "ORDER BY (CAST(`Free Meal Count (K-12)` AS REAL) / `Enrollment (K-12)`) DESC "
        "LIMIT 1",
        (county_name,),
    ).fetchone()
    return {"rate": row[0] if row else None}
\"\"\")

seq_record(db="california_schools", question_id=0, sequence=[
  {"tool": "get_highest_free_meal_ratio_by_county",
   "args": {"county_name": "Alameda"}}
])
```

## Example B — when multi-tool decomposition is right (qid 28)

NL: "Consider the average difference between K-12 enrollment and 15-17
enrollment of schools that are locally funded; list the names and DOC
type of schools which have a difference above this average."

Gold SQL: schools.School, schools.DOC where (frpm.Enrollment K-12 - frpm.Enrollment Ages 5-17) > (subquery: average of that same difference for locally-funded schools).

**Design reasoning.** The gold SQL has a clear subquery — a strong
decomposition seam. Two natural concepts:

  1. The aggregate ("avg enrollment difference for funding type X").
  2. The filter ("schools whose enrollment difference exceeds threshold T,
     filtered by funding type X").

Both are independently reusable. Other Bird questions about california
schools likely also want either "avg X by funding type" or "schools
exceeding threshold T." So:

```
tool_register(name="avg_enrollment_difference_by_funding_type",
  description="Average of (Enrollment K-12 − Enrollment Ages 5-17) across schools matching a given FundingType.",
  return_description="{avg_difference: float|null}",
  params_schema={
    "type": "object",
    "properties": {
      "funding_type": {
        "type": "string",
        "examples": ["Locally funded", "Directly funded", "Not in CS funding model"],
        "description": "Value of the FundingType column on the `schools` table.",
      }
    },
    "required": ["funding_type"],
  },
  code=...)

tool_register(name="schools_with_enrollment_difference_above",
  description="Schools matching a given FundingType whose (Enrollment K-12 − Enrollment Ages 5-17) exceeds a numeric threshold; returns school name + DOC type.",
  return_description="{schools: [{school: str, doc: str}, ...]}",
  params_schema={
    "type": "object",
    "properties": {
      "funding_type": {"type": "string",
                       "description": "FundingType column value."},
      "threshold":    {"type": "number",
                       "description": "Minimum (exclusive) enrollment difference."}
    },
    "required": ["funding_type", "threshold"],
  },
  code=...)
```

The recorded sequence then chains them with binding:

```
seq_record(db="california_schools", question_id=28, sequence=[
  {"tool": "avg_enrollment_difference_by_funding_type",
   "args": {"funding_type": "Locally funded"},
   "bind": "avg"},
  {"tool": "schools_with_enrollment_difference_above",
   "args": {"funding_type": "Locally funded",
            "threshold":    "{{avg.avg_difference}}"}}
])
```

This sequence reads like a small program. Both tools are now available
for many other questions.

## Example C — legitimate 0-parameter tool

If a question is intrinsically singleton ("the school with the highest X"
where X is a fixed metric across the entire dataset), zero parameters is
correct. But the NAME still describes the concept:

  `get_phone_of_school_with_highest_ge1500_sat_count()` — fine.
  `question_42_wrapper()` — never.

# === EXECUTION LOOP for a single question ===

1. `bird_get_question(db, qid)` — read NL, evidence, gold SQL.
2. `bird_run_gold(db, qid)` — capture the canonical answer.
3. `db_get_schema(db)` (first time) and, if helpful, `db_sample_rows` on
   relevant tables. For any column you'll parameterize on, also run
   `db_run_sql` to fetch DISTINCT values — needed to populate slot
   `enum`/`examples` correctly.
4. `tool_list(db)` — read every existing tool's name AND description.
   Could a sequence over existing tools, with different args, reproduce
   the gold answer? If yes → record that sequence and validate. STOP.
   Reuse is mandatory whenever it's possible.
5. Otherwise, **think out loud about decomposition**. Before any
   `tool_register` call, write a short paragraph (in your reasoning,
   not as a tool call) covering:
     - How does the gold SQL break into atomic operations?
     - For each operation: name, slots, slot types, slot value semantics.
     - Are any of these tools likely to be reused by other questions?
   This thinking determines whether you register 1, 2, or N tools.
6. `tool_register` each new tool, then immediately `tool_call` it with
   the args needed for THIS question to confirm it returns the expected
   shape. If it errors, fix the code (re-register) and try again.
7. `seq_record` the full sequence using THIS question's literal values
   as args (or `{{...}}` references for chained outputs).
8. `seq_validate` — must return `passed=true`.
   - If false: read `failure_msg`. The diff usually points to a wrong
     tool. Fix it, re-validate. Up to 2 retries.
   - If still failing, fall back to a single tool that is **still
     properly named and parameterized** (no wrappers).
9. Summary in your response: list tool names created or reused (with
   their slot names + types) and the recorded sequence. Be specific
   enough that a human can audit your design choices.

# === SELF-CHECK BEFORE EVERY tool_register ===

Answer all four:

1. **Name**: does it describe the *concept* in domain terms, not the
   question? Free of "wrapper", "question_N", "gold", "solver"?
2. **Slots**: have you lifted every domain literal in the SQL? Is each
   slot's name domain-meaningful, type precise, value semantics
   documented (enum or examples + description)?
3. **Decomposition**: did you consider whether this should be 1 tool or
   several? If you didn't think about it, go back.
4. **Reuse**: could a different Bird question reuse this exact tool with
   different args? If no, you've over-specialized — refactor.

If any answer is "no" or "I'm not sure", do not register yet.
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

def _make_tools():
    from _mcp_bridge import load_tools
    return load_tools(["invocable_apis"])


def make_agent():
    from cuga import CugaAgent
    from _llm import create_llm
    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ---------------------------------------------------------------------------
# Direct MCP access — for non-LLM endpoints (state inspection, emit)
# ---------------------------------------------------------------------------

def _mcp(tool: str, args: dict | None = None):
    from _mcp_bridge import call_tool
    return call_tool("invocable_apis", tool, args or {})


# ---------------------------------------------------------------------------
# Job tracking for batch synthesis
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}


def _job_record(job_id: str, **patch) -> dict:
    j = _jobs.setdefault(job_id, {"job_id": job_id, "events": []})
    j.update({k: v for k, v in patch.items() if k != "event"})
    if patch.get("event"):
        j["events"].append(patch["event"])
    return j


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class QuestionReq(BaseModel):
    instructions: str | None = None  # optional override


# ---------------------------------------------------------------------------
# Web app
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn

    agent = make_agent()
    app = FastAPI(title="Bird Invocable API Creator", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/databases")
    async def databases():
        """List Bird databases (passthrough to mcp-invocable_apis)."""
        try:
            r = _mcp("bird_list_databases", {}) or {}
            # Normalize to {"databases": ["california_schools", ...]} for the UI.
            entries = r.get("databases") or []
            return {"databases": [e["db"] if isinstance(e, dict) else e for e in entries]}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/questions/{db}")
    async def questions(db: str):
        """Bird question list for a DB (passthrough to mcp-invocable-apis)."""
        try:
            return _mcp("bird_list_questions", {"db": db})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/qmeta/{db}/{qid}")
    async def qmeta(db: str, qid: int):
        """Single Bird record (NL + evidence + SQL + difficulty)."""
        try:
            return _mcp("bird_get_question", {"db": db, "question_id": qid})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/dataset/{db}")
    async def dataset_state(db: str):
        """Snapshot: registered tools + Bird question count + validation totals."""
        try:
            tools = _mcp("tool_list", {"db": db}) or {}
            qs = _mcp("bird_list_questions", {"db": db}) or {}
            return {
                "db": db,
                "tools": tools,
                "questions_total": qs.get("count", 0),
            }
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    def _dataset_path(db: str) -> Path:
        """Resolve the per-db dataset.json path — newly named with db suffix."""
        return _DIR / "output" / db / f"{db}_dataset.json"

    @app.get("/stats/{db}")
    async def stats(db: str):
        """Aggregate stats over the emitted dataset.json — for the UI panel.

        Reads the on-disk dataset (post-emit) so the UI shows what's actually
        in the artifact, not just transient registry state.
        """
        path = _dataset_path(db)
        if not path.exists():
            return {"db": db, "emitted": False, "message": "no dataset emitted yet"}
        try:
            recs = json.loads(path.read_text())
            total = len(recs)
            with_seq = sum(1 for r in recs if r.get("tool_sequence"))
            passed = sum(1 for r in recs if r.get("validated"))
            ignored = sum(1 for r in recs if r.get("ignored"))
            keep = sum(
                1 for r in recs
                if r.get("validated") and not r.get("ignored")
            )
            seq_lens: dict[int, int] = {}
            tool_uses: dict[str, list[int]] = {}
            for r in recs:
                seq = r.get("tool_sequence") or []
                seq_lens[len(seq)] = seq_lens.get(len(seq), 0) + 1
                for s in seq:
                    tool_uses.setdefault(s["tool"], []).append(r["question_id"])
            reuse_count = sum(1 for v in tool_uses.values() if len(v) > 1)
            return {
                "db": db,
                "emitted": True,
                "total_questions": total,
                "with_sequence": with_seq,
                "validated": passed,
                "ignored": ignored,
                "keep": keep,
                "discard": total - keep,
                "unique_tools": len(tool_uses),
                "tools_reused_across_questions": reuse_count,
                "sequence_length_distribution": seq_lens,
                "emitted_at": (path.stat().st_mtime),
            }
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/record/{db}/{qid}")
    async def record(db: str, qid: int):
        """Return one Bird question's emitted record (post-emit).

        UI calls this after picking a question to show its sequence,
        validation status, ignore flag.
        """
        path = _dataset_path(db)
        if not path.exists():
            return JSONResponse({"error": "no dataset emitted yet"}, status_code=404)
        recs = json.loads(path.read_text())
        for r in recs:
            if r.get("question_id") == qid:
                return r
        return JSONResponse({"error": "qid not in dataset"}, status_code=404)

    @app.get("/dataset_full/{db}")
    async def dataset_full(db: str):
        """Return the entire emitted dataset.json — UI uses this for the filter panel."""
        path = _dataset_path(db)
        if not path.exists():
            return []
        return json.loads(path.read_text())

    @app.get("/tools_full/{db}")
    async def tools_full(db: str):
        """Return the emitted tool_usage.json — UI Tool Browser uses this.

        Falls back to live `tool_list` for tools that haven't been emitted yet.
        """
        usage_path = _DIR / "output" / db / f"{db}_tool_usage.json"
        if usage_path.exists():
            return json.loads(usage_path.read_text())
        try:
            r = _mcp("tool_list", {"db": db}) or {}
            tools = r.get("tools") or (r.get("data") or {}).get("tools") or []
            return {
                "db": db,
                "tools": [
                    {**t, "used_by_question_ids": [], "reuse_count": 0}
                    for t in tools
                ],
            }
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    class IgnoreReq(BaseModel):
        ignored: bool = True
        reason: str = ""

    @app.post("/ignore/{db}/{qid}")
    async def ignore(db: str, qid: int, req: IgnoreReq):
        """Toggle the manual ignore flag on a question's record."""
        try:
            r = _mcp("ignore_set", {"db": db, "question_id": qid,
                                    "ignored": req.ignored, "reason": req.reason})
            # Re-emit so dataset.json on disk reflects the new flag immediately.
            _mcp("dataset_emit", {"db": db, "out_dir": str(_DIR / "output")})
            return r
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    def _per_question_instructions(db: str, qid: int) -> str:
        """Punchy, action-mandatory instructions — the LLM must call tools, not chat."""
        return (
            f"TASK: synthesize the invocable-API tool sequence for Bird "
            f"question_id={qid} in db='{db}'. This is not a discussion; "
            f"execute the full loop using tool calls.\n\n"
            f"REQUIRED tool calls, in order:\n"
            f"  1. bird_get_question(db='{db}', question_id={qid})\n"
            f"  2. bird_run_gold(db='{db}', question_id={qid})\n"
            f"  3. tool_list(db='{db}')   — see what's already registered\n"
            f"  4. For each tool you need: tool_register(...) then immediately\n"
            f"     tool_call(...) to confirm it works on real data.\n"
            f"  5. seq_record(db='{db}', question_id={qid}, sequence=[...])\n"
            f"  6. seq_validate(db='{db}', question_id={qid})\n\n"
            f"You are NOT done until seq_validate returns passed=true (or you "
            f"have exhausted retries per the system prompt's fallback rule). "
            f"Your final response must list the tool names you registered or "
            f"reused, the recorded sequence, and the validation pass/fail."
        )

    async def _verify_recorded(db: str, qid: int) -> dict:
        """After agent.invoke, confirm a sequence + validation actually exists."""
        try:
            v = _mcp("seq_validate", {"db": db, "question_id": qid}) or {}
            return {"recorded": True, "passed": bool(v.get("passed")),
                    "failure_msg": v.get("failure_msg")}
        except Exception as e:
            return {"recorded": False, "passed": False, "failure_msg": str(e)}

    @app.post("/question/{db}/{qid}")
    async def question(db: str, qid: int, req: QuestionReq | None = None):
        """Interactive demo: agent processes one Bird question end-to-end."""
        instructions = (req.instructions if req else None) or _per_question_instructions(db, qid)
        try:
            result = await agent.invoke(instructions, thread_id=f"q-{db}-{qid}")
            verify = await _verify_recorded(db, qid)
            return {
                "db": db,
                "question_id": qid,
                "answer": result.answer,
                "verification": verify,
            }
        except Exception as e:
            log.exception("Question synthesis error")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/synthesize/{db}")
    async def synthesize(db: str):
        """Kick off batch synthesis: agent walks every Bird question for the DB."""
        job_id = uuid.uuid4().hex[:8]
        _job_record(job_id, db=db, status="started", processed=0, total=0)

        async def _runner():
            try:
                qs_resp = _mcp("bird_list_questions", {"db": db}) or {}
                qids = [q["question_id"] for q in qs_resp.get("questions", [])]
                _job_record(job_id, total=len(qids), passed=0, recorded=0)
                for qid in qids:
                    try:
                        await agent.invoke(_per_question_instructions(db, qid),
                                           thread_id=f"q-{db}-{qid}")
                        v = await _verify_recorded(db, qid)
                        ev = {"qid": qid,
                              "recorded": v["recorded"],
                              "passed":   v["passed"]}
                        _job_record(
                            job_id,
                            event=ev,
                            processed=_jobs[job_id]["processed"] + 1,
                            recorded=_jobs[job_id]["recorded"] + (1 if v["recorded"] else 0),
                            passed=_jobs[job_id]["passed"]   + (1 if v["passed"]   else 0),
                        )
                    except Exception as ex:
                        _job_record(
                            job_id,
                            event={"qid": qid, "status": "error", "error": str(ex)},
                            processed=_jobs[job_id]["processed"] + 1,
                        )
                # Auto-emit so the user sees results without a separate POST /emit call.
                try:
                    emit = _mcp("dataset_emit",
                                {"db": db, "out_dir": str(_DIR / "output")}) or {}
                    _job_record(job_id, status="finished", emit=emit)
                except Exception as ex:
                    _job_record(job_id, status="finished_emit_failed", error=str(ex))
            except Exception as ex:
                _job_record(job_id, status="error", error=str(ex))

        asyncio.create_task(_runner())
        return {"job_id": job_id, "db": db, "status": "started"}

    @app.get("/jobs/{job_id}")
    async def job_status(job_id: str):
        j = _jobs.get(job_id)
        if not j:
            return JSONResponse({"error": "no such job"}, status_code=404)
        return j

    @app.post("/emit/{db}")
    async def emit(db: str):
        """Freeze the registry + sequences to disk."""
        out_dir = str(_DIR / "output")
        try:
            return _mcp("dataset_emit", {"db": db, "out_dir": out_dir})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    print(f"\n  Bird Invocable API Creator  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Minimal HTML UI — DB picker → question list → per-question demo
# ---------------------------------------------------------------------------

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bird Invocable API Creator</title>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:#0f1117;color:#e2e8f0;min-height:100vh}
  header{background:#1a1a2e;border-bottom:1px solid #2d2d4a;padding:14px 28px;
         display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}
  header h1{font-size:16px;font-weight:700;color:#fff}
  .layout{display:grid;grid-template-columns:340px 1fr;gap:20px;
          max-width:1320px;margin:0 auto;padding:20px 24px}
  .card{background:#1a1a2e;border:1px solid #2d2d4a;border-radius:10px;
        margin-bottom:16px;overflow:hidden}
  .card-h{padding:12px 16px 10px;border-bottom:1px solid #2d2d4a;
          font-size:13px;font-weight:600;color:#c5cae9;display:flex;
          align-items:center;gap:8px}
  .card-b{padding:14px 16px}
  select,input,button,textarea{font-family:inherit;font-size:12px;
        background:#0f1117;border:1px solid #374151;color:#e2e8f0;
        border-radius:5px;padding:5px 9px;outline:none}
  select:focus,input:focus,textarea:focus{border-color:#0d9488}
  button{background:#0d9488;color:#fff;border:none;cursor:pointer;
         padding:6px 14px;border-radius:6px}
  button:hover{background:#0f766e}
  button:disabled{background:#374151;color:#6b7280;cursor:default}
  .btn-ghost{background:#1f2937;border:1px solid #374151;color:#9ca3af}
  .btn-red{background:#7f1d1d;color:#fecaca}
  .btn-red:hover{background:#991b1b}
  .row{display:flex;align-items:center;gap:8px;margin-bottom:9px}
  .row label{font-size:12px;color:#9ca3af;min-width:90px}
  .qlist{max-height:55vh;overflow:auto;border:1px solid #2d2d4a;border-radius:6px}
  .qrow{padding:7px 10px;border-bottom:1px solid #2d2d4a;
        cursor:pointer;font-size:12px;line-height:1.35;display:flex;align-items:flex-start;gap:6px}
  .qrow:last-child{border-bottom:none}
  .qrow:hover{background:#1f2937}
  .qrow.sel{background:#0d3330}
  .qid{color:#5eead4;font-weight:600;flex-shrink:0;width:34px}
  .qstatus{flex-shrink:0;width:14px;text-align:center;font-size:11px}
  .s-pass{color:#4ade80}
  .s-fail{color:#f87171}
  .s-none{color:#4b5563}
  .s-ign{color:#facc15}
  .qtext{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .diff{font-size:10px;padding:1px 6px;border-radius:8px;margin-left:6px;flex-shrink:0}
  .diff-simple{background:#0d3330;color:#5eead4}
  .diff-moderate{background:#1e3a5f;color:#60a5fa}
  .diff-challenging{background:#451a03;color:#fbbf24}
  .gold-sql,.tool-seq{font-family:ui-monospace,monospace;font-size:11px;background:#0f1117;
        border:1px solid #374151;border-radius:6px;padding:8px;
        white-space:pre-wrap;color:#d1d5db;max-height:200px;overflow:auto}
  .meta{font-size:10px;color:#6b7280;margin:8px 0 3px}
  .empty{font-size:12px;color:#4b5563;text-align:center;padding:24px}
  .stats-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:6px}
  .stat{background:#0f1117;border:1px solid #2d2d4a;border-radius:6px;padding:8px 10px}
  .stat-v{font-size:18px;font-weight:600;color:#5eead4}
  .stat-l{font-size:10px;color:#6b7280;margin-top:2px;text-transform:uppercase}
  .stat.warn .stat-v{color:#fbbf24}
  .stat.bad  .stat-v{color:#f87171}
  .badge{display:inline-block;padding:2px 8px;border-radius:8px;font-size:10px;
         font-weight:600;margin-left:4px}
  .b-pass{background:#0d3330;color:#5eead4}
  .b-fail{background:#451a03;color:#f87171}
  .b-ign {background:#422006;color:#facc15}
  .b-none{background:#1f2937;color:#9ca3af}
  .pill{display:inline-block;padding:1px 8px;border-radius:8px;
        background:#1f2937;color:#9ca3af;font-size:10px;margin-right:4px}
  .tool-row{padding:8px 10px;border:1px solid #2d2d4a;border-radius:6px;
            margin-bottom:6px;background:#0f1117;cursor:pointer}
  .tool-row:hover{background:#1f2937}
  .answer{font-size:12px;line-height:1.6;color:#d1d5db;white-space:pre-wrap;
        background:#0f1117;border:1px solid #2d2d4a;border-radius:7px;
        padding:12px;margin-top:10px;max-height:240px;overflow:auto}
  .progress{height:6px;background:#1f2937;border-radius:3px;overflow:hidden;margin-top:6px}
  .progress-bar{height:100%;background:#0d9488;transition:width 0.3s}
  .filters{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
  .filter{padding:3px 9px;border-radius:10px;font-size:11px;cursor:pointer;
          background:#1f2937;border:1px solid #374151;color:#9ca3af}
  .filter.on{background:#0d3330;border-color:#0d9488;color:#5eead4}
</style>
</head>
<body>

<header>
  <h1>🪶 Bird Invocable API Creator</h1>
  <div style="flex:1"></div>
  <span id="hdr-stat" style="font-size:11px;color:#4b5563"></span>
</header>

<div class="layout">

  <!-- ─────── LEFT: db picker + batch + question filter list ─────── -->
  <div>
    <div class="card">
      <div class="card-h">📚 Database</div>
      <div class="card-b">
        <div class="row"><label>db_id</label>
          <select id="db" style="flex:1"></select></div>
        <div class="row" style="margin-top:6px">
          <button id="batch-btn" onclick="batch()">⚡ Batch synthesize</button>
          <button class="btn-ghost" onclick="reEmit()">📥 Re-emit</button>
          <button class="btn-ghost" onclick="loadAll()">↺</button>
        </div>
        <div id="batch-status" style="font-size:11px;color:#6b7280;margin-top:8px"></div>
        <div id="batch-progress" class="progress" style="display:none">
          <div id="batch-bar" class="progress-bar" style="width:0"></div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-h">❓ Questions
        <span style="margin-left:auto;font-size:10px;color:#6b7280" id="qcount"></span>
      </div>
      <div class="card-b">
        <div class="filters">
          <span class="filter on" data-f="all"   onclick="setFilter(this)">all</span>
          <span class="filter"    data-f="pass"  onclick="setFilter(this)">✓ pass</span>
          <span class="filter"    data-f="fail"  onclick="setFilter(this)">✗ fail</span>
          <span class="filter"    data-f="none"  onclick="setFilter(this)">— no seq</span>
          <span class="filter"    data-f="ign"   onclick="setFilter(this)">⊘ ignored</span>
        </div>
        <div id="qlist" class="qlist"><div class="empty">Pick a database above</div></div>
      </div>
    </div>
  </div>

  <!-- ─────── RIGHT: stats panel + per-question inspector ─────── -->
  <div>

    <div class="card">
      <div class="card-h">📊 Dataset stats</div>
      <div class="card-b" id="stats-body">
        <div class="empty">No dataset emitted yet — run batch on the left.</div>
      </div>
    </div>

    <div class="card">
      <div class="card-h">🔬 Question inspector</div>
      <div class="card-b" id="insp-body">
        <div class="empty">Pick a question on the left to inspect or re-run.</div>
      </div>
    </div>

    <div class="card">
      <div class="card-h">🧰 Tool browser
        <span style="margin-left:auto;font-size:10px;color:#6b7280" id="tcount"></span>
      </div>
      <div class="card-b">
        <div class="row">
          <input id="tfilter" placeholder="filter by name…" style="flex:1"
                 oninput="renderTools()">
          <select id="tsort" onchange="renderTools()">
            <option value="reuse_desc">most reused</option>
            <option value="reuse_asc">least reused</option>
            <option value="name">name</option>
          </select>
        </div>
        <div id="tlist" style="max-height:55vh;overflow:auto;margin-top:8px">
          <div class="empty">No tools yet — run batch.</div>
        </div>
      </div>
    </div>

  </div>
</div>

<script>
let CURRENT_DB = null;
let CURRENT_QID = null;
let QUESTIONS = [];           // [{question_id, question, difficulty}]
let DATASET   = {};           // qid → record (post-emit)
let TOOLS     = [];           // tool_usage entries: name, description, params_schema, used_by_question_ids
let TOOLS_BY_NAME = {};       // name → tool entry (for inspector lookup)
let FILTER    = 'all';
let BATCH_JOB = null;
let BATCH_TIMER = null;

// ── Init ────────────────────────────────────────────────────────────
async function init() {
  const r = await fetch('/databases').then(r => r.json()).catch(() => ({databases:[]}));
  const sel = document.getElementById('db');
  sel.innerHTML = (r.databases || []).map(d =>
    `<option value="${d}">${d}</option>`).join('');
  if (!r.databases || !r.databases.length) {
    document.getElementById('qlist').innerHTML =
      '<div class="empty">No databases — set BIRD_DBS_DIR.</div>';
    return;
  }
  sel.value = r.databases.includes('california_schools')
    ? 'california_schools' : r.databases[0];
  sel.onchange = () => loadAll();
  CURRENT_DB = sel.value;
  await loadAll();
}

async function loadAll() {
  CURRENT_DB = document.getElementById('db').value;
  CURRENT_QID = null;
  document.getElementById('insp-body').innerHTML =
    '<div class="empty">Pick a question on the left to inspect or re-run.</div>';
  await Promise.all([loadQs(), loadStatsAndDataset(), loadTools()]);
  renderQs();
  renderTools();
}

// ── Tool browser ────────────────────────────────────────────────────
async function loadTools() {
  try {
    const r = await fetch('/tools_full/' + CURRENT_DB).then(r => r.json());
    TOOLS = (r && r.tools) || [];
    TOOLS_BY_NAME = {};
    for (const t of TOOLS) TOOLS_BY_NAME[t.name] = t;
  } catch (e) { TOOLS = []; TOOLS_BY_NAME = {}; }
}

function renderTools() {
  const filt = (document.getElementById('tfilter').value || '').toLowerCase();
  const sort = document.getElementById('tsort').value;
  let list = TOOLS.filter(t =>
    !filt || t.name.toLowerCase().includes(filt) ||
    (t.description||'').toLowerCase().includes(filt));
  if (sort === 'name') list.sort((a,b) => a.name.localeCompare(b.name));
  else if (sort === 'reuse_asc') list.sort((a,b) => (a.reuse_count||0) - (b.reuse_count||0));
  else list.sort((a,b) => (b.reuse_count||0) - (a.reuse_count||0));

  document.getElementById('tcount').textContent = `${list.length}/${TOOLS.length}`;
  const el = document.getElementById('tlist');
  if (!list.length) {
    el.innerHTML = '<div class="empty">No tools match.</div>';
    return;
  }
  el.innerHTML = list.map(t => {
    const props = (t.params_schema && t.params_schema.properties) || {};
    const slotChips = Object.entries(props).map(([k, v]) => {
      const ty = v.type || '?';
      const ex = v.enum ? ` ∈ {${v.enum.slice(0,4).join(', ')}${v.enum.length>4?'…':''}}`
               : (v.examples && v.examples.length) ? ` e.g. ${v.examples.slice(0,3).join(', ')}`
               : '';
      return `<span class="pill" title="${escapeHtml(v.description||'')}">` +
             `${escapeHtml(k)}: ${escapeHtml(ty)}${escapeHtml(ex)}</span>`;
    }).join(' ');
    const badge = t.reuse_count > 1
      ? `<span class="badge b-pass">×${t.reuse_count} reused</span>`
      : t.reuse_count === 1 ? `<span class="badge b-none">×1</span>`
      : `<span class="badge b-fail">unused</span>`;
    return `
      <div class="tool-row" onclick="showToolUsers('${escapeHtml(t.name)}')">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="color:#5eead4;font-weight:600;font-size:12px;font-family:ui-monospace,monospace">
            ${escapeHtml(t.name)}</span>
          ${badge}
        </div>
        <div style="font-size:11px;color:#9ca3af;margin-top:3px;line-height:1.4">
          ${escapeHtml(t.description || '(no description)')}</div>
        <div style="margin-top:5px">${slotChips || '<span class="pill">no slots</span>'}</div>
      </div>`;
  }).join('');
}

function showToolUsers(name) {
  const t = TOOLS_BY_NAME[name];
  if (!t) return;
  const qids = (t.used_by_question_ids || []).join(', ');
  alert(`${name}\n\n${t.description||'(no description)'}\n\nUsed by question_ids: ${qids || '(none)'}`);
}

// ── Question list ───────────────────────────────────────────────────
async function loadQs() {
  document.getElementById('qlist').innerHTML = '<div class="empty">Loading…</div>';
  try {
    const r = await fetch('/questions/' + CURRENT_DB).then(r => r.json());
    QUESTIONS = (r && r.questions) || (r && r.data && r.data.questions) || [];
  } catch (e) {
    QUESTIONS = [];
  }
}

function statusOf(qid) {
  const rec = DATASET[qid];
  if (!rec) return 'none';
  if (rec.ignored) return 'ign';
  if (rec.validated) return 'pass';
  if (rec.tool_sequence) return 'fail';
  return 'none';
}

function setFilter(el) {
  document.querySelectorAll('.filter').forEach(e => e.classList.remove('on'));
  el.classList.add('on');
  FILTER = el.dataset.f;
  renderQs();
}

function renderQs() {
  const el = document.getElementById('qlist');
  if (!QUESTIONS.length) {
    el.innerHTML = '<div class="empty">No questions for this database.</div>';
    return;
  }
  const filtered = QUESTIONS.filter(q => {
    if (FILTER === 'all') return true;
    return statusOf(q.question_id) === FILTER;
  });
  document.getElementById('qcount').textContent =
    `${filtered.length}/${QUESTIONS.length}`;
  el.innerHTML = filtered.length === 0 ? '<div class="empty">No matches</div>' :
    filtered.map(q => {
      const st = statusOf(q.question_id);
      const icon = {pass: '✓', fail: '✗', ign: '⊘', none: '·'}[st] || '·';
      return `
        <div class="qrow ${CURRENT_QID===q.question_id?'sel':''}"
             onclick="pickQ(${q.question_id})">
          <span class="qid">#${q.question_id}</span>
          <span class="qstatus s-${st}">${icon}</span>
          <span class="qtext">${escapeHtml(q.question)}</span>
          ${q.difficulty ? `<span class="diff diff-${q.difficulty}">${q.difficulty}</span>` : ''}
        </div>`;
    }).join('');
}

// ── Stats panel ─────────────────────────────────────────────────────
async function loadStatsAndDataset() {
  // Stats from emitted dataset.
  try {
    const s = await fetch('/stats/' + CURRENT_DB).then(r => r.json());
    if (!s.emitted) {
      document.getElementById('stats-body').innerHTML =
        '<div class="empty">No dataset emitted yet — run batch on the left.</div>';
      DATASET = {};
      return;
    }
    document.getElementById('stats-body').innerHTML = renderStats(s);
    // Dataset records keyed by qid for filter + inspector.
    DATASET = {};
    try {
      // We don't have a list endpoint, so fetch on a per-qid basis lazily;
      // but for the filter, pull the full dataset.json once via /record loop
      // would be wasteful. Instead, the stats endpoint gave us totals only.
      // Use a single fetch for the full file via the /record/{db}/{qid} path
      // is per-qid; better — just GET the static file at /output/...
      // The app doesn't serve static; the simplest path is to refetch /stats
      // and then per-qid /record on click. For the filter, we need all of
      // them. Issue a hidden bulk fetch:
      const all = await fetch('/dataset_full/' + CURRENT_DB).then(r => r.json());
      if (Array.isArray(all)) all.forEach(rec => DATASET[rec.question_id] = rec);
    } catch (e) {}
  } catch (e) {
    document.getElementById('stats-body').textContent = 'Error: ' + e.message;
  }
}

function renderStats(s) {
  const reuseClass = (s.tools_reused_across_questions === 0) ? 'warn' : '';
  const lenDist = Object.entries(s.sequence_length_distribution || {})
    .sort((a,b)=>+a[0]-+b[0])
    .map(([k,v]) => `<span class="pill">${k}-step: ${v}</span>`).join('');
  return `
    <div class="stats-grid">
      <div class="stat">
        <div class="stat-v">${s.total_questions}</div>
        <div class="stat-l">total</div>
      </div>
      <div class="stat">
        <div class="stat-v">${s.with_sequence}</div>
        <div class="stat-l">w/ sequence</div>
      </div>
      <div class="stat">
        <div class="stat-v">${s.validated}</div>
        <div class="stat-l">validated</div>
      </div>
      <div class="stat ${s.discard > 0 ? 'bad' : ''}">
        <div class="stat-v">${s.keep}</div>
        <div class="stat-l">keep / ${s.discard} discard</div>
      </div>
      <div class="stat ${reuseClass}">
        <div class="stat-v">${s.unique_tools}</div>
        <div class="stat-l">unique tools</div>
      </div>
      <div class="stat ${reuseClass}">
        <div class="stat-v">${s.tools_reused_across_questions}</div>
        <div class="stat-l">reused across qs</div>
      </div>
      <div class="stat">
        <div class="stat-v">${s.ignored}</div>
        <div class="stat-l">ignored</div>
      </div>
      <div class="stat">
        <div class="stat-v">${(s.with_sequence>0?Math.round(100*s.validated/s.with_sequence):0)}%</div>
        <div class="stat-l">pass-rate</div>
      </div>
    </div>
    <div style="margin-top:10px;font-size:11px;color:#9ca3af">
      <span style="color:#6b7280">sequence lengths:</span> ${lenDist || '—'}
    </div>
  `;
}

// ── Inspector ───────────────────────────────────────────────────────
async function pickQ(qid) {
  CURRENT_QID = qid;
  renderQs();  // re-renders with the .sel highlight
  document.getElementById('insp-body').innerHTML = '<div class="empty">Loading…</div>';
  try {
    const meta = await fetch('/qmeta/' + CURRENT_DB + '/' + qid).then(r => r.json());
    const data = (meta && meta.data) || meta || {};
    const rec  = DATASET[qid] || null;
    document.getElementById('insp-body').innerHTML = renderInspector(qid, data, rec);
  } catch (e) {
    document.getElementById('insp-body').innerHTML =
      `<div class="empty" style="color:#f87171">Error: ${e.message}</div>`;
  }
}

function renderInspector(qid, meta, rec) {
  const status = rec ? (rec.ignored ? 'ignored'
                       : rec.validated ? 'validated'
                       : rec.tool_sequence ? 'failed' : 'none') : 'none';
  const badge = {
    validated: '<span class="badge b-pass">✓ validated</span>',
    failed:    '<span class="badge b-fail">✗ failed</span>',
    ignored:   '<span class="badge b-ign">⊘ ignored</span>',
    none:      '<span class="badge b-none">— no sequence</span>',
  }[status];
  const seq = rec && rec.tool_sequence
    ? JSON.stringify(rec.tool_sequence, null, 2)
    : '(no sequence recorded yet)';
  const final = rec && rec.final_result
    ? JSON.stringify(rec.final_result, null, 2) : '—';
  const gold = rec && rec.gold_result
    ? JSON.stringify(rec.gold_result) : '—';
  const failure = rec && rec.failure_msg
    ? `<div class="meta">Failure:</div><div class="gold-sql" style="color:#fca5a5">${escapeHtml(rec.failure_msg)}</div>`
    : '';
  // For each step's tool, render its description + slot list inline so the
  // user can read the sequence without scrolling away to the Tool Browser.
  let stepDocs = '';
  if (rec && rec.tool_sequence) {
    stepDocs = '<div class="meta">Tools used in this sequence:</div>' +
      rec.tool_sequence.map((s, i) => {
        const t = TOOLS_BY_NAME[s.tool] || {};
        const props = (t.params_schema && t.params_schema.properties) || {};
        const slotLines = Object.entries(props).map(([k,v]) =>
          `<div style="font-size:11px;color:#9ca3af;margin-left:14px">` +
          `<span style="color:#5eead4">${escapeHtml(k)}</span> ` +
          `(${escapeHtml(v.type||'?')})` +
          (v.description ? ` — ${escapeHtml(v.description)}` : '') +
          `</div>`).join('');
        return `<div class="tool-row" style="margin-bottom:6px">
          <div style="font-family:ui-monospace,monospace;font-size:12px;color:#c5cae9">
            <span style="color:#6b7280">step ${i+1}:</span>
            <span style="color:#5eead4">${escapeHtml(s.tool)}</span>
          </div>
          <div style="font-size:11px;color:#9ca3af;margin-top:3px;line-height:1.4">
            ${escapeHtml(t.description || '(no description registered)')}</div>
          ${slotLines}</div>`;
      }).join('');
  }
  return `
    <div style="font-size:13px;color:#c5cae9;line-height:1.4">
      <span class="qid">#${qid}</span>${escapeHtml(meta.question || '(missing)')} ${badge}
    </div>
    <div class="meta">Evidence:</div>
    <div style="font-size:11px;color:#9ca3af">${escapeHtml(meta.evidence || '(none)')}</div>
    <div class="meta">Gold SQL:</div>
    <div class="gold-sql">${escapeHtml(meta.SQL || '(unavailable)')}</div>
    <div class="meta">Tool sequence (recorded):</div>
    <div class="tool-seq">${escapeHtml(seq)}</div>
    ${stepDocs}
    <div class="meta">Final result vs Gold:</div>
    <div class="tool-seq">final: ${escapeHtml(final)}\\ngold:  ${escapeHtml(gold)}</div>
    ${failure}
    <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
      <button id="rerun-btn" onclick="runQ()">▶ Run agent on this question</button>
      ${rec && rec.ignored
        ? `<button class="btn-ghost" onclick="setIgnore(false)">↺ Un-ignore</button>`
        : `<button class="btn-red" onclick="setIgnore(true)">⊘ Mark ignore</button>`}
    </div>
    <div id="qanswer" class="answer" style="display:none"></div>
  `;
}

async function runQ() {
  if (CURRENT_DB == null || CURRENT_QID == null) return;
  const btn = document.getElementById('rerun-btn');
  const ans = document.getElementById('qanswer');
  btn.disabled = true; btn.textContent = 'Synthesizing…';
  ans.style.display = 'block';
  ans.textContent = 'Running agent on question #' + CURRENT_QID + '…';
  try {
    const r = await fetch('/question/' + CURRENT_DB + '/' + CURRENT_QID, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({})
    }).then(r => r.json());
    let txt = r.answer || r.error || '(no response)';
    if (r.verification) {
      txt += `\\n\\n— verification: recorded=${r.verification.recorded} ` +
             `passed=${r.verification.passed}` +
             (r.verification.failure_msg ? ` failure=${r.verification.failure_msg}` : '');
    }
    ans.textContent = txt;
    // After single-question rerun, refresh stats + record
    await reEmit();           // re-emit so dataset.json reflects the new state
    await loadStatsAndDataset();
    await pickQ(CURRENT_QID); // refresh inspector
  } catch (e) {
    ans.textContent = 'Error: ' + e.message;
  }
  btn.disabled = false; btn.textContent = '▶ Run agent on this question';
}

async function setIgnore(on) {
  if (CURRENT_QID == null) return;
  try {
    await fetch('/ignore/' + CURRENT_DB + '/' + CURRENT_QID, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ignored: on, reason: on ? 'manual review' : ''})
    });
    await loadStatsAndDataset();
    await pickQ(CURRENT_QID);
    renderQs();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

// ── Batch ───────────────────────────────────────────────────────────
async function batch() {
  if (!CURRENT_DB) return;
  const btn = document.getElementById('batch-btn');
  const status = document.getElementById('batch-status');
  const prog = document.getElementById('batch-progress');
  btn.disabled = true; btn.textContent = 'Running…';
  prog.style.display = 'block';
  status.textContent = 'Starting…';
  try {
    const r = await fetch('/synthesize/' + CURRENT_DB, {method: 'POST'})
                .then(r => r.json());
    BATCH_JOB = r.job_id;
    if (BATCH_TIMER) clearInterval(BATCH_TIMER);
    BATCH_TIMER = setInterval(pollBatch, 4000);
    pollBatch();
  } catch (e) {
    btn.disabled = false; btn.textContent = '⚡ Batch synthesize';
    status.textContent = 'Error: ' + e.message;
  }
}

async function pollBatch() {
  if (!BATCH_JOB) return;
  try {
    const j = await fetch('/jobs/' + BATCH_JOB).then(r => r.json());
    const total = j.total || 1;
    const done  = j.processed || 0;
    document.getElementById('batch-bar').style.width = (100*done/total) + '%';
    document.getElementById('batch-status').textContent =
      `[${j.status}] ${done}/${total} processed · ${j.recorded||0} recorded · ${j.passed||0} passed`;
    if (j.status === 'finished' || j.status === 'finished_emit_failed' || j.status === 'error') {
      clearInterval(BATCH_TIMER); BATCH_TIMER = null;
      const btn = document.getElementById('batch-btn');
      btn.disabled = false; btn.textContent = '⚡ Batch synthesize';
      // Refresh everything from the just-emitted dataset
      await loadStatsAndDataset();
      await loadTools();
      renderQs();
      renderTools();
    }
  } catch (e) {
    document.getElementById('batch-status').textContent = 'Poll error: ' + e.message;
  }
}

async function reEmit() {
  try {
    await fetch('/emit/' + CURRENT_DB, {method: 'POST'});
  } catch (e) {}
}

function escapeHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

init();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=28815)
    parser.add_argument("--provider", "-p", default=None)
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model
    _web(args.port)
