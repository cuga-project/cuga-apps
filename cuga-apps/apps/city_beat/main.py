"""
City Beat — CUGA Demo App
=========================

Type a city name. The agent assembles a one-screen briefing for it:

  - Geocoded location + display name        (mcp-geo.geocode)
  - Current weather + travel-month outlook  (mcp-geo.get_weather)
  - Top attractions nearby                  (mcp-geo.search_attractions)
  - Today's news headlines                  (mcp-web.web_search)
  - Encyclopedia background                 (mcp-knowledge.get_wikipedia_article)
  - Optional crypto market spotlight        (mcp-finance.get_crypto_price)

Plus per-session inline tools for narrowing focus, tracking visited
cities, and persisting the briefing card the right panel renders.

Run:
    python main.py
    python main.py --port 28821
    python main.py --provider anthropic

Then open: http://127.0.0.1:28821

Environment variables:
    LLM_PROVIDER          rits | anthropic | openai | watsonx | litellm | ollama
    LLM_MODEL             model name override
    AGENT_SETTING_CONFIG  CUGA settings TOML path (defaulted in make_agent)
    TAVILY_API_KEY        required for mcp-web.web_search (set on the MCP host)
    OPENTRIPMAP_API_KEY   required for mcp-geo.search_attractions (free 500/day)

MCP server endpoints — auto-resolved by _mcp_bridge based on context:
    Code Engine  → https://cuga-apps-mcp-<name>.<project>.<region>.codeengine.appdomain.cloud/mcp
    Docker       → http://mcp-<name>:<port>/mcp
    Bare host    → http://localhost:<port>/mcp

Set CUGA_TARGET=ce (or run on Code Engine) to force the public CE URLs.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
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


# ── Per-thread session store ────────────────────────────────────────────
_sessions: dict[str, dict] = {}


def _get_session(thread_id: str) -> dict:
    if thread_id not in _sessions:
        _sessions[thread_id] = {
            "current_city":   "",
            "focus_topics":   [],          # narrows news search
            "watchlist":      [],          # cities the user is tracking
            "crypto_spotlight": "",        # optional ticker for the market widget
            "briefing":       None,        # the structured card
            "history":        [],          # past briefings (capped)
        }
    return _sessions[thread_id]


def _append_unique(lst: list[str], value: str) -> None:
    if value and value.lower() not in [v.lower() for v in lst]:
        lst.append(value)


# ── Tools ────────────────────────────────────────────────────────────────
def _make_tools():
    """Compose MCP-loaded tools (geo, web, knowledge, finance) with inline
    @tool defs that mutate per-session state and persist the briefing.
    """
    from langchain_core.tools import tool
    from _mcp_bridge import load_tools

    # Pull in tools from four different MCP servers — each provides a
    # discrete capability. _mcp_bridge resolves the URLs based on whether
    # we're on Code Engine, in docker-compose, or on bare metal.
    mcp_tools = load_tools(["geo", "web", "knowledge", "finance"])

    # ── Inline session tools ────────────────────────────────────────────

    @tool
    def set_current_city(thread_id: str, city: str) -> str:
        """Save the city the user is asking about as the active focus.
        Call this whenever the user names a city.

        Args:
            thread_id: The current session/thread ID.
            city:      Plain English city name, e.g. "Lisbon", "Boulder, CO".
        """
        if not city:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "city is empty"})
        session = _get_session(thread_id)
        session["current_city"] = city.strip()
        _append_unique(session["watchlist"], city.strip())
        return json.dumps({"ok": True, "data": {
            "current_city": session["current_city"],
            "watchlist":    session["watchlist"],
        }})

    @tool
    def add_focus_topic(thread_id: str, topic: str) -> str:
        """Add a topic that should bias the news search for this session
        (e.g. "tech startups", "live music", "transit").

        Args:
            thread_id: The current session/thread ID.
            topic:     Short keyword phrase.
        """
        session = _get_session(thread_id)
        normalized = (topic or "").strip()
        if not normalized:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "topic is empty"})
        _append_unique(session["focus_topics"], normalized)
        return json.dumps({"ok": True, "data": {
            "focus_topics": session["focus_topics"],
        }})

    @tool
    def clear_focus_topics(thread_id: str) -> str:
        """Wipe the session's news-bias topics. Use when the user wants a
        broad, unfiltered briefing.

        Args:
            thread_id: The current session/thread ID.
        """
        session = _get_session(thread_id)
        session["focus_topics"] = []
        return json.dumps({"ok": True, "data": {"focus_topics": []}})

    @tool
    def set_crypto_spotlight(thread_id: str, ticker: str) -> str:
        """Save a crypto ticker (e.g. "btc", "eth") to spotlight on the
        briefing card. Pass an empty ticker to clear the spotlight.

        Args:
            thread_id: The current session/thread ID.
            ticker:    Common ticker or CoinGecko slug, or "" to clear.
        """
        session = _get_session(thread_id)
        session["crypto_spotlight"] = (ticker or "").strip().lower()
        return json.dumps({"ok": True, "data": {
            "crypto_spotlight": session["crypto_spotlight"],
        }})

    @tool
    def get_session_state(thread_id: str) -> str:
        """Read everything tracked for this session: current city, focus
        topics, watchlist, crypto spotlight. Call this at the start of a
        briefing request to recall context.

        Args:
            thread_id: The current session/thread ID.
        """
        session = _get_session(thread_id)
        return json.dumps({"ok": True, "data": {
            "current_city":     session["current_city"],
            "focus_topics":     session["focus_topics"],
            "watchlist":        session["watchlist"],
            "crypto_spotlight": session["crypto_spotlight"],
            "has_briefing":     session["briefing"] is not None,
        }})

    @tool
    def save_briefing(thread_id: str, briefing_json: str) -> str:
        """Persist the structured city briefing so the right-panel UI can
        render it. Call this at the END of every briefing turn, after you
        have collected weather + news + wiki + (optional) attractions and
        crypto.

        Args:
            thread_id:     The current session/thread ID.
            briefing_json: A JSON object with this shape:
                {
                  "city":            str,
                  "display_name":    str,
                  "lat":             float,
                  "lon":             float,
                  "weather": {
                      "current":     str,        # e.g. "Sunny, 22°C, light wind"
                      "outlook":     str         # 1–3 line outlook
                  },
                  "wiki": {
                      "title":       str,
                      "summary":     str,        # 2–4 sentences
                      "url":         str
                  },
                  "news": [                       # 3–6 items
                      {"title": str, "url": str, "snippet": str}
                  ],
                  "attractions": [                # OPTIONAL, 3–6 items
                      {"name": str, "category": str, "distance_m": int}
                  ],
                  "crypto":   null OR {"ticker": str, "price_usd": float, "change_24h_pct": float},
                  "tagline":  str                 # 1 punchy sentence
                }
        """
        session = _get_session(thread_id)
        try:
            briefing = json.loads(briefing_json)
            if not isinstance(briefing, dict):
                return json.dumps({"ok": False, "code": "bad_input",
                                   "error": "briefing_json must be a JSON object"})
            briefing["_at"] = datetime.now(timezone.utc).isoformat()
            session["briefing"] = briefing
            session["history"].insert(0, briefing)
            session["history"] = session["history"][:8]
            log.info("[%s] briefing saved for %s",
                     thread_id[:8], briefing.get("city", "?"))
            return json.dumps({"ok": True, "data": {"saved": True}})
        except json.JSONDecodeError as exc:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": f"invalid JSON: {exc}"})

    inline_tools = [
        set_current_city, add_focus_topic, clear_focus_topics,
        set_crypto_spotlight, get_session_state, save_briefing,
    ]

    return [*mcp_tools, *inline_tools]


# ── System prompt ────────────────────────────────────────────────────────
_SYSTEM = """\
# City Beat

You are a city-briefing concierge. The user names a city; you assemble a
single, glanceable briefing pulling from public web + knowledge + geo +
finance APIs through MCP tools, plus light inline session memory.

## On every new request

1. If the user named a city, call `set_current_city(thread_id=..., city=...)`.
2. Call `get_session_state(thread_id=...)` to recall prior focus topics
   and the optional crypto spotlight.
3. Call `geocode(place=<city>)` from mcp-geo to get lat/lon and the
   canonical display name. If geocoding fails, ask the user to clarify.

## Build the briefing
Call these in parallel-ish — the order doesn't matter, but each must run:

  - `get_weather(city=<city>, travel_month=<empty or what user mentioned>)` from mcp-geo.
  - `web_search(query=...)` from mcp-web. Build the query as
    "<city> news today" plus any focus topics joined with spaces. Cap
    `max_results` at 5.
  - `get_wikipedia_article(title=<city>)` from mcp-knowledge for the
    background blurb. If you get an empty result, try
    `search_wikipedia(query=<city>)` and pick the top hit.
  - OPTIONAL: `search_attractions(lat=..., lon=..., category="cultural", limit=6)`
    from mcp-geo — only if the user asked about things to do, or if the
    briefing would otherwise feel sparse.
  - OPTIONAL: if `crypto_spotlight` is non-empty, call
    `get_crypto_price(symbol=<ticker>)` from mcp-finance.

## Synthesize and persist
4. Build the briefing object (see `save_briefing` docstring for the exact
   shape). For each `news` item, copy `title`, `url`, and a 1–2 sentence
   `snippet` from the search result. For `wiki.summary`, pick the first
   2–4 sentences of the article extract — do not paraphrase.
5. Call `save_briefing(thread_id=..., briefing_json=...)`.
6. Reply to the user with a short prose summary that ends with the
   "tagline" from the briefing. Two short paragraphs maximum — the right
   panel shows the structured detail.

## Rules
- Cite news as markdown links in your prose. Wikipedia is just `[More on
  Wikipedia](url)`.
- Never make up news headlines, weather numbers, or coordinates. If a
  tool fails, say so plainly and skip that section in the briefing.
- The tagline is one sentence and reflects the *vibe* of the city today —
  not a generic platitude.

## Thread ID
You will receive the thread_id in every user message (format:
"[thread:<UUID>]"). Always extract it and pass it unchanged to every
inline tool that requires thread_id.
"""


# ── Agent factory ────────────────────────────────────────────────────────
def make_agent():
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
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ── Request models ──────────────────────────────────────────────────────
class AskReq(BaseModel):
    question: str
    thread_id: str = ""


# ── HTTP server ──────────────────────────────────────────────────────────
def _web(port: int) -> None:
    import uvicorn

    app = FastAPI(title="City Beat", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    _agent = None

    def _get_agent():
        nonlocal _agent
        if _agent is None:
            log.info("Initialising CugaAgent (mcp: geo, web, knowledge, finance)…")
            _agent = make_agent()
            log.info("CugaAgent ready.")
        return _agent

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.post("/ask")
    async def api_ask(req: AskReq):
        thread_id = req.thread_id or str(uuid.uuid4())
        augmented = f"[thread:{thread_id}] {req.question}"
        try:
            agent = _get_agent()
            result = await agent.invoke(augmented, thread_id=thread_id)
            return {"answer": str(result), "thread_id": thread_id}
        except Exception as exc:
            log.exception("Agent invocation failed")
            return JSONResponse(
                status_code=500,
                content={"answer": f"Error: {exc}", "thread_id": thread_id},
            )

    @app.get("/session/{thread_id}")
    async def api_session(thread_id: str):
        return _get_session(thread_id)

    @app.get("/health")
    async def health():
        return {"ok": True}

    print(f"\n  City Beat  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI entry point ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="City Beat — CUGA demo app")
    parser.add_argument("--port", type=int, default=28821)
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
