"""
Ouroboros — CUGA finds its next client (multi-agent edition)
============================================================

A CugaSupervisor orchestrating 7 specialist CugaAgents. Each specialist is
backed by one skill (SKILL.md + tools.py) under ./skills/. The supervisor's
planner decides which specialist to delegate to, each runs in its own
context, and the pitch+email writer specialist returns the final structured
leads JSON which the server parses and stores per-thread.

CUGA capabilities tapped (skills-branch SDK):
  • CugaSupervisor        — A2A multi-agent orchestration
  • CugaAgent             — per-specialist plan/execute graph
  • CugaLite step limits  — bounded planner per agent
  • Policies              — intent_guard, tool_guide, output_formatter
  • Skills (declarative)  — SKILL.md + tools.py, host-loaded at startup

Run:
    python main.py --port 28822
    python main.py --provider anthropic
    python main.py --provider rits --model gpt-oss-120b

Then open: http://127.0.0.1:28822

Env vars:
    LLM_PROVIDER          rits | anthropic | openai | watsonx | litellm | ollama
    LLM_MODEL             model name override
    AGENT_SETTING_CONFIG  CUGA settings TOML (defaulted in main)
    CUGA_TARGET=ce        forces public Code Engine MCP URLs
    MCP_<NAME>_URL        per-server URL override
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Path bootstrap — must come before local imports ─────────────────────
_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in (str(_DIR), str(_DEMOS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Default to the hosted Code Engine MCP servers; user-set value still wins.
os.environ.setdefault("CUGA_TARGET", "ce")

# CUGA's `cuga.config` module reads AGENT_SETTING_CONFIG once at import
# time and pins the agent-internal LLM TOML. Setting it inside
# make_supervisor() is too late — by then specialists.py has already
# imported cuga.sdk indirectly. So we resolve it here, before the first
# cuga import in this process.
_AGENT_SETTING_CONFIG = {
    "rits":      "settings.rits.toml",
    "watsonx":   "settings.watsonx.toml",
    "openai":    "settings.openai.toml",
    "groq":      "settings.groq.toml",
    "litellm":   "settings.litellm.toml",
    "anthropic": "settings.openai.toml",   # cuga has no "anthropic"
                                            # platform; openai TOML is the
                                            # closest fallback. Internal
                                            # nodes will fail unless the
                                            # user runs a proxy or we
                                            # monkey-patch LLMManager.
    "ollama":    "settings.openai.toml",
}
_provider = (os.getenv("LLM_PROVIDER") or "rits").lower()
os.environ.setdefault(
    "AGENT_SETTING_CONFIG",
    _AGENT_SETTING_CONFIG.get(_provider, "settings.rits.toml"),
)


def _patch_executor_timeout(seconds: int = 180) -> None:
    """Bump CUGA's hardcoded 30s code-executor timeout.

    `code_executor.py:148` calls
        await executor.execute(..., timeout=30)
    with no env / config override. A specialist's CugaLite graph runs
    multiple LLM steps for one delegation, and 30s is too tight for
    them — scout-on-cold-LLM regularly takes 30–60s. We monkey-patch
    LocalExecutor.execute so any caller-provided timeout < `seconds`
    is bumped up. Idempotent.
    """
    try:
        from cuga.backend.cuga_graph.nodes.cuga_lite.executors.local import (
            local_executor as _le,
        )
    except ImportError:
        return
    if getattr(_le.LocalExecutor.execute, "_ouroboros_patched", False):
        return
    _orig = _le.LocalExecutor.execute

    async def _patched(self, *args, timeout: int = 30, **kwargs):
        bumped = max(int(timeout or 30), seconds)
        return await _orig(self, *args, timeout=bumped, **kwargs)

    _patched._ouroboros_patched = True   # type: ignore[attr-defined]
    _le.LocalExecutor.execute = _patched   # type: ignore[assignment]
    log = __import__("logging").getLogger(__name__)
    log.info("patched LocalExecutor.execute timeout floor to %ds", seconds)


_patch_executor_timeout(180)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ui import _HTML


# ── Per-thread server-side session ──────────────────────────────────────
# The supervisor itself doesn't have inline session-state hooks on this
# branch, so the server holds the cross-turn memory: location, categories,
# pitch_focus, plus the most recent leads board parsed from the writer
# specialist's output.

_sessions: dict[str, dict] = {}


def _get_session(thread_id: str) -> dict:
    if thread_id not in _sessions:
        _sessions[thread_id] = {
            "target_location": "",
            "categories":      [],
            "pitch_focus":     "",
            "leads":           None,
            "history":         [],
        }
    return _sessions[thread_id]


def _format_session_brief(session: dict) -> str:
    parts = []
    if session["target_location"]:
        parts.append(f'location={session["target_location"]!r}')
    if session["categories"]:
        parts.append(f'categories={session["categories"]}')
    if session["pitch_focus"]:
        parts.append(f'pitch_focus={session["pitch_focus"]!r}')
    return "; ".join(parts) if parts else "(empty)"


# ── Extract the structured leads JSON from the supervisor's text answer ──
# The pitch_email_writer specialist is instructed to emit a fenced ```json
# block. We strip that off, parse it, and store it in the session.

_JSON_FENCE_RE = re.compile(r"```json\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)


# ── Per-turn run metadata (so we can debug what each stage actually produced) ─
_RUNS_DIR = _DIR / "runs"
try:
    _RUNS_DIR.mkdir(exist_ok=True)
except Exception:
    pass


def _coerce(value):
    """Best-effort coerce a supervisor variable to JSON-safe form."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_coerce(v) for v in value]
    if isinstance(value, dict):
        return {k: _coerce(v) for k, v in value.items()}
    return repr(value)


def _harvest_supervisor_state(supervisor) -> dict:
    """Pull variables + chat messages out of the supervisor's last state.
    The supervisor's variables_manager preserves every variable created
    during code execution (including `final` from phase 3); the chat
    messages preserve every `Execution output:` line.
    """
    out: dict = {"variables": {}, "stages": []}

    try:
        vm = supervisor.variables_manager
        for name in vm.get_variable_names():
            try:
                out["variables"][name] = _coerce(vm.get_variable(name))
            except Exception as exc:
                out["variables"][name] = f"<unreadable: {exc}>"
    except Exception as exc:
        out["variables"]["__error__"] = str(exc)

    try:
        state = supervisor._supervisor_state
        messages = (
            state.get("supervisor_chat_messages", [])
            if isinstance(state, dict)
            else getattr(state, "supervisor_chat_messages", []) or []
        )
        for i, msg in enumerate(messages):
            role = type(msg).__name__
            content = getattr(msg, "content", "") or ""
            if not isinstance(content, str):
                content = str(content)
            stage = {
                "i":       i,
                "role":    role,
                "len":     len(content),
                "content": content[:12000],
            }
            if content.startswith("Execution output:"):
                stage["kind"] = "execution_output"
            out["stages"].append(stage)
    except Exception as exc:
        out["stages"].append({"error": str(exc)})

    return out


def _writer_output_from_state(supervisor) -> str | None:
    """Best-effort recovery of the writer specialist's full output.

    The supervisor's outer Conversational LLM tends to paraphrase the
    writer's JSON down to a one-liner, dropping the lead board. But the
    writer's actual output is preserved in two places:

      1. supervisor.variables_manager['final']  (the prelude binds
         `final = await delegate_to_pitch_email_writer(...)`)
      2. supervisor_chat_messages — the Execution output line that
         followed phase 3's `print(final)`.

    Try (1) first; fall back to (2).
    """
    try:
        vm = supervisor.variables_manager
        names = list(vm.get_variable_names())
        for cand in ("final", "writer_output", "lead_board", "enriched_list"):
            if cand in names:
                val = vm.get_variable(cand)
                if isinstance(val, str) and '"leads"' in val:
                    return val
    except Exception as exc:
        log.debug("variables_manager unreadable: %s", exc)

    try:
        state = supervisor._supervisor_state
        messages = (
            state.get("supervisor_chat_messages", [])
            if isinstance(state, dict)
            else getattr(state, "supervisor_chat_messages", []) or []
        )
        # Walk in reverse — the writer's print(final) is the LAST
        # Execution output before the supervisor's conversational turn.
        for msg in reversed(messages):
            content = getattr(msg, "content", "") or ""
            if not isinstance(content, str):
                continue
            if content.startswith("Execution output:") and '"leads"' in content:
                return content[len("Execution output:"):].lstrip("\n").strip()
    except Exception as exc:
        log.debug("chat-messages scan failed: %s", exc)

    return None


def _format_elapsed(ms: int) -> str:
    s = ms / 1000.0
    if s < 1:
        return f"{ms} ms"
    if s < 60:
        return f"{s:.1f} s"
    m = int(s // 60)
    rem = s - m * 60
    return f"{m}m {rem:.0f}s"


def _save_run(thread_id: str, question: str, answer: str,
              leads: dict | None, supervisor,
              started_at: datetime, elapsed_ms: int) -> str | None:
    """Persist this turn's metadata to runs/<thread_id>/<ts>.json so we
    can pick apart what each stage actually produced. Best-effort —
    failure here must never break the /ask response."""
    try:
        ts       = datetime.now(timezone.utc)
        run_dir  = _RUNS_DIR / re.sub(r"[^a-zA-Z0-9_\-]", "_", thread_id)[:64]
        run_dir.mkdir(parents=True, exist_ok=True)
        fname    = ts.strftime("%Y%m%dT%H%M%SZ") + ".json"
        path     = run_dir / fname
        record = {
            "thread_id":         thread_id,
            "timestamp":         ts.isoformat(),
            "started_at":        started_at.isoformat(),
            "elapsed_ms":        elapsed_ms,
            "elapsed_human":     _format_elapsed(elapsed_ms),
            "question":          question,
            "answer_full":       answer or "",
            "answer_len":        len(answer or ""),
            "leads_extracted":   bool(leads),
            "leads_count":       len(leads.get("leads", []) or []) if leads else 0,
            "leads":             leads,
            "supervisor_state":  _harvest_supervisor_state(supervisor),
        }
        path.write_text(json.dumps(record, indent=2, default=str, ensure_ascii=False))
        log.info("[%s] run saved: %s (%s, stages=%d, vars=%d)",
                 thread_id[:8], path, record["elapsed_human"],
                 len(record["supervisor_state"].get("stages", [])),
                 len(record["supervisor_state"].get("variables", {})))
        return str(path)
    except Exception as exc:
        log.warning("[%s] run save failed: %s", thread_id[:8], exc)
        return None


def _extract_leads_json(text: str) -> dict | None:
    """Extract the writer's leads object from the supervisor's final answer.

    The writer fences its JSON in ```json``` per its SKILL.md, but the
    supervisor's planner sometimes summarises and strips the fence,
    leaving bare JSON or JSON-with-prose. Try four extraction shapes:
      1. fenced ```json``` block
      2. whole text as JSON
      3. first balanced { … } that contains a "leads" key
      4. last balanced { … } in the text (some planners append extra
         prose after the JSON; we want the JSON, not the prose).
    """
    if not text:
        return None

    # 1. Fenced
    for raw in _JSON_FENCE_RE.findall(text):
        try:
            obj = json.loads(raw.strip())
            if isinstance(obj, dict) and "leads" in obj:
                return obj
        except json.JSONDecodeError:
            continue

    # 2. Whole text
    try:
        obj = json.loads(text.strip())
        if isinstance(obj, dict) and "leads" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    # 3 + 4: balanced-brace scan. Find every top-level { ... } in the
    # text and return the first/last one that has a "leads" key.
    candidates: list[dict] = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start >= 0:
                chunk = text[start:i + 1]
                try:
                    obj = json.loads(chunk)
                    if isinstance(obj, dict) and "leads" in obj:
                        candidates.append(obj)
                except json.JSONDecodeError:
                    pass
                start = -1
    # Prefer the LAST balanced JSON with leads — the planner sometimes
    # writes a short pre-amble dict, then the real board.
    if candidates:
        return candidates[-1]

    return None


# ── Cheap user-input parser for session updates ─────────────────────────
# We keep this tiny and conservative — we only want to give the supervisor
# the minimum context (location + focus) it needs in the prompt. The agent
# doesn't read the session dict directly.

_LOCATION_HINT_RE = re.compile(
    r"\b(?:in|near|around|at)\s+([A-Z][\w &\-,'.]+?)(?:\s+(?:that|for|with|focus|pitch|—)|[?.,]|$)",
    re.IGNORECASE,
)


def _maybe_update_session(session: dict, question: str) -> None:
    """Heuristic: catch a location mention and stash it. The supervisor's
    own planner is the source of truth — this just helps continuity for
    follow-up questions where the user says 'now scout salons there'."""
    m = _LOCATION_HINT_RE.search(question)
    if m and not session["target_location"]:
        session["target_location"] = m.group(1).strip().rstrip(",.")


# ── Supervisor build ────────────────────────────────────────────────────

# Prepended to every /ask payload. CugaSupervisor.description is dead
# (cuga_supervisor_graph.py:379 hardcodes special_instructions=None);
# the user message is the only injection point.
#
# CRITICAL: do NOT include any triple-backtick sequences in this string.
# The supervisor extracts code via re.findall(r'```python(.*?)```')
# (cuga_supervisor_graph.py:35,63). Any extra triple-backtick in a code
# block — even inside a regex literal or a quoted example — corrupts
# the extraction (the non-greedy match closes on the wrong fence,
# producing malformed code with no print(), and the SDK then
# misclassifies the response as "final text answer, no code"). Use the
# words "JSON-fenced" / "code fence" instead of literal triple-backticks
# in any prose; use neutral angle brackets <like> in any code examples
# that need to allude to fences.
_TASK_PRELUDE = """\
=== OUROBOROS LEAD-HUNT CONTRACT ===

Every user request below is a lead-hunt. You are the supervisor; you
delegate to specialists. Run THREE PHASES in order. Phase 3 is
MANDATORY — the UI cannot render anything without it.

CORE DATA STRUCTURE: a single dict `enrichments` keyed by the candidate
index (0, 1, 2). Each value is itself a dict that accumulates the per-
candidate enrichment fields as the five sweeps run. By phase 3 every
candidate has its own self-contained bundle, so the writer never has
to align parallel lists.

PHASE 1 — scout + parse + initialize.
    user_question = <user request as Python string>
    scout_result = await delegate_to_scout(task=user_question)
    try:
        data = json.loads(scout_result.strip())
        candidates = data.get("candidates", []) or []
    except (json.JSONDecodeError, ValueError, AttributeError):
        data, candidates = {}, []
    top = candidates[:3]
    enrichments = {}
    for i in range(len(top)):
        enrichments[i] = {"candidate": top[i]}
    print(f"Got {len(candidates)} candidates; deep-diving top {len(top)}")

PHASE 2 — five specialist sweeps. Each sweep is ONE code block. Inside
the block, loop with enumerate(top) and call exactly ONE specialist;
write every return value into `enrichments[i][<key>]`. Run ALL FIVE
sweeps, in the exact order below. Do NOT skip any sweep. Do NOT
proceed to phase 3 until all five have completed. If a candidate has
no website, store the empty string under its key so the slot still
exists.

SWEEP 1 — voice_of_customer (every candidate):
    for i, c in enumerate(top):
        r = await delegate_to_voice_of_customer(
            task=f"Find verbatim review friction for {json.dumps(c)} in {data.get('display_name', '')}"
        )
        enrichments[i]["voc"] = r
    print(enrichments)

SWEEP 2 — site_auditor (skip empty website):
    for i, c in enumerate(top):
        if not c.get("website"):
            enrichments[i]["audit"] = ""
            continue
        r = await delegate_to_site_auditor(
            task=f"Audit this business: {json.dumps(c)}"
        )
        enrichments[i]["audit"] = r
    print(enrichments)

SWEEP 3 — revenue_estimator (every candidate):
    for i, c in enumerate(top):
        r = await delegate_to_revenue_estimator(
            task=f"Estimate ARR band for {json.dumps(c)} in {data.get('display_name', '')}"
        )
        enrichments[i]["revenue"] = r
    print(enrichments)

SWEEP 4 — person_finder (skip empty website):
    for i, c in enumerate(top):
        if not c.get("website"):
            enrichments[i]["person"] = ""
            continue
        r = await delegate_to_person_finder(
            task=f"Find decision-maker + email pattern for {json.dumps(c)}"
        )
        enrichments[i]["person"] = r
    print(enrichments)

SWEEP 5 — stack_scanner (skip empty website):
    for i, c in enumerate(top):
        if not c.get("website"):
            enrichments[i]["stack"] = ""
            continue
        r = await delegate_to_stack_scanner(
            task=f"Fingerprint third-party tools at {c.get('website', '')}"
        )
        enrichments[i]["stack"] = r
    print(enrichments)

PHASE 3 — writer. Build a SINGLE self-contained enriched_list so the
writer never has to zip parallel lists. Each entry is a complete bundle:
the candidate plus its audit / voc / revenue / person / stack.

    enriched_list = [enrichments[i] for i in range(len(top))]
    location_obj = {
        "location":     data.get("location", ""),
        "display_name": data.get("display_name", ""),
        "lat":          data.get("lat"),
        "lon":          data.get("lon"),
    }
    writer_task = (
        "Build the final ranked lead board per your SKILL.md schema.\\n\\n"
        f"User request: {user_question}\\n\\n"
        f"Location: {json.dumps(location_obj)}\\n\\n"
        f"All scout candidates (use #4..N as preliminary, deep_dive=false leads): {json.dumps(candidates)}\\n\\n"
        f"Enriched top {len(top)} (each dict carries its own audit / voc / revenue / person / stack):\\n"
        f"{json.dumps(enriched_list)}\\n\\n"
        "REQUIREMENTS — read these carefully:\\n"
        "1. Top 3 leads MUST have deep_dive=true. Every other field on the lead schema must be populated from the matching enrichment bundle (do not leave them null).\\n"
        "2. fit_score MUST be an integer 1-10. Never null.\\n"
        "3. pitch MUST be 60-150 words and cite at least one CONCRETE signal pulled from this lead's voc / audit / stack / person bundle. Quote a review verbatim if voc has one. Name a missing website feature if audit has one. Name an incumbent tool if stack has one. End with the CUGA capability that closes the gap and a measurable lift.\\n"
        "4. email_draft MUST have non-empty subject AND body, per your SKILL.md email rules.\\n"
        "5. Pull review-citation URLs from voc into evidence[]. Pull website_signals from audit. Pull stack into stack. Pull owner name + email_guess from person. Pull ARR band from revenue.\\n"
        "6. If a particular bundle field is empty, OMIT only that signal — do not fabricate. The pitch must still cite at least one real signal from another field.\\n"
        "7. Lower-ranked candidates (4..N): deep_dive=false, 1-2 sentence preliminary pitch from OSM data alone, skip the deep-dive fields per SKILL.md.\\n"
        "8. Use the location object verbatim for the top-level location/display_name/lat/lon.\\n\\n"
        "Output the JSON-fenced lead board first, then 2 short paragraphs of summary."
    )
    final = await delegate_to_pitch_email_writer(task=writer_task)
    print(final)

RETURN. After phase 3 returns, reply with the writer's output verbatim
as plain text (TYPE 2, no code fence). Do not paraphrase, do not wrap,
do not summarise.

HARD RULES:
  - Initialize `enrichments` dict in phase 1 BEFORE any sweep. Every
    phase-2 sweep WRITES into enrichments[i][<key>] for every i in
    range(len(top)). Skipped iterations write the empty string.
  - One specialist kind per code block. Loop with enumerate(top) inside
    the block to call that specialist for every candidate.
  - Every code block must contain at least one print() — the
    supervisor's code extractor requires it.
  - Never write three-backticks-in-a-row inside any code block. The
    extractor mis-truncates and your block is silently dropped.
  - Run ALL FIVE sweeps before calling the writer. Do not call the
    writer twice. Do not skip phase 3.
  - Reference only variables that have already been created in a
    prior code block.
  - If a specialist errors (timeout, exception), set enrichments[i][<key>]
    to the empty string and continue. Do not abort the cascade.
  - If `top` is empty (scout returned no candidates), skip phase 2 and
    call phase 3 with enriched_list = [].

=== USER REQUEST ===
"""


async def _attach_policies(supervisor) -> None:
    """Wire CUGA policies onto the supervisor's specialists.

    The policy store is shared across all CugaAgent instances in this
    process (one sqlite-vec DB), so we add each policy ONCE on a
    representative agent and let the runtime trigger filters
    (target_tools, AlwaysTrigger on agent response) scope enforcement at
    call time:

      - intent_guard `ouroboros_abuse_guard` — keyword-triggered; fires
        whenever any specialist's input contains harassment / doxxing
        intent. Added once on the writer; visible to all.
      - tool_guide `prefer_independents` — `target_tools=
        ["find_local_businesses"]` scopes it to the scout's tool.
      - output_formatter `leads_board_formatter` — fires on
        agent_response with keywords {"leads", "lead board"} so it
        matches only the writer's final synthesis, not specialists' raw
        returns.

    `reset_policy_storage=True` on the *first* agent built clears the
    shared DB so re-runs don't accumulate duplicates.
    """
    agents = getattr(supervisor, "_agents", {}) or {}
    if not agents:
        log.warning("no agents on supervisor; skipping policy attach")
        return

    writer = agents.get("pitch_email_writer")
    scout  = agents.get("scout")
    primary = writer or next(iter(agents.values()))

    # Reset shared storage so a process restart doesn't accumulate
    # duplicates of the same policy. Note: the policy DB lives at
    # <cuga_sdk_path>/dbs/cuga.db (NOT inside the app), so without this
    # clear, every restart leaves stale policies behind.
    try:
        ok = await primary.policies.clear()
        log.info("policy store cleared: %s", ok)
    except Exception as exc:
        log.debug("policy store clear skipped: %s", exc)

    # 1. Intent guard — wide-scope refusal.
    try:
        await primary.policies.add_intent_guard(
            name="ouroboros_abuse_guard",
            keywords=["harass", "dox", "stalk", "scrape personal",
                       "find someone's home address", "track down"],
            response=(
                "I can help with finding businesses that would benefit "
                "from a CUGA agent — not with locating individuals or "
                "personal information. Try rephrasing in terms of a "
                "business or a neighborhood."
            ),
        )
    except Exception as exc:
        log.warning("intent_guard skipped: %s", exc)

    # 2. Tool guide — only the find_local_businesses tool gets enriched.
    if scout is not None:
        try:
            await scout.policies.add_tool_guide(
                name="prefer_independents",
                content=(
                    "When you see global chains in the result list "
                    "(Starbucks, McDonald's, Hilton, Subway, KFC, etc.), "
                    "drop them from your shortlist. Independent 1–5 "
                    "location businesses are the target."
                ),
                target_tools=["find_local_businesses"],
            )
        except Exception as exc:
            log.warning("tool_guide skipped: %s", exc)

    # 3. Output formatter — keyword-trigger on the writer's response so
    #    it only fires when the writer's prose mentions "leads".
    if writer is not None:
        try:
            await writer.policies.add_output_formatter(
                name="leads_board_formatter",
                format_config=(
                    "Always emit a fenced ```json``` block containing the "
                    "leads schema documented in your SKILL.md, followed "
                    "by a 2-paragraph prose summary that names the top 3 "
                    "leads and their angle, ending with one line of next "
                    "steps."
                ),
                format_type="markdown",
                keywords=["leads", "lead board", "shortlist", "ranked"],
            )
        except Exception as exc:
            log.warning("output_formatter skipped: %s", exc)


def make_supervisor():
    from cuga.sdk import CugaSupervisor
    from _llm import create_llm
    from specialists import make_all

    # AGENT_SETTING_CONFIG is set at module top (before cuga import).
    model = create_llm(
        provider=os.getenv("LLM_PROVIDER"),
        model=os.getenv("LLM_MODEL"),
    )

    agents = make_all(model=model)
    supervisor = CugaSupervisor(
        agents=agents,
        model=model,
        # description= is dead in this SDK branch (never rendered into
        # the supervisor's prompt). We inject the cascade rules via
        # _TASK_PRELUDE on the user message in /ask instead.
        # Step accounting (each block = 2 steps: model + execute):
        #   phase 1 (scout+parse+init):  2
        #   phase 2 (5 specialists × up to 3 candidates, often <15
        #             due to website conditionals): 20–30
        #   phase 3 (writer):            2
        #   misc planner indecision/retries: 5–15
        # 100 caps comfortably over the median 35–50.
        cuga_lite_max_steps=100,
    )
    return supervisor


# ── Request models ──────────────────────────────────────────────────────
class AskReq(BaseModel):
    question: str
    thread_id: str = ""


# ── HTTP server ──────────────────────────────────────────────────────────
def _web(port: int) -> None:
    import uvicorn

    app = FastAPI(title="Ouroboros", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    _supervisor = None
    _policies_attached = False
    _init_lock = asyncio.Lock()

    async def _get_supervisor():
        nonlocal _supervisor, _policies_attached
        async with _init_lock:
            if _supervisor is None:
                log.info("Initialising CugaSupervisor with 7 specialists…")
                _supervisor = make_supervisor()
                log.info("Supervisor ready; attaching policies…")
                try:
                    await _attach_policies(_supervisor)
                    _policies_attached = True
                except Exception as exc:
                    log.warning("policy attach partially failed: %s", exc)
                log.info("Specialists: %s",
                         list(getattr(_supervisor, "_agents", {}).keys()))
            return _supervisor

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.post("/ask")
    async def api_ask(req: AskReq):
        thread_id = req.thread_id or str(uuid.uuid4())
        session = _get_session(thread_id)
        _maybe_update_session(session, req.question)

        # Brief the supervisor with prior session state inline. Keeps the
        # planner stateless across HTTP turns while preserving continuity.
        # The _TASK_PRELUDE prefix is the ONLY way to inject orchestration
        # rules in this CUGA branch — the supervisor's `description` kwarg
        # is stored but never rendered into the prompt template.
        session_brief = _format_session_brief(session)
        augmented = (
            f"{_TASK_PRELUDE}"
            f"{req.question}\n\n"
            f"[session:{session_brief}] "
            f"[thread:{thread_id}]"
        )
        import time as _time
        started_at = datetime.now(timezone.utc)
        t0 = _time.monotonic()
        try:
            supervisor = await _get_supervisor()
            result = await supervisor.invoke(augmented, thread_id=thread_id)
            elapsed_ms = int((_time.monotonic() - t0) * 1000)
            log.info("[%s] supervisor.invoke completed in %s",
                     thread_id[:8], _format_elapsed(elapsed_ms))
            answer = (
                result.answer if hasattr(result, "answer") else str(result)
            )

            # Parse the writer's fenced JSON, if present, into the session.
            leads = _extract_leads_json(answer)

            # Fallback: the supervisor's outer Conversational LLM frequently
            # paraphrases the writer's JSON board down to a useless one-liner
            # ("Here's the complete enriched lead board…"). When that
            # happens, _extract_leads_json returns None even though the
            # writer DID produce a valid board. Recover the writer's raw
            # output from the supervisor's variables_manager / chat
            # history, and use it as the user-facing answer too.
            if not leads:
                writer_raw = _writer_output_from_state(supervisor)
                if writer_raw:
                    log.info("[%s] supervisor paraphrased; recovered writer "
                             "output (%d chars)",
                             thread_id[:8], len(writer_raw))
                    recovered = _extract_leads_json(writer_raw)
                    if recovered:
                        leads  = recovered
                        # Use the writer's verbatim output as the chat reply
                        # — the supervisor's paraphrase has lost the data.
                        answer = writer_raw

            if leads:
                leads["_at"] = datetime.now(timezone.utc).isoformat()
                session["leads"] = leads
                if leads.get("location"):
                    session["target_location"] = leads["location"]
                # Mirror the leads' own location/categories/focus for UI hints.
                session["history"].insert(0, leads)
                session["history"] = session["history"][:6]
                log.info("[%s] leads parsed: %d items in %s",
                         thread_id[:8],
                         len(leads.get("leads", []) or []),
                         leads.get("location", "?"))
            else:
                log.warning("[%s] no leads extracted from supervisor answer "
                            "(answer length: %d chars)",
                            thread_id[:8], len(answer or ""))

            # Persist per-turn metadata for debugging — every stage's
            # output, all supervisor variables, the extracted leads.
            _save_run(thread_id, req.question, answer, leads, supervisor,
                      started_at=started_at, elapsed_ms=elapsed_ms)

            return {
                "answer":        answer,
                "thread_id":     thread_id,
                "elapsed_ms":    elapsed_ms,
                "elapsed_human": _format_elapsed(elapsed_ms),
            }
        except Exception as exc:
            elapsed_ms = int((_time.monotonic() - t0) * 1000)
            log.exception("Supervisor invocation failed after %s",
                          _format_elapsed(elapsed_ms))
            return JSONResponse(
                status_code=500,
                content={
                    "answer":        f"Error: {exc}",
                    "thread_id":     thread_id,
                    "elapsed_ms":    elapsed_ms,
                    "elapsed_human": _format_elapsed(elapsed_ms),
                },
            )

    @app.get("/session/{thread_id}")
    async def api_session(thread_id: str):
        return _get_session(thread_id)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/runs/{thread_id}")
    async def api_runs(thread_id: str):
        """List saved per-turn metadata for a thread."""
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", thread_id)[:64]
        run_dir = _RUNS_DIR / safe
        if not run_dir.exists():
            return {"thread_id": thread_id, "runs": []}
        files = sorted(run_dir.glob("*.json"))
        return {
            "thread_id": thread_id,
            "runs": [
                {"file": f.name, "size": f.stat().st_size,
                 "url": f"/runs/{thread_id}/{f.name}"}
                for f in files
            ],
        }

    @app.get("/runs/{thread_id}/{filename}")
    async def api_run_detail(thread_id: str, filename: str):
        """Return the saved metadata for one turn."""
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", thread_id)[:64]
        # filename arrives untrusted — reject anything that's not a
        # bare ts-stamped json file in the thread's own dir.
        if not re.fullmatch(r"\d{8}T\d{6}Z\.json", filename):
            return JSONResponse(status_code=400, content={"error": "bad filename"})
        path = _RUNS_DIR / safe / filename
        if not path.exists():
            return JSONResponse(status_code=404, content={"error": "not found"})
        try:
            return json.loads(path.read_text())
        except Exception as exc:
            return JSONResponse(status_code=500,
                                content={"error": f"read failed: {exc}"})

    @app.get("/specialists")
    async def specialists():
        sup = await _get_supervisor()
        agents = getattr(sup, "_agents", {}) or {}
        return {
            "count": len(agents),
            "specialists": [
                {"name": n, "description": getattr(a, "description", "")}
                for n, a in agents.items()
            ],
        }

    print(f"\n  Ouroboros (multi-agent)  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI entry point ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Ouroboros — multi-agent CUGA lead generation",
    )
    parser.add_argument("--port", type=int, default=28822)
    parser.add_argument(
        "--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"],
    )
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    _web(args.port)


if __name__ == "__main__":
    main()
