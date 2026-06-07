"""
Bird Invocable API Creator — CUGA-native edition
================================================

Same job as `bird_invocable_api_creator`: turn a Bird-SQL database into an
invocable API. Different *how*.

In the original app, a ~420-line system prompt carries all the design rules
(decomposition, slot semantics, reuse, forbidden names, output format).
The LLM-side loop is generic; the prompt is the brain.

Here we go the other way. The system prompt is ~25 lines. Every rule lives
in a **CUGA policy** loaded at startup, surfaced to the agent only when its
trigger fires:

  - Playbook  "bird_synthesis_loop"        — execution loop (NL trigger)
  - Playbook  "decomposition_mindset"      — design reasoning (NL trigger)
  - Playbook  "reuse_first"                — reuse rules (kw: register, new tool)
  - ToolGuide on `tool_register`           — slot/name/code-quality rules
  - ToolGuide on `seq_record`/`seq_validate`— sequence-format + retry rules
  - IntentGuard "forbidden_tool_names"     — informational block on bad names
  - OutputFormatter "synthesis_summary"    — structured final answer

CUGA features actually exercised (vs the original):
  - Policy storage + .cuga folder fs-sync
  - NL/keyword triggers (Playbooks fire only when needed → cheaper context)
  - ToolGuide injection (rules attach to the tool, not the system prompt)
  - IntentGuard
  - OutputFormatter (final answer is structured JSON, not free prose)
  - HITL approval pathway on `tool_register` (opt-in via --approve)
  - Per-question thread_id checkpointing (also in original)

Run:
    python main.py --port 28816
    python main.py --port 28816 --approve   # require HITL approval for tool_register
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
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

from _carbon import carbon_head, carbon_css  # noqa: E402  (apps root on sys.path)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================================
# THIN system prompt — just the role + pointer to policies.
# Everything else is in policies, attached to tools or triggered by intent.
# ============================================================================

_SYSTEM = """\
You design Bird invocable APIs.

A Bird question gives you (NL question, evidence, gold SQL) on a real sqlite
database. Your job is to register one or more reusable Python tools and a
ground-truth tool-call sequence whose composed result equals the gold SQL
result.

You have MCP tools for: inspecting the DB, reading Bird questions, running
gold SQL, registering/calling tools, recording/validating sequences. Each
tool carries its own usage guidance (delivered as ToolGuide policies). When
your intent matches a Playbook, the playbook will be surfaced automatically.

Drive the work entirely through tool calls. You are done only when
`seq_validate` returns passed=true, or after 2 failed retries.
"""


# ============================================================================
# Policies — each is a short, focused markdown blob. Triggers decide when
# the agent sees it.
# ============================================================================

_PLAYBOOK_SYNTHESIS_LOOP = """\
# Bird synthesis loop

For each question, in order:

1. `bird_get_question(db, question_id)` — read NL, evidence, gold SQL.
2. `bird_run_gold(db, question_id)` — capture canonical answer.
3. `db_get_schema(db)` and, if useful, `db_sample_rows(db, table, n)`.
4. `tool_list(db)` — read every existing tool's name AND description.
   If existing tools (with different args) can reproduce the gold answer,
   record that sequence and validate. STOP. Reuse is mandatory when possible.
5. Otherwise register the minimum new tools needed, `tool_call` each once
   to confirm shape, then `seq_record` and `seq_validate`.
6. On validation failure: read `failure_msg`, fix, re-validate. Max 2 retries.

Refer to the `decomposition_mindset` playbook before any `tool_register`.
Refer to the `reuse_first` playbook whenever you're tempted to register a
new tool that resembles an existing one.
"""

_PLAYBOOK_DECOMPOSITION = """\
# Decomposition mindset

There is no universal answer to "how many tools." For each question, weigh:

- **Atomic operations**: does the gold SQL do one conceptually atomic thing,
  or several composable steps?
- **Reuse potential**: would another Bird question plausibly need a *piece*
  of this query? If yes, factor that piece into its own tool.
- **Sequence clarity**: a 2-step sequence whose steps name distinct concepts
  is better than a single mega-tool; a 5-step sequence whose steps are
  arbitrary slices of the same SQL is worse than 1 tool.

**Strong multi-step signals (default to ≥2 tools when you see these):**
  - Subquery in WHERE/HAVING (e.g. `WHERE x > (SELECT AVG(x) FROM …)`).
  - CTE (`WITH … AS (…)`).
  - Self-join with materially different filters per side.
  - GROUP BY + HAVING comparing against a computed scalar.

Read the gold SQL as a story. Each "and then" is a candidate tool boundary.
"""

_PLAYBOOK_REUSE = """\
# Reuse before invention

`tool_register` will FAIL when:
  - The name matches a forbidden pattern (`question_*`, `q<N>*`, `*_wrapper`,
    `*_solver`, `gold_*`, `fallback_*`, `generic_*`, `todo_*`).
  - The new tool's SQL skeleton (literals stripped) matches an existing
    tool's, OR ≥85% of its name tokens overlap with an existing tool.

When that happens, the error names the existing tool. Two responses:
  - **Reuse with different args** (most common). E.g. existing
    `get_highest_free_meal_ratio_by_county(county_name)` covers any county.
  - **Broaden**: `tool_delete` the old tool, re-register with a wider
    signature, and re-`seq_validate` any earlier questions that depended on
    the deleted name.

Never silently duplicate.
"""

_TOOL_GUIDE_REGISTER = """\
## Quality rules for tool_register

**Name** — concept, not question. snake_case verb-led, domain-meaningful.
✓ `avg_enrollment_difference_by_funding_type`, `schools_with_enrollment_difference_above`.
✗ Anything with `question`, `qid`, `wrapper`, `gold`, `solver`, or a question
   number (will be rejected by the server).

**Slots** — every literal in the gold SQL's WHERE/HAVING/LIMIT/threshold
positions that is a domain value MUST become a parameter. Hardcoding
`'Alameda'`, `1500`, etc. in the body is a policy violation.

- Slot names: domain-meaningful and singular (`county_name`, not `param1`).
- Slot types: precise — `string`, `integer`, `number`, `boolean`.
- Use `enum` for small fixed vocabularies; `examples` (3–5) + `description`
  for larger ones. **Never include this question's literal value in
  `examples`** — it leaks the answer. Pick OTHER values from
  `db_run_sql(... SELECT DISTINCT col ...)`.

**Code** — `def run(conn, **kwargs) -> dict`. Allowed imports: `sqlite3`,
`json`, `re`. Use `?` placeholders (never f-string SQL). For string equality
on user-supplied values, use `COLLATE NOCASE`. Backtick column/table names
with spaces. Return dict keys that describe the value
(`{"rate": 0.93}`, not `{"rows": [[…]]}`). Empty result → `None` (scalar)
or `[]` (list).

After registering, immediately `tool_call` with this question's args to
verify it works on real data. Fix and re-register if it errors.
"""

_TOOL_GUIDE_SEQUENCES = """\
## Sequence recording

Sequence format: a list of `{tool, args, bind?}` entries.
- `args` may reference earlier step output: `"{{name}}"` or `"{{name.path}}"`.
- `bind` names the step output so later steps can reference it.

After `seq_record`, immediately call `seq_validate`. On failure:
  - Read `failure_msg`. The diff usually points to a wrong tool or wrong arg.
  - Fix and re-validate. Max 2 retries.
  - If still failing, fall back to a single properly-named, parameterized
    tool (never a `*_wrapper` or `question_N_*` shape).
"""

_INTENT_GUARD_FORBIDDEN = """\
The names `question_<N>`, `q<N>_solver`, `*_wrapper`, `gold_*`, `solve_*`,
`generic_query`, `get_data`, `fetch_rows` are forbidden for registered
tools. Pick a concept-led, domain-meaningful name instead.
"""

_OUTPUT_FORMATTER_SUMMARY = """\
At the end of synthesis, return a structured summary in this shape:

```
{
  "question_id": <int>,
  "tools_registered": [<tool_name>, ...],
  "tools_reused":     [<tool_name>, ...],
  "sequence":         [{"tool": ..., "args": {...}}, ...],
  "validated":        <bool>,
  "failure_msg":      <string or null>
}
```

No prose before or after the JSON block.
"""


async def setup_policies(agent) -> None:
    """Load all CUGA policies for this app. Idempotent — clears first."""
    await agent.policies.clear()

    # --- Playbooks: fire when the agent's intent matches their NL trigger.
    await agent.policies.add_playbook(
        name="bird_synthesis_loop",
        content=_PLAYBOOK_SYNTHESIS_LOOP,
        natural_language_trigger=[
            "synthesize an invocable API tool sequence for a Bird question",
            "build the tool sequence for a Bird SQL question",
        ],
        keywords=["synthesize", "bird", "invocable"],
        threshold=0.6,
        priority=80,
    )
    await agent.policies.add_playbook(
        name="decomposition_mindset",
        content=_PLAYBOOK_DECOMPOSITION,
        natural_language_trigger=[
            "decide how many tools to register for a SQL question",
            "decompose a SQL query into reusable tools",
        ],
        keywords=["register", "decompose", "design"],
        threshold=0.6,
        priority=70,
    )
    await agent.policies.add_playbook(
        name="reuse_first",
        content=_PLAYBOOK_REUSE,
        natural_language_trigger=[
            "consider whether an existing tool already covers this question",
        ],
        keywords=["reuse", "duplicate", "existing tool"],
        threshold=0.6,
        priority=70,
    )

    # --- ToolGuides: attached to specific tools; the agent sees them as
    # extensions of the tool description when those tools are in scope.
    await agent.policies.add_tool_guide(
        name="tool_register_quality",
        content=_TOOL_GUIDE_REGISTER,
        target_tools=["tool_register"],
        prepend=False,
        priority=80,
    )
    await agent.policies.add_tool_guide(
        name="sequence_recording_rules",
        content=_TOOL_GUIDE_SEQUENCES,
        target_tools=["seq_record", "seq_validate"],
        prepend=False,
        priority=80,
    )

    # --- IntentGuard: surfaces a reminder if the agent's intent suggests it
    # is about to register a forbidden-shape tool. Server still enforces.
    await agent.policies.add_intent_guard(
        name="forbidden_tool_names",
        keywords=["question_wrapper", "gold_wrapper", "solver", "fallback_tool"],
        response=_INTENT_GUARD_FORBIDDEN,
        priority=90,
        allow_override=False,
    )

    # --- OutputFormatter: shape the final answer as JSON for downstream UI.
    await agent.policies.add_output_formatter(
        name="synthesis_summary",
        format_config=_OUTPUT_FORMATTER_SUMMARY,
        format_type="markdown",
        natural_language_trigger=[
            "summary of a Bird question synthesis",
            "final report after validating a tool sequence",
        ],
        threshold=0.6,
        priority=70,
    )

    log.info("✅ Loaded %d CUGA policies",
             len(await agent.policies.list()))


# ============================================================================
# Agent + MCP plumbing (same shape as the original — only the policy stack
# is different).
# ============================================================================

def _make_tools():
    from _mcp_bridge import load_tools
    return load_tools(["invocable_apis"])


def make_agent(require_approval: bool = False):
    from cuga import CugaAgent
    from _llm import create_llm
    agent = CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )
    return agent


def _mcp(tool: str, args: dict | None = None):
    from _mcp_bridge import call_tool
    return call_tool("invocable_apis", tool, args or {})


# ============================================================================
# Per-question instructions — now genuinely thin. Three lines, not 20.
# All design rules surface via policies when their triggers fire.
# ============================================================================

def _instructions(db: str, qid: int) -> str:
    return (
        f"Synthesize the invocable-API tool sequence for Bird question_id={qid} "
        f"in db='{db}'. Drive the full synthesis loop via tool calls. You are "
        f"done only when seq_validate returns passed=true (or 2 retries failed)."
    )


# ============================================================================
# HITL approval wiring — for the --approve mode. Demonstrates CUGA's
# action_response pathway. Auto-approves after a brief delay so the UI sees
# the request but doesn't block forever.
# ============================================================================

async def _maybe_resume_with_approval(agent, result, thread_id: str):
    """If the agent paused for tool_register approval, auto-confirm. This
    exercises the HITL surface; a real UI would prompt the user instead."""
    if "Execution paused for approval" not in (result.answer or ""):
        return result
    from cuga.backend.cuga_graph.nodes.human_in_the_loop.followup_model import (
        ActionResponse, ActionType,
    )
    approval = ActionResponse(
        action_id="tool_approval",
        response_type=ActionType.CONFIRMATION,
        confirmed=True,
        timestamp=datetime.now().isoformat(),
        user_id=thread_id,
        session_id=thread_id,
    )
    log.info("HITL auto-approving tool_register for thread %s", thread_id)
    return await agent.invoke(None, thread_id=thread_id, action_response=approval)


# ============================================================================
# FastAPI app — same endpoint surface as the original so the UI is portable.
# ============================================================================

_jobs: dict[str, dict] = {}


def _job_record(job_id: str, **patch) -> dict:
    j = _jobs.setdefault(job_id, {"job_id": job_id, "events": []})
    j.update({k: v for k, v in patch.items() if k != "event"})
    if patch.get("event"):
        j["events"].append(patch["event"])
    return j


class QuestionReq(BaseModel):
    instructions: str | None = None


def _web(port: int, require_approval: bool) -> None:
    import uvicorn

    agent = make_agent(require_approval=require_approval)

    # Configure approval policy at startup if requested.
    async def _bootstrap():
        await setup_policies(agent)
        if require_approval:
            await agent.policies.add_tool_approval(
                name="tool_register_review",
                required_tools=["tool_register"],
                approval_message="A new tool is being registered. Approve?",
                auto_approve_after=2,
                priority=95,
            )
            log.info("HITL approval ENABLED on tool_register")

    asyncio.get_event_loop().run_until_complete(_bootstrap())

    app = FastAPI(title="Bird Invocable API Creator — CUGA-native",
                  docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    async def health():
        return {"ok": True, "policies": await agent.policies.list()}

    @app.get("/policies")
    async def policies():
        return {"policies": await agent.policies.list()}

    @app.get("/databases")
    async def databases():
        try:
            r = _mcp("bird_list_databases", {}) or {}
            entries = r.get("databases") or []
            return {"databases": [e["db"] if isinstance(e, dict) else e for e in entries]}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/questions/{db}")
    async def questions(db: str):
        try:
            return _mcp("bird_list_questions", {"db": db})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/qmeta/{db}/{qid}")
    async def qmeta(db: str, qid: int):
        try:
            return _mcp("bird_get_question", {"db": db, "question_id": qid})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    def _dataset_path(db: str) -> Path:
        return _DIR / "output" / db / f"{db}_dataset.json"

    @app.get("/stats/{db}")
    async def stats(db: str):
        path = _dataset_path(db)
        if not path.exists():
            return {"db": db, "emitted": False}
        recs = json.loads(path.read_text())
        total = len(recs)
        validated = sum(1 for r in recs if r.get("validated"))
        with_seq = sum(1 for r in recs if r.get("tool_sequence"))
        tool_uses: dict[str, int] = {}
        for r in recs:
            for s in r.get("tool_sequence") or []:
                tool_uses[s["tool"]] = tool_uses.get(s["tool"], 0) + 1
        return {
            "db": db, "emitted": True,
            "total_questions": total,
            "with_sequence": with_seq,
            "validated": validated,
            "unique_tools": len(tool_uses),
            "tools_reused": sum(1 for v in tool_uses.values() if v > 1),
        }

    @app.get("/dataset_full/{db}")
    async def dataset_full(db: str):
        path = _dataset_path(db)
        if not path.exists():
            return []
        return json.loads(path.read_text())

    async def _verify(db: str, qid: int) -> dict:
        try:
            v = _mcp("seq_validate", {"db": db, "question_id": qid}) or {}
            return {"recorded": True, "passed": bool(v.get("passed")),
                    "failure_msg": v.get("failure_msg")}
        except Exception as e:
            return {"recorded": False, "passed": False, "failure_msg": str(e)}

    @app.post("/question/{db}/{qid}")
    async def question(db: str, qid: int, req: QuestionReq | None = None):
        instructions = (req.instructions if req else None) or _instructions(db, qid)
        thread_id = f"q-{db}-{qid}"
        try:
            result = await agent.invoke(instructions, thread_id=thread_id)
            result = await _maybe_resume_with_approval(agent, result, thread_id)
            verify = await _verify(db, qid)
            return {
                "db": db, "question_id": qid,
                "answer": getattr(result, "answer", str(result)),
                "verification": verify,
            }
        except Exception as e:
            log.exception("Question synthesis error")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/synthesize/{db}")
    async def synthesize(db: str):
        job_id = uuid.uuid4().hex[:8]
        _job_record(job_id, db=db, status="started", processed=0,
                    total=0, passed=0, recorded=0)

        async def _runner():
            try:
                qs = _mcp("bird_list_questions", {"db": db}) or {}
                qids = [q["question_id"] for q in qs.get("questions", [])]
                _job_record(job_id, total=len(qids))
                for qid in qids:
                    try:
                        thread_id = f"q-{db}-{qid}"
                        r = await agent.invoke(_instructions(db, qid),
                                               thread_id=thread_id)
                        await _maybe_resume_with_approval(agent, r, thread_id)
                        v = await _verify(db, qid)
                        _job_record(
                            job_id,
                            event={"qid": qid, "recorded": v["recorded"],
                                   "passed": v["passed"]},
                            processed=_jobs[job_id]["processed"] + 1,
                            recorded=_jobs[job_id]["recorded"] + (1 if v["recorded"] else 0),
                            passed=_jobs[job_id]["passed"] + (1 if v["passed"] else 0),
                        )
                    except Exception as ex:
                        _job_record(
                            job_id,
                            event={"qid": qid, "error": str(ex)},
                            processed=_jobs[job_id]["processed"] + 1,
                        )
                try:
                    emit = _mcp("dataset_emit",
                                {"db": db, "out_dir": str(_DIR / "output")}) or {}
                    _job_record(job_id, status="finished", emit=emit)
                except Exception as ex:
                    _job_record(job_id, status="finished_emit_failed", error=str(ex))
            except Exception as ex:
                _job_record(job_id, status="error", error=str(ex))

        asyncio.create_task(_runner())
        return {"job_id": job_id, "db": db}

    @app.get("/jobs/{job_id}")
    async def job_status(job_id: str):
        j = _jobs.get(job_id)
        if not j:
            return JSONResponse({"error": "no such job"}, status_code=404)
        return j

    @app.post("/emit/{db}")
    async def emit(db: str):
        try:
            return _mcp("dataset_emit",
                        {"db": db, "out_dir": str(_DIR / "output")})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    print(f"\n  Bird Invocable API Creator (CUGA-native)  →  http://127.0.0.1:{port}")
    print(f"  HITL approval on tool_register: {'ON' if require_approval else 'off'}\n")
    # Public deployment: layered, in-memory rate limiting on POST.
    from _ratelimit import install_rate_limit
    install_rate_limit(app)
    from _usage import install_usage
    install_usage(app)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ============================================================================
# Minimal UI — DB picker, question list, single-question run, policy peek.
# ============================================================================

_APP_CSS = """<style>
  body { background: var(--cds-background); }

  .wrap { max-width: 69rem; margin: 0 auto; padding: var(--cds-sp-06) var(--cds-sp-06) var(--cds-sp-08); }

  .page-title { display: flex; align-items: baseline; gap: var(--cds-sp-03); margin-bottom: var(--cds-sp-02); }
  .page-title h1 { font-size: 1.25rem; line-height: 1.4; font-weight: 600; }
  .page-title .native { font-size: 0.875rem; font-weight: 400; color: var(--cds-link-primary); }
  .sub { font-size: 0.75rem; color: var(--cds-text-helper); letter-spacing: 0.32px; margin-bottom: var(--cds-sp-06); }

  .card {
    background: var(--cds-layer-01);
    border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-05);
    margin-bottom: var(--cds-sp-05);
  }
  .row { display: flex; gap: var(--cds-sp-03); align-items: center; margin-bottom: var(--cds-sp-03); }
  .row:last-child { margin-bottom: 0; }
  .card-label { font-size: 0.75rem; font-weight: 600; letter-spacing: 0.32px; text-transform: uppercase; color: var(--cds-text-secondary); }
  .card-label.w { width: 5.5rem; }

  select.cds-select { min-height: 2.5rem; }
  .card .cds-btn { min-height: 2.5rem; flex: none; }

  #status { font-size: 0.75rem; color: var(--cds-text-helper); }

  #policies { font-size: 0.75rem; display: flex; flex-wrap: wrap; gap: var(--cds-sp-02); }
  #qcount { font-size: 0.75rem; color: var(--cds-text-helper); margin-left: auto; }

  .qlist {
    max-height: 50vh; overflow: auto;
    border: 1px solid var(--cds-border-subtle);
    background: var(--cds-layer-02);
  }
  .qrow {
    padding: var(--cds-sp-03) var(--cds-sp-04);
    border-bottom: 1px solid var(--cds-border-subtle);
    cursor: pointer; font-size: 0.75rem;
    display: flex; gap: var(--cds-sp-03); align-items: center;
    transition: background var(--cds-dur-fast) var(--cds-ease-productive);
  }
  .qrow:last-child { border-bottom: none; }
  .qrow:hover { background: var(--cds-layer-hover); }
  .qrow.sel { background: var(--cds-support-info-bg); box-shadow: inset 2px 0 0 var(--cds-interactive); }
  .qid { color: var(--cds-link-primary); font-weight: 600; width: 2.5rem; font-family: var(--cds-font-mono); }

  pre {
    font-family: var(--cds-font-mono);
    font-size: 0.6875rem; line-height: 1.5;
    background: var(--cds-layer-02);
    border: 1px solid var(--cds-border-subtle);
    color: var(--cds-text-primary);
    padding: var(--cds-sp-04);
    white-space: pre-wrap; max-height: 280px; overflow: auto;
  }

  .pill {
    display: inline-flex; align-items: center;
    padding: 0 var(--cds-sp-03); height: 1.5rem;
    border-radius: 0.9375rem;
    background: var(--cds-support-info-bg); color: var(--cds-link-primary);
    font-size: 0.6875rem; letter-spacing: 0.16px; white-space: nowrap;
  }
  .pill-warn { background: var(--cds-support-warning-bg); color: var(--cds-text-primary); }

  #insp .meta-label { font-size: 0.75rem; color: var(--cds-text-helper); margin: var(--cds-sp-04) 0 var(--cds-sp-02); letter-spacing: 0.32px; }
  #insp .q-text { font-size: 0.875rem; line-height: 1.5; color: var(--cds-text-primary); }
  .insp-empty { color: var(--cds-text-placeholder); font-size: 0.875rem; }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Bird&nbsp;Invocable&nbsp;API&nbsp;Creator</div>
  <div class="cds-header__actions">
    <span class="cds-helper-01">Playbooks · ToolGuides · IntentGuard · OutputFormatter</span>
    <span class="cds-tag cds-tag--blue">CUGA-native</span>
  </div>
</header>

<div class="wrap">

<div class="page-title">
  <h1>🪶 Bird Invocable API Creator</h1>
  <span class="native">CUGA-native</span>
</div>
<div class="sub">Thin prompt + Playbooks + ToolGuides + IntentGuard + OutputFormatter</div>

<div class="card">
  <div class="row">
    <strong class="card-label w">Database</strong>
    <select id="db" class="cds-select" style="flex:1"></select>
    <button class="cds-btn cds-btn--sm" onclick="batch()">⚡ Batch</button>
    <button class="cds-btn cds-btn--secondary cds-btn--sm" onclick="loadAll()">↺</button>
  </div>
  <div id="status"></div>
</div>

<div class="card">
  <div class="row"><strong class="card-label">Active CUGA policies</strong></div>
  <div id="policies"></div>
</div>

<div class="card">
  <div class="row"><strong class="card-label">Questions</strong>
    <span id="qcount"></span>
  </div>
  <div id="qlist" class="qlist"></div>
</div>

<div class="card">
  <div class="row"><strong class="card-label">Inspector</strong></div>
  <div id="insp"><span class="insp-empty">Pick a question above.</span></div>
</div>

</div>

<script>
let CURRENT_DB=null, CURRENT_QID=null, QUESTIONS=[], DATASET={};

async function init() {
  const r = await fetch('/databases').then(r=>r.json());
  const sel = document.getElementById('db');
  sel.innerHTML = (r.databases||[]).map(d=>`<option>${d}</option>`).join('');
  sel.onchange = loadAll;
  CURRENT_DB = sel.value;
  await loadAll();
  loadPolicies();
}

async function loadPolicies() {
  const r = await fetch('/policies').then(r=>r.json());
  document.getElementById('policies').innerHTML = (r.policies||[]).map(p=>
    `<span class="pill">${p.type}: ${p.name}</span>`).join(' ');
}

async function loadAll() {
  CURRENT_DB = document.getElementById('db').value;
  const r = await fetch('/questions/'+CURRENT_DB).then(r=>r.json());
  QUESTIONS = (r&&r.questions)||(r&&r.data&&r.data.questions)||[];
  try {
    const all = await fetch('/dataset_full/'+CURRENT_DB).then(r=>r.json());
    DATASET = {};
    if (Array.isArray(all)) all.forEach(rec=>DATASET[rec.question_id]=rec);
  } catch(e){ DATASET={}; }
  renderQs();
}

function renderQs() {
  document.getElementById('qcount').textContent = QUESTIONS.length;
  document.getElementById('qlist').innerHTML = QUESTIONS.map(q=>{
    const rec = DATASET[q.question_id];
    const icon = !rec ? '·' : rec.validated ? '✓' : rec.tool_sequence ? '✗' : '·';
    return `<div class="qrow ${CURRENT_QID===q.question_id?'sel':''}" onclick="pickQ(${q.question_id})">
      <span class="qid">#${q.question_id}</span>
      <span style="color:var(--cds-interactive);width:14px">${icon}</span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(q.question)}</span>
    </div>`;
  }).join('');
}

async function pickQ(qid) {
  CURRENT_QID = qid;
  renderQs();
  const meta = await fetch(`/qmeta/${CURRENT_DB}/${qid}`).then(r=>r.json());
  const data = (meta&&meta.data)||meta||{};
  const rec = DATASET[qid] || null;
  document.getElementById('insp').innerHTML = `
    <div class="q-text">${esc(data.question||'')}</div>
    <div class="meta-label">Gold SQL:</div>
    <pre>${esc(data.SQL||'(unavailable)')}</pre>
    ${rec ? `
      <div class="meta-label">Recorded sequence (validated=${rec.validated}):</div>
      <pre>${esc(JSON.stringify(rec.tool_sequence,null,2))}</pre>
    `:''}
    <button class="cds-btn cds-btn--sm" style="margin-top:var(--cds-sp-04)" onclick="runQ()">▶ Run agent on this question</button>
    <pre id="ans" style="display:none;margin-top:var(--cds-sp-04)"></pre>
  `;
}

async function runQ() {
  const ans = document.getElementById('ans');
  ans.style.display='block'; ans.textContent='Running…';
  const r = await fetch(`/question/${CURRENT_DB}/${CURRENT_QID}`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'
  }).then(r=>r.json());
  ans.textContent = (r.answer||r.error||'') +
    (r.verification ? `\\n\\n— verification: passed=${r.verification.passed}` +
      (r.verification.failure_msg?` failure=${r.verification.failure_msg}`:'') : '');
  await loadAll();
}

async function batch() {
  const s = document.getElementById('status');
  s.textContent='Starting…';
  const r = await fetch('/synthesize/'+CURRENT_DB, {method:'POST'}).then(r=>r.json());
  const t = setInterval(async()=>{
    const j = await fetch('/jobs/'+r.job_id).then(r=>r.json());
    s.textContent = `[${j.status}] ${j.processed||0}/${j.total||0} · ${j.recorded||0} recorded · ${j.passed||0} passed`;
    if (['finished','finished_emit_failed','error'].includes(j.status)) { clearInterval(t); await loadAll(); }
  }, 4000);
}

function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
init();
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("Bird Invocable API Creator — CUGA-native")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)


# ============================================================================
# Entry
# ============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=28816)
    parser.add_argument("--provider", "-p", default=None)
    parser.add_argument("--model", "-m", default=None)
    parser.add_argument("--approve", action="store_true",
                        help="Require HITL approval on tool_register (auto-confirms after 2s)")
    args = parser.parse_args()
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model
    _web(args.port, args.approve)
