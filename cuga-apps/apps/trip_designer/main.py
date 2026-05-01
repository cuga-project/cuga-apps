"""
Trip Designer — itinerary planner with a goal-shaped prompt
===========================================================

Same domain as travel_planner, but deliberately written so the system prompt
stays out of the way. There's NO prescribed workflow ("first call X, then Y"),
NO prescribed sub-decomposition ("days × morning/afternoon/evening"), NO
prescribed tool order. The agent owns the plan.

The user gives:
  - A destination
  - Number of days
  - Travel month
  - Optional interests + travel style + hard constraints

The agent must:
  1. Propose a plan (decomposition + tool intentions). Free; recorded; UI shows.
  2. Use the available MCP tools (web · knowledge · geo) to gather facts.
  3. Replan if early calls reveal something the plan didn't anticipate.
  4. Produce an itinerary that respects the constraints.

Plan + tool calls stream to the UI over SSE so the planning is visible live.

Run:
    python main.py --port 28817

Environment variables:
    LLM_PROVIDER, LLM_MODEL, AGENT_SETTING_CONFIG
    TAVILY_API_KEY (optional — improves web_search)
    OPENTRIPMAP_API_KEY (optional — improves search_attractions)
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


# ── Session ──────────────────────────────────────────────────────────────

@dataclass
class TripSession:
    id: str
    request: dict
    plan_history: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    itinerary: str = ""
    status: str = "running"        # running | done | error
    error: str | None = None
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)


_sessions: dict[str, TripSession] = {}


def _short(value: Any, n: int = 200) -> Any:
    if isinstance(value, str) and len(value) > n:
        return value[:n] + "…"
    if isinstance(value, dict):
        return {k: _short(v, n) for k, v in value.items()}
    return value


# ── Tools (propose_plan + observed MCP tools) ────────────────────────────
# Each MCP tool gets wrapped with a thin shim that streams a tool_call event
# into the session queue (so the UI can show the agent's work live). No
# budget enforcement here — this app is about visibility, not constraints.

def _wrap_tool(orig, session: TripSession):
    from langchain_core.tools import StructuredTool

    name = orig.name
    description = orig.description
    args_schema = getattr(orig, "args_schema", None)

    async def _wrapped(**kwargs: Any) -> str:
        session.tool_calls.append({"tool": name, "args": kwargs})
        await session.queue.put({
            "type": "tool_call",
            "tool": name,
            "args": _short(kwargs),
            "count": len(session.tool_calls),
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
            await session.queue.put({
                "type": "tool_result",
                "tool": name,
                "preview": str(exc)[:240],
                "ok": False,
            })
            return json.dumps({"ok": False, "code": "tool_error", "error": str(exc)})

    return StructuredTool(
        name=name,
        description=description,
        args_schema=args_schema,
        coroutine=_wrapped,
    )


def _make_tools(session: TripSession) -> list:
    from langchain_core.tools import tool
    from _mcp_bridge import load_tools

    @tool
    async def propose_plan(plan: str) -> str:
        """Record your plan — your decomposition, what you'll research, what
        the resulting itinerary will look like. Call this BEFORE any other
        tool, and again whenever you want to revise. Free.

        Args:
            plan: Markdown describing your decomposition + research intent +
                  output shape. The user sees this verbatim.
        """
        session.plan_history.append({"plan": plan, "at_calls": len(session.tool_calls)})
        await session.queue.put({
            "type": "plan",
            "plan": plan,
            "version": len(session.plan_history),
            "at_calls": len(session.tool_calls),
        })
        if len(session.plan_history) > 6:
            return "WARNING: too many replans. Stop planning and produce the itinerary."
        return f"Plan v{len(session.plan_history)} recorded."

    base_tools = load_tools(["web", "knowledge", "geo"])
    return [propose_plan] + [_wrap_tool(t, session) for t in base_tools]


# ── System prompt — deliberately light + goal-shaped ─────────────────────
# What's NOT here: a numbered tool-call workflow, a fixed itinerary template,
# any opinion about what counts as a sub-task. The planner owns all of it.

_SYSTEM = """\
# Trip Designer

You design travel itineraries by gathering real information (weather,
geography, attractions, practicalities) with your tools and composing them
into a plan that respects the user's constraints.

You have:
- `propose_plan(plan)` — free; records your plan so the user can see it.
- A toolkit covering web search + page fetch, Wikipedia, geocoding,
  attractions search, weather, hiking, and YouTube.

How you work is up to you. Decide your decomposition (days, themes,
geography, whatever fits), the order of investigation, the tool mix per
sub-task, and the format of the final itinerary.

Two requirements:

1. **Call `propose_plan` first**, before any other tool. Outline what
   sub-tasks you'll work through and what the user can expect. Replan
   freely as you learn.

2. **Cite real sources** — every claim about a place, time, cost, or fact
   must reference something a tool returned. Never invent attractions,
   distances, prices, opening hours, or names.

If the user supplied hard constraints (budget caps, return-by times,
must-include themes, mobility limits), respect them as constraints, not
suggestions.

That's it. Start with `propose_plan`.
"""


# ── Agent ────────────────────────────────────────────────────────────────

def make_agent(session: TripSession):
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


def _format_request(req: dict) -> str:
    """Render the user's input into a single prompt message — without
    instructing the agent on how to handle it."""
    lines = []
    lines.append(f"Destination: {req.get('destination', '?')}")
    lines.append(f"Days: {req.get('days', '?')}")
    lines.append(f"Travel month: {req.get('travel_month', 'flexible')}")
    if req.get("origin_city"):
        lines.append(f"Origin: {req['origin_city']}")
    if req.get("interests"):
        lines.append(f"Interests: {', '.join(req['interests'])}")
    if req.get("travel_style"):
        lines.append(f"Travel style: {req['travel_style']}")
    if req.get("constraints"):
        lines.append(f"Hard constraints: {req['constraints']}")
    lines.append("")
    lines.append("Design the trip. Propose a plan first, then execute.")
    return "\n".join(lines)


async def _execute(session: TripSession) -> None:
    try:
        agent = make_agent(session)
        result = await agent.invoke(_format_request(session.request), thread_id=session.id)
        session.itinerary = result.answer or ""
        session.status = "done"
        await session.queue.put({"type": "itinerary", "itinerary": session.itinerary})
    except Exception as exc:
        log.exception("Agent execution failed")
        session.status = "error"
        session.error = str(exc)
        await session.queue.put({"type": "error", "error": str(exc)})
    finally:
        await session.queue.put({
            "type": "done",
            "status": session.status,
            "tool_call_count": len(session.tool_calls),
            "plan_count": len(session.plan_history),
        })


# ── Request models ───────────────────────────────────────────────────────

class RunReq(BaseModel):
    destination: str
    days: int = 5
    travel_month: str = ""
    origin_city: str = ""
    interests: list[str] = []
    travel_style: str = ""
    constraints: str = ""


# ── Web ──────────────────────────────────────────────────────────────────

def _web(port: int) -> None:
    import uvicorn
    from ui import _HTML

    app = FastAPI(title="Trip Designer", docs_url=None, redoc_url=None)
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
        if not req.destination.strip():
            return JSONResponse({"error": "destination is empty"}, status_code=400)

        sid = uuid.uuid4().hex[:8]
        session = TripSession(id=sid, request=req.model_dump())
        _sessions[sid] = session

        await session.queue.put({
            "type": "init",
            "session_id": sid,
            "request": session.request,
        })

        asyncio.create_task(_execute(session))
        return {"session_id": sid}

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
            "request": session.request,
            "plan_history": session.plan_history,
            "tool_calls": session.tool_calls,
            "itinerary": session.itinerary,
            "status": session.status,
            "error": session.error,
        }

    print(f"\n  Trip Designer  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Trip Designer — itinerary planner with a goal-shaped prompt")
    parser.add_argument("--port", type=int, default=28817)
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
