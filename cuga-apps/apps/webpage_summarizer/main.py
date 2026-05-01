"""
Webpage Summarizer — CUGA Demo App

A FastAPI server that accepts a URL and uses CugaAgent to fetch and summarize
the contents of that webpage. Paste any URL into the chat and the agent will
retrieve the page, extract its text, and produce a concise summary.

Usage:
  python main.py [--port 28071] [--provider anthropic] [--model claude-sonnet-4-6]

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
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from langchain_core.tools import tool
from pydantic import BaseModel

from ui import _HTML

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def _make_tools():
    # Delegated to MCP server(s): web.
    from _mcp_bridge import load_tools
    return load_tools(["web"])


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a webpage summarizer assistant. Your job is to fetch and summarize the content
of web pages provided by the user.

When given a URL:
1. Call fetch_webpage to retrieve the page content.
2. Produce a well-structured summary that includes:
   - Page title and source URL
   - A 2–3 sentence overview of the page's main purpose
   - Key topics or sections covered (as bullet points)
   - Any important facts, data, or conclusions mentioned
   - A one-sentence bottom line: what the reader should take away

Keep summaries concise but informative. If the page is an article, focus on the argument
and evidence. If it is a product page, highlight features and pricing. If it is a news
story, capture who/what/when/where/why.

If the URL is unreachable or returns an error, report it clearly and ask the user for
a different URL.

Do not make up content — only summarise what is actually on the page.
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

    app = FastAPI(title="Webpage Summarizer", version="1.0.0")

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
        question: str

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.post("/ask")
    async def ask(req: AskRequest):
        thread_id = str(uuid.uuid4())
        try:
            agent = _get_agent()
            result = await agent.invoke(req.question, thread_id=thread_id)
            return {"answer": str(result)}
        except Exception as exc:
            log.exception("Agent invocation failed")
            return JSONResponse(status_code=500, content={"answer": f"Error: {exc}"})

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Webpage Summarizer — CUGA demo app")
    parser.add_argument("--port", type=int, default=28071)
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

    print(f"\n  Webpage Summarizer  →  http://127.0.0.1:{args.port}\n")
    _web(args.port)
