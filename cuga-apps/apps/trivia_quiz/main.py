"""
Trivia Quiz Maker — CUGA Demo App

A FastAPI server that uses CugaAgent to build a 5-question multiple-choice quiz
from a Wikipedia article. Name any topic and get questions plus an answer key.

Usage:
  python main.py [--port 28831] [--provider anthropic] [--model claude-sonnet-4-6]

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
import logging
import os
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap — must come before local imports
# ---------------------------------------------------------------------------
_DIR = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in [str(_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Robustness: AGENT_SETTING_CONFIG may arrive as an in-IMAGE absolute path
# (e.g. /app/apps/settings.watsonx.toml from build/.env) while running from a
# local checkout where it doesn't exist. CUGA aborts on a missing config file,
# so remap a non-existent absolute config to a local file of the same name.
_asc = os.environ.get("AGENT_SETTING_CONFIG", "")
if os.path.isabs(_asc) and not os.path.isfile(_asc):
    for _cand in (_DIR / os.path.basename(_asc), _DEMOS_DIR / os.path.basename(_asc)):
        if _cand.is_file():
            os.environ["AGENT_SETTING_CONFIG"] = str(_cand)
            break

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
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator
from ui import _HTML

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _make_tools():
    # Delegated to MCP server(s): knowledge.
    from _mcp_bridge import load_tools

    return load_tools(["knowledge"])


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You write fair, fun multiple-choice quizzes grounded in Wikipedia.

For every topic:
1. Find it with search_wikipedia, then read get_article_summary and, for more detail, get_article_sections.
2. Write exactly 5 questions. Each has 4 options (A–D) with exactly one correct answer, and the wrong options must be plausible.
3. Match the difficulty the user asks for (default: medium). Mix question types: who, what, when, why.
4. After the questions, add an **Answer key**: the letter plus one sentence explaining why, based on the article.
5. End with the source article title and URL.
Only ask about facts that are stated in the article you read. Never make up dates or numbers.
"""


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def make_agent():
    from _llm import create_llm
    from cuga.sdk import CugaAgent

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
        # Each question is independent — disable the persistent knowledge store
        # and on-disk policy auto-load so nothing carries across questions via
        # the shared .cuga folder.
        enable_knowledge=False,
        auto_load_policies=False,
    )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


def _web(port: int):
    import uvicorn

    app = FastAPI(title="Trivia Quiz Maker", version="1.0.0")

    # Lazy-initialise the agent on first request so startup is instant
    _agent = None

    def _get_agent():
        nonlocal _agent
        if _agent is None:
            log.info("Initialising CugaAgent…")
            _agent = make_agent()
            log.info("CugaAgent ready.")
        return _agent

    class AskRequest(BaseModel):
        # Upper bound keeps a single request from pushing a huge prompt through
        # the agent; 2000 chars is plenty for any quiz topic + difficulty hint.
        question: str = Field(
            ...,
            min_length=1,
            max_length=2000,
            description="Quiz topic or request",
        )

        @field_validator("question")
        @classmethod
        def _question_not_blank(cls, v: str) -> str:
            if not v.strip():
                raise ValueError("question must not be empty or whitespace-only")
            return v

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.exception_handler(RequestValidationError)
    async def validation_failed(_req, exc):
        # Family convention: answered JSON bodies {"answer": …} so the UI can
        # show a friendly message instead of bare status text.
        log.info("Rejected /ask request: %s", exc.errors()[:1])
        return JSONResponse(
            status_code=422,
            content={
                "answer": "Please keep your question between 1 and 2000 "
                "characters (and not just whitespace)."
            },
        )

    @app.post("/ask")
    async def ask(req: AskRequest):
        from _usage import track_utterance

        track_utterance(req.question)
        thread_id = str(uuid.uuid4())
        try:
            agent = _get_agent()
            result = await agent.invoke(req.question, thread_id=thread_id)
            # Return the agent's synthesised answer only. `getattr(result, "answer")`
            # never falls back to str(result): the result object's repr dumps the
            # CUGA plan + generated Python code, which must not reach the client.
            answer = getattr(result, "answer", None) or "The agent returned no answer."
            return {"answer": answer}
        except Exception:
            log.exception("Agent invocation failed")
            # Keep the detailed exception in the server log only; do not leak
            # internals (stack fragments, paths, provider errors) to clients.
            # No "Error:" prefix here — the UI adds one.
            return JSONResponse(
                status_code=500,
                content={"answer": "Quiz generation failed. Please try again."},
            )

    @app.get("/health")
    async def health():
        return {"ok": True}

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
    parser = argparse.ArgumentParser(description="Trivia Quiz Maker — CUGA demo app")
    parser.add_argument("--port", type=int, default=28831)
    parser.add_argument(
        "--provider",
        "-p",
        default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"],
    )
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    print(f"\n  Trivia Quiz Maker  →  http://127.0.0.1:{args.port}\n")
    _web(args.port)
