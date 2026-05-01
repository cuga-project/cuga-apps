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
# In-memory session store
# thread_id → {genres, liked_movies, disliked_movies, actors, directors, moods, recommendations}
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


def _append_unique(lst: list, value: str) -> None:
    """Append value to list only if not already present (case-insensitive)."""
    if value and value.lower() not in [v.lower() for v in lst]:
        lst.append(value)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def _make_tools():
    # Wikipedia lookup delegated to mcp-knowledge. The 3 session-state tools
    # below (save_preference, get_preferences, save_recommendations) stay inline
    # because they mutate this process's in-memory session store.
    from _mcp_bridge import load_tools
    knowledge_tools = load_tools(["knowledge"])

    @tool
    def save_preference(thread_id: str, category: str, value: str) -> str:
        """
        Save a user preference to their session profile.
        Call this whenever the user mentions something they like, dislike, or prefer.

        Args:
            thread_id: The current session/thread ID (always pass the thread_id you received)
            category: One of: genre, liked_movie, disliked_movie, favorite_actor,
                      favorite_director, mood
            value: The preference value (e.g. "thriller", "The Dark Knight", "Christopher Nolan")
        """
        session = _get_session(thread_id)
        category_map = {
            "genre": "genres",
            "liked_movie": "liked_movies",
            "disliked_movie": "disliked_movies",
            "favorite_actor": "favorite_actors",
            "favorite_director": "favorite_directors",
            "mood": "moods",
        }
        key = category_map.get(category.lower().replace(" ", "_"))
        if not key:
            return f"Unknown category '{category}'. Valid: genre, liked_movie, disliked_movie, favorite_actor, favorite_director, mood"

        _append_unique(session[key], value)
        log.info("Saved preference [%s] %s → %s", thread_id[:8], category, value)
        return f"Saved: {category} = {value}"

    @tool
    def get_preferences(thread_id: str) -> str:
        """
        Retrieve all saved preferences for the current session.
        Call this at the start of a recommendation request to recall what the user has told you.

        Args:
            thread_id: The current session/thread ID
        """
        session = _get_session(thread_id)
        parts = []
        if session["genres"]:
            parts.append("Genres: " + ", ".join(session["genres"]))
        if session["liked_movies"]:
            parts.append("Liked movies: " + ", ".join(session["liked_movies"]))
        if session["disliked_movies"]:
            parts.append("Disliked movies: " + ", ".join(session["disliked_movies"]))
        if session["favorite_actors"]:
            parts.append("Favourite actors: " + ", ".join(session["favorite_actors"]))
        if session["favorite_directors"]:
            parts.append("Favourite directors: " + ", ".join(session["favorite_directors"]))
        if session["moods"]:
            parts.append("Mood / vibe: " + ", ".join(session["moods"]))
        if not parts:
            return "No preferences saved yet for this session."
        return "\n".join(parts)

    @tool
    def save_recommendations(thread_id: str, recommendations_json: str) -> str:
        """
        Persist the structured list of recommendations so the UI can display them as cards.
        Call this EVERY time you produce a set of recommendations.

        Args:
            thread_id: The current session/thread ID
            recommendations_json: A JSON array where each element is an object with keys:
              title (str), year (str or int), genre (str), reason (str — one sentence why
              this matches the user's taste), rating (optional str, e.g. "8.5/10")
        """
        session = _get_session(thread_id)
        try:
            recs = json.loads(recommendations_json)
            if not isinstance(recs, list):
                return "recommendations_json must be a JSON array."
            session["recommendations"] = recs
            log.info("Saved %d recommendations for session %s", len(recs), thread_id[:8])
            return f"Saved {len(recs)} recommendations."
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"

    return [*knowledge_tools, save_preference, get_preferences, save_recommendations]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a personalized movie recommendation assistant. Your goal is to learn what
the user enjoys and suggest films they will love.

## Collecting preferences
Whenever the user mentions:
- a movie they like or have enjoyed → call save_preference(category="liked_movie", ...)
- a genre they enjoy → call save_preference(category="genre", ...)
- a movie they disliked → call save_preference(category="disliked_movie", ...)
- a favourite actor → call save_preference(category="favorite_actor", ...)
- a favourite director → call save_preference(category="favorite_director", ...)
- a mood or vibe (e.g. "something uplifting", "edge-of-seat thriller") → save_preference(category="mood", ...)

Save preferences immediately as the user mentions them — do not wait until they ask
for recommendations.

## Making recommendations
When the user asks for recommendations (or when you judge it's time):
1. Call get_preferences(thread_id=...) to recall everything you know.
2. Optionally call get_wikipedia_article(title=...) to verify details about movies you plan to suggest.
3. Select 5–8 films that best match the profile.
4. Call save_recommendations(thread_id=..., recommendations_json=...) with a JSON array:
   [{"title": "...", "year": "...", "genre": "...", "reason": "...", "rating": "..."}, ...]
5. Then write a friendly, conversational reply listing those same films with short
   descriptions of why each fits the user's taste.

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
        thread_id = req.thread_id or str(uuid.uuid4())
        # Embed thread_id in the message so the agent can pass it to tools
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
    async def get_session(thread_id: str):
        """Return stored preferences and recommendations for a session."""
        return _get_session(thread_id)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

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
