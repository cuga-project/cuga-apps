"""
Paper Scout — Academic Paper Research via arXiv + Semantic Scholar
==================================================================

Research any scientific topic: the agent searches arXiv and Semantic Scholar,
fetches paper abstracts and metadata, and synthesises findings with citations.
Paste an arXiv ID directly for instant paper summaries.

No API keys required — both arXiv and Semantic Scholar offer free public APIs.

Run:
    python main.py
    python main.py --port 28808
    python main.py --provider anthropic

Then open: http://127.0.0.1:28808

Environment variables:
    LLM_PROVIDER         rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL            model override
    AGENT_SETTING_CONFIG path to the agent settings TOML file
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

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
# Tools — delegated to the mcp-knowledge MCP server.
# The server exposes: search_arxiv, get_arxiv_paper, search_semantic_scholar,
# get_paper_references (all identical signatures to the former inline tools).
# ---------------------------------------------------------------------------

def _make_tools():
    from _mcp_bridge import load_tools
    return load_tools(["knowledge"])


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
# Paper Scout — Academic Research Assistant

You help users discover and understand research papers using two sources:
- **arXiv** — preprints in CS, ML, physics, math, biology, economics
- **Semantic Scholar** — broader coverage, citation counts, cross-disciplinary

You have four tools: `search_arxiv`, `get_arxiv_paper`, `search_semantic_scholar`,
and `get_paper_references`.

## Modes of operation

### Mode 1 — Topic research (no arXiv IDs in the user message)
The user gives a topic. Your job: find the most relevant and impactful papers.

Process:
1. Call `search_arxiv` with a focused query. Try 1-2 query variations if needed
   (e.g. different terminology). Use category filters for precision (cs.AI, cs.LG,
   stat.ML, q-bio, econ.EM, etc.).
2. Call `search_semantic_scholar` with a complementary query. This catches
   highly-cited older papers arXiv may not rank well.
3. Synthesise across all results. Do NOT simply list papers — group by theme,
   compare approaches, highlight agreements and tensions.

### Mode 2 — Direct arXiv ID or URL (user pastes an arXiv link or ID)
Call `get_arxiv_paper` immediately. Do NOT call `search_arxiv`. Summarise the
paper and offer to fetch its references via `get_paper_references`.

### Mode 3 — Foundational / citation questions
When the user asks "what does this build on?" or "what are the key prior works?",
call `get_paper_references` using the Semantic Scholar paper_id or arXiv ID.

## Citation format — CRITICAL

Every paper mentioned MUST be cited:
  [Title](url) by Author et al. (year) — N citations

When comparing papers:
  "Both [Attention Is All You Need](url) and [BERT](url) introduce self-attention
   but differ in …"

## Output structure for topic research

**Topic**: <topic>

**Papers found** (list with citation counts and year)
- [Title](url) — Author et al. (year) — N citations — source: arXiv/S2

**Synthesis**
Organise by theme, not by paper. Cite inline using the format above.
Cover: what the mainstream approach is, what open problems remain,
where different groups disagree.

**Key papers to read first** (top 3, ranked by impact + recency)

**Suggested follow-up queries**

## Output structure for direct paper summary

**Paper**: [Title](url)
**Authors**: …  **Year**: …  **arXiv**: …

**Summary** (4-6 bullet points of core contributions)

**Method** (what technique/approach, in plain language)

**Key results** (what did they show / prove / measure?)

**Limitations** (what did the authors acknowledge as gaps?)

**Related work** — offer to fetch references

## Rules

- Never fabricate citation counts, paper titles, or authors. Only report
  what the tools return.
- If a search returns no results, try a rephrased query before giving up.
- Keep topic syntheses under 700 words unless the user asks for more.
- Prefer recent papers (last 2 years) unless the user asks for foundational work.
- When Semantic Scholar and arXiv return the same paper, deduplicate — cite once.
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

    app = FastAPI(title="Paper Scout", docs_url=None, redoc_url=None)
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

    print(f"\n  Paper Scout  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Paper Scout — Academic Research Agent")
    parser.add_argument("--port", type=int, default=28808)
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
