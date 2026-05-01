"""
Travel Itinerary Planner — CUGAAgent Demo App

A FastAPI server that exposes a conversational travel planning API, with two
interchangeable agent backends:

  - CUGAAgent  : enterprise-grade agent with policy system and graph-based reasoning
  - ReAct      : LangGraph prebuilt ReAct agent (tool-call loop)

Both agents receive the same tools and system instructions — making this a clean
side-by-side comparison of the two architectures on an identical task.

Data sources:
  - Wikipedia REST API     : city overviews (no key)
  - wttr.in                : live weather (no key)
  - Nominatim (OSM)        : geocoding (no key)
  - OpenTripMap            : attractions/POIs (free API key)
  - Tavily                 : web search (API key)

Usage:
  POST /plan      — generate a full itinerary
  POST /chat      — multi-turn follow-up
  POST /configure — initialise both agents (pass keys here)
  GET  /config/status
  GET  /health
"""

import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import SystemMessage
from pydantic import BaseModel

from cuga.sdk import CugaAgent
from llm import create_llm

# Make ../apps importable so _mcp_bridge resolves when launched from this dir.
_APPS_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_DIR))

load_dotenv(_APPS_DIR / ".env")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Travel Itinerary Planner",
    description="CUGAAgent vs LangGraph ReAct — same tools, two agents",
    version="1.0.0",
)

_static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_static), name="static")

_cuga_agent: Optional[CugaAgent] = None
_react_agent = None  # ReactAgentWrapper
_agent_lock = asyncio.Lock()

# ---------------------------------------------------------------------------
# Tools — loaded from three MCP servers at startup:
#   mcp-web       : web_search, fetch_webpage, fetch_webpage_links, ...
#   mcp-knowledge : get_wikipedia_article, search_wikipedia, arxiv/S2 ...
#   mcp-geo       : geocode, search_attractions, get_weather, find_hikes
# Populated by startup() below — must not be read at import time.
# ---------------------------------------------------------------------------

TOOLS: list = []

# ---------------------------------------------------------------------------
# System instructions (shared)
# ---------------------------------------------------------------------------

SYSTEM_INSTRUCTIONS = """\
You are an expert travel planner. When asked to create an itinerary, always follow
this research workflow before writing a single day of the plan:

1. Call get_wikipedia_article(title=<city>) to understand the destination.
2. Call get_weather(city, travel_month) to factor in climate.
3. Call geocode(place=<city>) to obtain lat/lon for the city.
4. Call search_attractions(lat, lon, category) at least twice with different
   categories relevant to the traveller's interests (e.g. historic + cultural,
   or natural + amusements).
5. Call web_search(query) for at least two practical queries:
   - visa / entry requirements for international travellers
   - local transport options and approximate costs
   - any notable events or festivals during the travel month
6. Only after gathering all the above, write the itinerary.

Itinerary format:
- Brief destination intro (2–3 sentences)
- Weather & packing tips for the travel month
- Day-by-day plan with morning / afternoon / evening slots
  — each activity should note approximate duration and any booking tips
- Practical section: getting there, getting around, estimated daily budget
  (broken down by accommodation / food / activities / transport)
- Top 3 insider tips

Be specific — use real attraction names from your tool results.
If the traveller specifies interests, weight the itinerary accordingly.
"""

# ---------------------------------------------------------------------------
# ReAct wrapper — same interface as CugaAgent
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    answer: str
    error: Optional[str] = None


class ReactAgentWrapper:
    """
    Thin wrapper around LangGraph's prebuilt ReAct agent that mirrors the
    CugaAgent.invoke(message, thread_id) interface.

    LangGraph's create_react_agent wires a tool-calling loop:
      LLM → tool calls → observations → ... → final answer
    Memory is handled by MemorySaver + thread_id in the run config.
    """

    def __init__(self, model, tools: list, system_instructions: str):
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.prebuilt import create_react_agent

        self._graph = create_react_agent(
            model=model,
            tools=tools,
            prompt=SystemMessage(content=system_instructions),
            checkpointer=MemorySaver(),
        )

    async def invoke(self, message: str, thread_id: str = "default") -> AgentResult:
        config = {"configurable": {"thread_id": thread_id}}
        try:
            result = await self._graph.ainvoke(
                {"messages": [("human", message)]},
                config=config,
            )
            answer = result["messages"][-1].content
            return AgentResult(answer=answer)
        except Exception as e:
            return AgentResult(answer="", error=str(e))

    async def aclose(self):
        pass  # MemorySaver needs no teardown


# ---------------------------------------------------------------------------
# Agent builders
# ---------------------------------------------------------------------------

async def _build_cuga_agent(llm) -> CugaAgent:
    # CUGAAgent validates OPENAI_API_KEY internally even when a custom model is
    # supplied. Set a placeholder so the check passes without routing to OpenAI.
    if not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "sk-placeholder-not-used"

    agent = CugaAgent(model=llm, tools=TOOLS, special_instructions=SYSTEM_INSTRUCTIONS)
    await agent.initialize()
    return agent


def _build_react_agent(llm) -> ReactAgentWrapper:
    return ReactAgentWrapper(model=llm, tools=TOOLS, system_instructions=SYSTEM_INSTRUCTIONS)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ConfigureRequest(BaseModel):
    rits_api_key: Optional[str] = None
    rits_model: str = "llama-3-3-70b-instruct"
    rits_base_url: Optional[str] = None
    tavily_api_key: Optional[str] = None
    opentripmap_api_key: Optional[str] = None


class PlanRequest(BaseModel):
    destination: str
    days: int = 5
    interests: list[str] = []
    travel_style: str = "mid-range"
    travel_month: str = "June"
    origin_city: Optional[str] = None
    agent_type: str = "cuga"   # "cuga" | "react"


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"
    agent_type: str = "cuga"   # "cuga" | "react"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_agent(agent_type: str):
    if agent_type == "react":
        if not _react_agent:
            raise HTTPException(status_code=503, detail="Agents not configured. Call POST /configure first.")
        return _react_agent
    else:
        if not _cuga_agent:
            raise HTTPException(status_code=503, detail="Agents not configured. Call POST /configure first.")
        return _cuga_agent


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    """Auto-configure agents from environment if credentials are already present.

    Tries providers in priority order so that whichever key is present in the
    environment (or .env file) is used automatically — no config modal needed.
    """
    global _cuga_agent, _react_agent, TOOLS

    # Fetch tool definitions from the three MCP servers we depend on.
    if not TOOLS:
        from _mcp_bridge import load_tools
        TOOLS = load_tools(["web", "knowledge", "geo"])

    # Build a candidate list: explicit LLM_PROVIDER first, then auto-detect by key presence
    explicit = os.environ.get("LLM_PROVIDER")
    candidates = [explicit] if explicit else []
    _auto_priority = [
        ("rits",      "RITS_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("openai",    "OPENAI_API_KEY"),
        ("watsonx",   "WATSONX_APIKEY"),
        ("litellm",   "LITELLM_API_KEY"),
    ]
    for provider, key_var in _auto_priority:
        if provider not in candidates and os.environ.get(key_var):
            candidates.append(provider)

    for provider in candidates:
        try:
            llm = create_llm(provider=provider)
        except Exception:
            continue
        try:
            _cuga_agent = await _build_cuga_agent(llm)
            _react_agent = _build_react_agent(llm)
            os.environ.setdefault("LLM_PROVIDER", provider)  # surface in /config/status
            return
        except Exception:
            _cuga_agent = None
            _react_agent = None


@app.on_event("shutdown")
async def shutdown():
    if _cuga_agent:
        await _cuga_agent.aclose()
    if _react_agent:
        await _react_agent.aclose()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/configure")
async def configure(req: ConfigureRequest):
    """
    Build both CUGAAgent and LangGraph ReAct agent from the same LLM instance
    and tool set. Both will be available immediately after this call.
    """
    global _cuga_agent, _react_agent
    async with _agent_lock:
        if req.tavily_api_key:
            os.environ["TAVILY_API_KEY"] = req.tavily_api_key
        if req.opentripmap_api_key:
            os.environ["OPENTRIPMAP_API_KEY"] = req.opentripmap_api_key

        if not req.rits_api_key:
            raise HTTPException(status_code=400, detail="rits_api_key is required.")

        try:
            llm = create_llm(
                provider="rits",
                model=req.rits_model,
                rits_api_key=req.rits_api_key,
                rits_base_url=req.rits_base_url,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"LLM init failed: {e}")

        # Tear down existing agents.
        if _cuga_agent:
            await _cuga_agent.aclose()

        try:
            _cuga_agent = await _build_cuga_agent(llm)
        except Exception as e:
            _cuga_agent = None
            raise HTTPException(status_code=500, detail=f"CUGAAgent init failed: {e}")

        _react_agent = _build_react_agent(llm)

    return {"status": "configured", "model": req.rits_model, "agents": ["cuga", "react"]}


@app.get("/config/prefill")
async def config_prefill():
    """Return current env var values so the UI can pre-populate the config form."""
    return {
        "llm_provider":        os.environ.get("LLM_PROVIDER", ""),
        "rits_api_key":        os.environ.get("RITS_API_KEY", ""),
        "rits_model":          os.environ.get("LLM_MODEL", "llama-3-3-70b-instruct"),
        "rits_base_url":       os.environ.get("RITS_BASE_URL", ""),
        "tavily_api_key":      os.environ.get("TAVILY_API_KEY", ""),
        "opentripmap_api_key": os.environ.get("OPENTRIPMAP_API_KEY", ""),
    }


@app.get("/config/status")
async def config_status():
    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    model = os.environ.get("LLM_MODEL", "")
    return {
        "configured": _cuga_agent is not None,
        "provider": provider,
        "model": model,
        "agents": {
            "cuga": _cuga_agent is not None,
            "react": _react_agent is not None,
        },
    }


@app.post("/plan")
async def plan_itinerary(request: PlanRequest):
    """Generate a travel itinerary using the selected agent."""
    agent = _get_agent(request.agent_type)

    interests_str = ", ".join(request.interests) if request.interests else "general sightseeing and local culture"
    origin_line = f"- Travelling from: {request.origin_city}\n" if request.origin_city else ""

    prompt = (
        f"Create a {request.days}-day travel itinerary for **{request.destination}**.\n\n"
        f"Traveller profile:\n"
        f"- Travel month: {request.travel_month}\n"
        f"- Interests: {interests_str}\n"
        f"- Travel style / budget: {request.travel_style}\n"
        f"{origin_line}"
        f"\nResearch the destination thoroughly using your tools, then write the full itinerary."
    )

    # Scope thread_id per agent so histories don't cross-pollinate.
    thread_id = f"{request.agent_type}-plan-{request.destination.lower().replace(' ', '-')}"
    result = await agent.invoke(prompt, thread_id=thread_id)

    if result.error:
        raise HTTPException(status_code=500, detail=result.error)

    return {
        "destination": request.destination,
        "days": request.days,
        "travel_month": request.travel_month,
        "agent_type": request.agent_type,
        "itinerary": result.answer,
    }


@app.post("/chat")
async def chat(request: ChatRequest):
    """Multi-turn follow-up. Use the same thread_id and agent_type as /plan."""
    agent = _get_agent(request.agent_type)
    result = await agent.invoke(request.message, thread_id=request.thread_id)
    if result.error:
        raise HTTPException(status_code=500, detail=result.error)
    return {"response": result.answer, "thread_id": request.thread_id, "agent_type": request.agent_type}


@app.get("/")
async def index():
    return FileResponse(_static / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 28090))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
