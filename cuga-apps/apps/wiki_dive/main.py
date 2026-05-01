"""
Wiki Dive — Deep Wikipedia Research powered by CugaAgent
=========================================================

Go beyond Wikipedia's search bar: the agent reads articles section by section,
follows "See also" links to pull related concepts, and synthesises a structured
report with citations and cross-article connections.

No API keys required — uses Wikipedia's free public REST and action APIs.

Run:
    python main.py
    python main.py --port 28809
    python main.py --provider anthropic

Then open: http://127.0.0.1:28809

Environment variables:
    LLM_PROVIDER         rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL            model override
    AGENT_SETTING_CONFIG path to the agent settings TOML file
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Path bootstrap
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
# Wikipedia API endpoints
# ---------------------------------------------------------------------------
_WIKI_REST   = "https://en.wikipedia.org/api/rest_v1"
_WIKI_ACTION = "https://en.wikipedia.org/w/api.php"

# Wikipedia requires a descriptive User-Agent or it returns 403.
_HEADERS = {
    "User-Agent": "WikiDive/1.0 (cuga-apps demo; https://github.com/IBM/cuga-apps) httpx/0.27",
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def _make_tools():
    # Delegated to MCP server(s): knowledge.
    from _mcp_bridge import load_tools
    return load_tools(["knowledge"])


def _strip_tags(text: str) -> str:
    """Remove HTML tags from a string."""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
# Wiki Dive — Deep Wikipedia Research Assistant

You help users understand complex topics by reading Wikipedia articles
thoroughly — not just the lead summary, but sections, cross-links, and
related articles.

You have four tools:
- `search_wikipedia`    — find relevant articles by keyword
- `get_article_summary` — read the lead/introduction of an article
- `get_article_sections`— read the full article section by section
- `get_related_articles`— discover related pages to broaden coverage

## Process

### For topic research
1. Call `search_wikipedia` to identify the most relevant article(s).
2. Call `get_article_summary` on the top 1-2 results to confirm relevance.
3. Call `get_article_sections` on the primary article for deep content.
4. Call `get_related_articles` to discover connected concepts.
5. Call `get_article_summary` on 2-3 related articles that add meaningful
   context (e.g. predecessor concepts, competing theories, key figures).
6. Synthesise across all articles.

### For a specific article title
Go directly to `get_article_sections` — skip the search step.

## Citation format

Every claim from Wikipedia MUST cite the source article:

  According to **[Article Title](url)**: "key fact or close paraphrase"

When multiple articles confirm a point:
  "Both **[Transformer (deep learning)](url)** and **[Attention mechanism (machine learning)](url)**
   describe self-attention as …"

## Output structure

**Topic**: <the topic>

**Articles read**
- [Title](url) — one-line description of what it covers

**Overview** (2-3 paragraphs)
Plain-language synthesis of what Wikipedia says. No jargon without explanation.
Cite inline using the format above.

**Key concepts** (bullet list)
Each concept explained in 1-2 sentences with the source article cited.

**History / development** (if relevant)
Chronological narrative with citations.

**Current state / applications** (if relevant)
What is this used for today? Where is it going?

**Points of debate or nuance** (if any)
Where does Wikipedia note contested views, ongoing research, or limitations?

**Related topics to explore**
3-5 linked concepts with one-line descriptions and Wikipedia URLs.

## Rules

- Never fabricate facts. Report only what the tool results contain.
- If an article does not exist or is a disambiguation page, try a refined title.
- If Wikipedia coverage on a topic is sparse, say so and explain the gap.
- Keep the synthesis under 800 words unless the user asks for more depth.
- Prefer encyclopedic, neutral tone — match Wikipedia's style.
- Do not summarise the lead section alone and call it a deep dive. You must
  call `get_article_sections` on at least the primary article.
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
# Request models
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class AskReq(BaseModel):
    question: str
    thread_id: str = "default"


# ---------------------------------------------------------------------------
# Web server
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse

    from ui import _HTML

    app = FastAPI(title="Wiki Dive", docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"],
        allow_methods=["*"], allow_headers=["*"],
    )

    _agent = make_agent()

    @app.post("/ask")
    async def api_ask(req: AskReq):
        question = req.question.strip()
        if not question:
            return JSONResponse({"error": "Empty question"}, status_code=400)
        try:
            result = await _agent.invoke(question, thread_id=req.thread_id)
            return {"answer": result.answer}
        except Exception as exc:
            log.error("Agent error: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/", response_class=HTMLResponse)
    async def ui():
        return HTMLResponse(_HTML)

    print(f"\n  Wiki Dive  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Wiki Dive — Deep Wikipedia Research Agent")
    parser.add_argument("--port", type=int, default=28809)
    parser.add_argument("--provider", "-p", default=None,
                        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    _web(args.port)


if __name__ == "__main__":
    main()
