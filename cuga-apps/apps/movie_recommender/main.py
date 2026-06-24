"""
Movie Recommender — CUGA Demo App

A FastAPI server that collects user preferences (genres, example movies, favourite
actors / directors, mood) and uses CugaAgent to generate personalised watch-next
suggestions.  Movie details are looked up via the free Wikipedia REST API — no API
key required.

Usage:
  python main.py [--port 8072] [--provider anthropic] [--model claude-sonnet-4-6]

Required env vars:
  LLM_PROVIDER          — LLM backend: anthropic | openai | rits | watsonx | litellm | ollama
  LLM_MODEL             — Model name for the chosen provider
  AGENT_SETTING_CONFIG  — Path to the agent settings TOML file

Optional env vars (provider-specific):
  ANTHROPIC_API_KEY     — Required when LLM_PROVIDER=anthropic
  OPENAI_API_KEY        — Required when LLM_PROVIDER=openai
  RITS_API_KEY          — Required when LLM_PROVIDER=rits
"""

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap — must come before local imports
# ---------------------------------------------------------------------------
_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in [str(_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Third-party imports (after path bootstrap)
# ---------------------------------------------------------------------------
import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from langchain_core.tools import tool
from pydantic import BaseModel

from ui import _HTML

# ---------------------------------------------------------------------------
# Per-request panel store (stateless)
# ---------------------------------------------------------------------------
# This app is STATELESS: every request is a single, self-contained free-form
# message. The agent infers the user's whole taste profile from THAT message
# alone — nothing is remembered across turns. The store below only holds the
# *current* turn's extracted profile + recommendations so the side panel (which
# the browser polls via GET /session/<id>) can render them. It is reset at the
# start of every turn.
# ---------------------------------------------------------------------------
_sessions: dict = {}


def _get_session(thread_id: str) -> dict:
    if thread_id not in _sessions:
        _sessions[thread_id] = {
            "genres": [],
            "liked_movies": [],
            "disliked_movies": [],
            "favorite_actors": [],
            "favorite_directors": [],
            "moods": [],
            "recommendations": [],
        }
    return _sessions[thread_id]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def _make_tools():
    # Wikipedia lookup delegated to mcp-knowledge. The single inline tool below
    # records the agent's one-shot result (extracted profile + recommendations)
    # into this process's per-turn panel store.
    from _mcp_bridge import load_tools
    knowledge_tools = load_tools(["knowledge"])

    _PROFILE_KEYS = {
        "genres", "liked_movies", "disliked_movies",
        "favorite_actors", "favorite_directors", "moods",
    }

    @tool
    def save_movie_result(thread_id: str, profile_json: str,
                          recommendations_json: str) -> str:
        """
        Record the taste profile you extracted from the user's message AND your
        recommendations, in a single call, so the UI can display them.

        Call this exactly once, after you have read the user's message and chosen
        the films. Everything must be derived from the current message alone.

        Args:
            thread_id: The current session/thread ID (pass the one you received).
            profile_json: A JSON object capturing what the user told you, with any
                of these keys (each a list of strings; omit or leave empty if not
                mentioned): genres, liked_movies, disliked_movies, favorite_actors,
                favorite_directors, moods.
            recommendations_json: A JSON array where each element is an object with
                keys: title (str), year (str or int), genre (str), reason (str —
                one sentence why this matches the user's taste), rating (optional
                str, e.g. "8.5/10").
        """
        session = _get_session(thread_id)
        try:
            profile = json.loads(profile_json) if profile_json.strip() else {}
            if not isinstance(profile, dict):
                return "profile_json must be a JSON object."
        except json.JSONDecodeError as e:
            return f"Invalid profile_json: {e}"
        try:
            recs = json.loads(recommendations_json)
            if not isinstance(recs, list):
                return "recommendations_json must be a JSON array."
        except json.JSONDecodeError as e:
            return f"Invalid recommendations_json: {e}"

        for key in _PROFILE_KEYS:
            value = profile.get(key) or []
            if isinstance(value, str):
                value = [value]
            session[key] = [str(v) for v in value if str(v).strip()]
        session["recommendations"] = recs
        log.info("[%s] extracted profile + %d recommendations",
                 thread_id[:8], len(recs))
        return f"Saved profile and {len(recs)} recommendations."

    return [*knowledge_tools, save_movie_result]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a personalized movie recommendation assistant. You are STATELESS: the user
sends ONE free-form message describing their taste, and you must figure everything
out from that single message. You have NO memory of previous messages — never assume
anything the user did not say in the current message.

## How to respond to each message
1. Read the user's message and infer their taste profile from it. Pick out, where
   present: genres they enjoy, specific movies they liked, movies they disliked,
   favourite actors, favourite directors, and any mood / vibe they want tonight
   (e.g. "something uplifting", "edge-of-seat thriller"). It is fine if some of
   these are absent — work with whatever the message provides. If the message is
   sparse (e.g. just "recommend a thriller"), infer a reasonable profile from it.
2. Optionally call get_wikipedia_article(title=...) to verify details about films
   you plan to suggest.
3. Choose 5–8 films that best match the inferred profile, avoiding anything the
   user said they dislike.
4. Call save_movie_result(thread_id=..., profile_json=..., recommendations_json=...)
   exactly ONCE, where:
     - profile_json is what you extracted from THIS message, e.g.
       {"genres": ["sci-fi", "thriller"], "liked_movies": ["Inception"],
        "moods": ["uplifting"]}
     - recommendations_json is a JSON array:
       [{"title": "...", "year": "...", "genre": "...", "reason": "...", "rating": "..."}, ...]
   This step is REQUIRED and is the PRIMARY output — the panel on the right is what
   the user reads. You MUST call it before you reply, even if you only have partial
   results.
5. Then reply with a SHORT framing ONLY — 1–2 sentences pointing the user to the
   panel on the right. Do NOT repeat the full list of films or their descriptions
   in prose; the panel already shows every recommendation and the taste profile.

## Tone
Warm, knowledgeable, enthusiastic about film — like a friend who has seen everything.
Keep replies focused. Don't pad with unnecessary filler.

## Thread ID
You will receive the thread_id in every user message (format: "[thread:<UUID>]").
Always extract it and pass it unchanged to every tool call that requires thread_id.
"""


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def make_agent():
    from cuga.sdk import CugaAgent
    from _llm import create_llm

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
        # CUGA's policy DB is a global sqlite store shared by every app. Don't
        # auto-load it, or an output-formatter persisted by another app (e.g.
        # find_a_doctor's doctor board) bleeds in and the model emits that board
        # instead of this app's answer.
        auto_load_policies=False,
    )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

def _web(port: int):
    import uvicorn

    app = FastAPI(title="Movie Recommender", version="1.0.0")

    _agent = None

    def _get_agent():
        nonlocal _agent
        if _agent is None:
            log.info("Initialising CugaAgent…")
            _agent = make_agent()
            log.info("CugaAgent ready.")
        return _agent

    class AskRequest(BaseModel):
        question: str
        thread_id: str = ""

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.post("/ask")
    async def ask(req: AskRequest):
        from _usage import track_utterance; track_utterance(req.question)
        # Stateless: the panel id keys the data the UI polls, but we reset it
        # each turn and run the agent on a fresh memory thread, so nothing
        # carries over from the previous message.
        thread_id = req.thread_id or uuid.uuid4().hex
        _sessions.pop(thread_id, None)
        # Embed the panel id in the message so the agent passes it to its tool.
        augmented = f"[thread:{thread_id}] {req.question}"
        try:
            agent = _get_agent()
            result = await agent.invoke(augmented, thread_id=uuid.uuid4().hex)
            return {"answer": str(result), "thread_id": thread_id}
        except Exception as exc:
            log.exception("Agent invocation failed")
            return JSONResponse(
                status_code=500,
                content={"answer": f"Error: {exc}", "thread_id": thread_id},
            )

    @app.get("/session/{thread_id}")
    async def get_session(thread_id: str):
        """Return stored preferences and recommendations for a session."""
        return _get_session(thread_id)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # Public deployment: layered, in-memory rate limiting on POST.
    from _ratelimit import install_rate_limit
    install_rate_limit(app)
    from _usage import install_usage
    install_usage(app)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Movie Recommender — CUGA demo app")
    parser.add_argument("--port", type=int, default=28806)
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

    print(f"\n  Movie Recommender  →  http://127.0.0.1:{args.port}\n")
    _web(args.port)
