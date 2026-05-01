"""
Brief Budget — Research brief on a hard tool-call budget
========================================================

A planner-driven demo. The user gives a research question + a tool-call budget;
the agent must:
  1. Decide a decomposition (sub-topics, budget split, tool plan).
  2. Execute against the plan, decrementing budget per tool call.
  3. Replan if observations diverge from the plan.
  4. Synthesize a brief that cites only what was retrieved.

The system prompt is goal-shaped, NOT procedural: it does not prescribe
sub-topics or tool order. Decomposition is the agent's job.

Plan + tool-call events stream to the UI over SSE, so the planner's work is
visible live.

Run:
    python main.py --port 28816

Environment variables:
    LLM_PROVIDER, LLM_MODEL, AGENT_SETTING_CONFIG, TAVILY_API_KEY (optional)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

# ── Path bootstrap ───────────────────────────────────────────────────────
_DIR       = Path(__file__).parent
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


# ── Session state ────────────────────────────────────────────────────────
# One BriefSession per /api/run request. Holds the budget counter, plan
# history, tool-call log, queue for SSE events, and the final brief.

@dataclass
class BriefSession:
    id: str
    question: str
    budget: int
    used: int = 0
    plan_history: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    brief: str = ""
    status: str = "running"      # running | done | error
    error: str | None = None
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)


_sessions: dict[str, BriefSession] = {}


def _short(value: Any, n: int = 200) -> Any:
    """Truncate long strings so SSE payloads stay compact."""
    if isinstance(value, str) and len(value) > n:
        return value[:n] + "…"
    if isinstance(value, dict):
        return {k: _short(v, n) for k, v in value.items()}
    return value


# ── Tools ────────────────────────────────────────────────────────────────
# Two pieces:
#   1. propose_plan: free, LLM-emitted plan text. Stored on session, streamed.
#   2. Each MCP-loaded tool wrapped with a budget-aware shim that decrements
#      session.used and emits SSE events. Wrapping preserves the original
#      args_schema so the LLM still sees the right tool signatures.

def _wrap_tool_with_budget(orig, session: BriefSession):
    """Return a StructuredTool that mirrors `orig` but decrements budget +
    streams events into session.queue. Returns a budget_exhausted envelope
    once session.used >= session.budget."""
    from langchain_core.tools import StructuredTool

    name = orig.name
    description = orig.description
    args_schema = getattr(orig, "args_schema", None)

    async def _wrapped(**kwargs: Any) -> str:
        if session.used >= session.budget:
            await session.queue.put({
                "type": "budget_exhausted",
                "tool": name,
                "used": session.used,
                "budget": session.budget,
            })
            return json.dumps({
                "ok": False,
                "code": "budget_exhausted",
                "error": f"Budget exhausted: {session.used} of {session.budget} calls used. Stop calling tools and synthesize from what you have.",
            })

        session.used += 1
        remaining = session.budget - session.used
        session.tool_calls.append({"tool": name, "args": kwargs, "at": session.used})
        await session.queue.put({
            "type": "tool_call",
            "tool": name,
            "args": _short(kwargs),
            "used": session.used,
            "remaining": remaining,
        })

        try:
            result = await orig.ainvoke(kwargs)
            await session.queue.put({
                "type": "tool_result",
                "tool": name,
                "preview": _short(result if isinstance(result, str) else str(result), 240),
                "ok": True,
            })
            return result
        except Exception as exc:
            log.exception("Tool %s raised", name)
            err_envelope = json.dumps({
                "ok": False,
                "code": "tool_error",
                "error": str(exc),
            })
            await session.queue.put({
                "type": "tool_result",
                "tool": name,
                "preview": str(exc)[:240],
                "ok": False,
            })
            return err_envelope

    return StructuredTool(
        name=name,
        description=description,
        args_schema=args_schema,
        coroutine=_wrapped,
    )


def _make_tools(session: BriefSession) -> list:
    """Build the tool list for this session: propose_plan + budget-wrapped MCP tools."""
    from langchain_core.tools import tool
    from _mcp_bridge import load_tools

    @tool
    async def propose_plan(plan: str) -> str:
        """Propose or revise your research plan. Call this BEFORE any tool, and
        again whenever you want to change direction. Does NOT count against
        your tool-call budget.

        Args:
            plan: A markdown description of your decomposition. List 2–5 sub-topics,
                  the budget you allocate to each, the tools you'll lean on per
                  sub-topic, and your rationale. The user will see this verbatim.
        """
        session.plan_history.append({
            "plan": plan,
            "at_used": session.used,
            "at_remaining": session.budget - session.used,
        })
        await session.queue.put({
            "type": "plan",
            "plan": plan,
            "version": len(session.plan_history),
            "used": session.used,
            "remaining": session.budget - session.used,
        })
        if len(session.plan_history) > 6:
            return "WARNING: you have replanned too many times. Stop planning and execute or synthesize."
        return (
            f"Plan recorded (v{len(session.plan_history)}). "
            f"{session.budget - session.used} of {session.budget} calls remain. "
            "Now use your tools to gather material, then synthesize the brief."
        )

    base_tools = load_tools(["web", "knowledge"])
    wrapped = [propose_plan] + [_wrap_tool_with_budget(t, session) for t in base_tools]
    return wrapped


# ── System prompt — goal-shaped, NOT procedural ──────────────────────────
# Notes:
# - No prescribed sub-topics (the agent decomposes per question).
# - No prescribed tool order (the agent decides per sub-topic).
# - Hard rules: cite real URLs, never fabricate, stop on budget exhaustion.

_SYSTEM = """\
# Brief Budget — research analyst with a hard tool-call budget

You produce a structured literature brief on a research question, drawing on
real sources retrieved with your tools, while staying under a fixed tool-call
budget.

## Available tools

- `propose_plan(plan)` — record your plan. Free. Does NOT cost budget.
- Academic: `search_arxiv`, `get_arxiv_paper`, `search_semantic_scholar`,
  `get_paper_references`.
- Encyclopedic: `search_wikipedia`, `get_wikipedia_article`,
  `get_article_summary`, `get_article_sections`, `get_related_articles`.
- General web: `web_search`, `fetch_webpage`, `fetch_webpage_links`.
- Feeds & video: `fetch_feed`, `search_feeds`, `get_youtube_video_info`,
  `get_youtube_transcript`.

Every non-plan tool call decrements your budget by 1. When budget = 0, every
further tool call returns `{ok: false, code: "budget_exhausted"}` — at that
point you MUST stop calling tools and synthesize from what you already have.

## What you do — and own

You decide:

- **Decomposition** — break the question into 2–5 sub-topics. Don't follow a
  template; choose based on what the question actually asks.
- **Budget allocation** — split the budget across sub-topics. Lop-sided is
  fine if one sub-topic is denser.
- **Tool mix per sub-topic** — pick the tools that match each sub-topic
  (academic vs encyclopedic vs web). Different sub-topics need different mixes.
- **When to replan** — if a sub-topic returns nothing useful or you find
  unexpected structure, call `propose_plan` again to revise.

## Process — required order

1. **Propose plan first** — call `propose_plan(plan="…")` with a markdown
   plan that lists sub-topics, budget split, and intended tools per sub-topic.
   No tool calls before the plan is recorded.
2. **Execute** — work through your plan calling the tools. Each call
   decrements budget. Read the responses. Decide each next call from what
   you've seen.
3. **Replan when warranted** — call `propose_plan` again if you change
   direction. Replans are free but max ~3 replans is sensible.
4. **Synthesize** — when you have enough material, or budget is at most 2
   calls left, write the brief.

## Brief format

```
**[Question restated in one sentence]**

[1–2 sentence overall finding]

### [Sub-topic 1 title]
- Bullet 1, with citation [Title](url) — claim.
- Bullet 2, with citation.
- ...

### [Sub-topic 2 title]
- ...

### Sources
- [Title](url) — what it contributed
- ...

Budget: X of Y calls used.
```

## Hard rules

- NEVER fabricate sources, URLs, citation counts, dates, or numbers. Cite
  only what tools returned.
- If `budget_exhausted` shows up, STOP calling tools and synthesize.
- Don't repeat the same query if it returned nothing — pivot, don't retry.
- The plan is yours to design. There is no template.
"""


# ── Agent factory (per session) ──────────────────────────────────────────

def make_agent(session: BriefSession):
    from cuga.sdk import CugaAgent
    from _llm import create_llm

    _provider_toml = {
        "rits":      "settings.rits.toml",
        "watsonx":   "settings.watsonx.toml",
        "openai":    "settings.openai.toml",
        "anthropic": "settings.openai.toml",
        "litellm":   "settings.litellm.toml",
        "ollama":    "settings.openai.toml",
    }
    provider = (os.getenv("LLM_PROVIDER") or "").lower()
    os.environ.setdefault(
        "AGENT_SETTING_CONFIG",
        _provider_toml.get(provider, "settings.rits.toml"),
    )

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(session),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ── Background runner — agent.invoke + final brief event ─────────────────

async def _execute(session: BriefSession) -> None:
    user_msg = (
        f"Research question: {session.question}\n\n"
        f"Budget: {session.budget} tool calls.\n\n"
        "Propose a plan first (call propose_plan), execute it, replan if needed, "
        "then write the brief in the required format."
    )
    try:
        agent = make_agent(session)
        result = await agent.invoke(user_msg, thread_id=session.id)
        session.brief = result.answer or ""
        session.status = "done"
        await session.queue.put({
            "type": "brief",
            "brief": session.brief,
        })
    except Exception as exc:
        log.exception("Agent execution failed")
        session.status = "error"
        session.error = str(exc)
        await session.queue.put({"type": "error", "error": str(exc)})
    finally:
        await session.queue.put({
            "type": "done",
            "status": session.status,
            "used": session.used,
            "budget": session.budget,
            "plan_count": len(session.plan_history),
            "tool_call_count": len(session.tool_calls),
        })


# ── Request models ───────────────────────────────────────────────────────

class RunReq(BaseModel):
    question: str
    budget: int = 20


# ── Web app ──────────────────────────────────────────────────────────────

def _web(port: int) -> None:
    import uvicorn

    from ui import _HTML

    app = FastAPI(title="Brief Budget", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/api/run")
    async def api_run(req: RunReq):
        question = req.question.strip()
        if not question:
            return JSONResponse({"error": "question is empty"}, status_code=400)
        budget = max(1, min(int(req.budget), 100))

        sid = uuid.uuid4().hex[:8]
        session = BriefSession(id=sid, question=question, budget=budget)
        _sessions[sid] = session

        await session.queue.put({
            "type": "init",
            "session_id": sid,
            "question": question,
            "budget": budget,
        })

        asyncio.create_task(_execute(session))
        return {"session_id": sid, "budget": budget}

    @app.get("/api/stream/{sid}")
    async def api_stream(sid: str):
        session = _sessions.get(sid)
        if session is None:
            return JSONResponse({"error": "session not found"}, status_code=404)

        async def event_stream():
            while True:
                try:
                    event = await asyncio.wait_for(session.queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") == "done":
                    break

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/api/result/{sid}")
    async def api_result(sid: str):
        session = _sessions.get(sid)
        if session is None:
            return JSONResponse({"error": "session not found"}, status_code=404)
        return {
            "session_id": sid,
            "question": session.question,
            "budget": session.budget,
            "used": session.used,
            "status": session.status,
            "error": session.error,
            "plan_history": session.plan_history,
            "tool_calls": session.tool_calls,
            "brief": session.brief,
        }

    print(f"\n  Brief Budget  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Brief Budget — research brief on a hard budget")
    parser.add_argument("--port", type=int, default=28816)
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
