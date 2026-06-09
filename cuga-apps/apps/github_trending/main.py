"""
GitHub Trending — CUGA Demo App
===============================

Ask for what's trending on GitHub — overall or by language/topic — and the
agent returns a ranked board of repositories, each with a plain-English
summary of what the project actually offers (what it's for, who it's for,
and why it's getting attention right now).

All tools are inline @tool defs. The live data comes from GitHub's public
REST API via direct httpx calls — no MCP servers. Unauthenticated works
(rate-limited); set GITHUB_TOKEN to raise the limits.

Run:
    python main.py
    python main.py --port 28823
    python main.py --provider anthropic

Then open: http://127.0.0.1:28823

Environment variables:
    LLM_PROVIDER          rits | anthropic | openai | watsonx | litellm | ollama
    LLM_MODEL             model name override
    AGENT_SETTING_CONFIG  path to CUGA settings TOML (defaulted in make_agent)
    GITHUB_TOKEN          optional — raises the GitHub API rate limit
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
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
# thread_id → {language, since, topic, repos}
_sessions: dict[str, dict] = {}


def _get_session(thread_id: str) -> dict:
    if thread_id not in _sessions:
        _sessions[thread_id] = {
            "language": "",
            "since":    "weekly",
            "topic":    "",
            "repos":    [],
        }
    return _sessions[thread_id]


# ── GitHub REST helpers ─────────────────────────────────────────────────
_GH_API = "https://api.github.com"
_SINCE_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}


def _gh_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "cuga-apps-github-trending",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _since_date(since: str) -> str:
    days = _SINCE_DAYS.get((since or "weekly").lower(), 7)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return cutoff.strftime("%Y-%m-%d")


# ── Tools ────────────────────────────────────────────────────────────────
def _make_tools():
    import httpx
    from langchain_core.tools import tool

    @tool
    def set_filters(thread_id: str, language: str = "", since: str = "",
                    topic: str = "") -> str:
        """Save the user's trending filters for this session. Call this whenever
        the user names a language, time window, or topic.

        Args:
            thread_id: The current session/thread ID (always pass through).
            language:  Programming language filter, e.g. "python", "rust",
                       "typescript". Empty string means "any language".
            since:     Time window — one of "daily", "weekly", "monthly".
                       Empty keeps the current value (default "weekly").
            topic:     Optional GitHub topic to narrow by, e.g. "llm",
                       "agents", "devtools". Empty clears the topic.
        """
        session = _get_session(thread_id)
        if language is not None:
            session["language"] = (language or "").strip().lower()
        if since:
            s = since.strip().lower()
            if s not in _SINCE_DAYS:
                return json.dumps({"ok": False, "code": "bad_input",
                                   "error": "since must be daily, weekly, or monthly"})
            session["since"] = s
        if topic is not None:
            session["topic"] = (topic or "").strip().lower()
        return json.dumps({"ok": True, "data": {
            "language": session["language"] or "any",
            "since":    session["since"],
            "topic":    session["topic"] or "none",
        }})

    @tool
    def find_trending_repos(thread_id: str, language: str = "", since: str = "",
                            topic: str = "", limit: int = 10) -> str:
        """Find repositories trending on GitHub, approximated as recently-created
        repos that have gained the most stars in the time window. Use this as
        the FIRST step of any trending request.

        Args:
            thread_id: The current session/thread ID.
            language:  Language filter (e.g. "python"); empty = any. If empty,
                       the session's saved language is used.
            since:     "daily" | "weekly" | "monthly"; empty uses the session value.
            topic:     Optional GitHub topic filter; empty uses the session value.
            limit:     How many repos to return (1–25, default 10).
        """
        session = _get_session(thread_id)
        language = (language or session["language"] or "").strip().lower()
        since = (since or session["since"] or "weekly").strip().lower()
        topic = (topic or session["topic"] or "").strip().lower()
        limit = max(1, min(int(limit or 10), 25))

        qualifiers = [f"created:>{_since_date(since)}", "stars:>5"]
        if language:
            qualifiers.append(f"language:{language}")
        if topic:
            qualifiers.append(f"topic:{topic}")
        params = {
            "q": " ".join(qualifiers),
            "sort": "stars",
            "order": "desc",
            "per_page": limit,
        }
        try:
            with httpx.Client(timeout=20, headers=_gh_headers()) as client:
                resp = client.get(f"{_GH_API}/search/repositories", params=params)
            if resp.status_code == 403:
                return json.dumps({"ok": False, "code": "rate_limited",
                                   "error": "GitHub API rate limit hit. Set GITHUB_TOKEN "
                                            "to raise it, or try again in a minute."})
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except Exception as exc:  # noqa: BLE001
            log.exception("GitHub search failed")
            return json.dumps({"ok": False, "code": "network_error", "error": str(exc)})

        repos = [{
            "full_name":   it.get("full_name"),
            "url":         it.get("html_url"),
            "description": it.get("description") or "",
            "language":    it.get("language") or "",
            "stars":       it.get("stargazers_count", 0),
            "forks":       it.get("forks_count", 0),
            "open_issues": it.get("open_issues_count", 0),
            "topics":      it.get("topics", [])[:8],
            "created_at":  it.get("created_at"),
            "pushed_at":   it.get("pushed_at"),
            "owner":       (it.get("owner") or {}).get("login"),
        } for it in items]

        log.info("[%s] trending: %d repos (lang=%s since=%s topic=%s)",
                 thread_id[:8], len(repos), language or "any", since, topic or "none")
        return json.dumps({"ok": True, "data": {
            "count":    len(repos),
            "language": language or "any",
            "since":    since,
            "topic":    topic or "none",
            "repos":    repos,
        }})

    @tool
    def get_repo_readme(full_name: str, max_chars: int = 6000) -> str:
        """Fetch a repository's README as raw text so you can summarize what the
        project offers. Call this for each repo you intend to describe in depth.

        Args:
            full_name: "owner/repo", e.g. "langchain-ai/langchain".
            max_chars: Truncate the README to this many characters (default 6000).
        """
        full_name = (full_name or "").strip().strip("/")
        if "/" not in full_name:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "full_name must look like 'owner/repo'"})
        headers = _gh_headers()
        headers["Accept"] = "application/vnd.github.raw+json"
        try:
            with httpx.Client(timeout=20, headers=headers, follow_redirects=True) as client:
                resp = client.get(f"{_GH_API}/repos/{full_name}/readme")
            if resp.status_code == 404:
                return json.dumps({"ok": True, "data": {
                    "full_name": full_name, "readme": "", "note": "No README found."}})
            if resp.status_code == 403:
                return json.dumps({"ok": False, "code": "rate_limited",
                                   "error": "GitHub API rate limit hit."})
            resp.raise_for_status()
            text = resp.text
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"ok": False, "code": "network_error", "error": str(exc)})

        truncated = len(text) > max_chars
        return json.dumps({"ok": True, "data": {
            "full_name": full_name,
            "readme":    text[:max_chars],
            "truncated": truncated,
        }})

    @tool
    def get_repo_languages(full_name: str) -> str:
        """Return the language byte-breakdown for a repo (e.g. {"Python": 82000,
        "TypeScript": 12000}). Useful for describing the stack.

        Args:
            full_name: "owner/repo".
        """
        full_name = (full_name or "").strip().strip("/")
        if "/" not in full_name:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "full_name must look like 'owner/repo'"})
        try:
            with httpx.Client(timeout=20, headers=_gh_headers()) as client:
                resp = client.get(f"{_GH_API}/repos/{full_name}/languages")
            resp.raise_for_status()
            langs = resp.json()
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"ok": False, "code": "network_error", "error": str(exc)})
        total = sum(langs.values()) or 1
        breakdown = sorted(
            ({"language": k, "pct": round(100 * v / total, 1)} for k, v in langs.items()),
            key=lambda d: d["pct"], reverse=True,
        )
        return json.dumps({"ok": True, "data": {"full_name": full_name,
                                                "breakdown": breakdown[:6]}})

    @tool
    def save_repos(thread_id: str, repos_json: str) -> str:
        """Persist the structured, summarized repo board so the UI can render it
        as cards. Call this EVERY time you finish a trending request.

        Args:
            thread_id:  The current session/thread ID.
            repos_json: A JSON array. Each element should include:
                          full_name     (str)  e.g. "owner/repo"
                          url           (str)
                          language      (str)
                          stars         (int)
                          forks         (int)
                          topics        (list[str])
                          summary       (str)  2–3 sentences: what it is / who it's for
                          offers        (list[str], 2–5 bullets of concrete features)
                          why_trending  (str, one sentence)
        """
        session = _get_session(thread_id)
        try:
            repos = json.loads(repos_json)
            if not isinstance(repos, list):
                return json.dumps({"ok": False, "code": "bad_input",
                                   "error": "repos_json must be a JSON array"})
            session["repos"] = repos
            log.info("[%s] saved %d repo cards", thread_id[:8], len(repos))
            return json.dumps({"ok": True, "data": {"saved": len(repos)}})
        except json.JSONDecodeError as exc:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": f"invalid JSON: {exc}"})

    return [
        set_filters, find_trending_repos, get_repo_readme,
        get_repo_languages, save_repos,
    ]


# ── System prompt ────────────────────────────────────────────────────────
_SYSTEM = """\
# GitHub Trending

You surface what's trending on GitHub and explain — in plain English — what
each repository actually offers. The user may ask broadly ("what's trending
this week?") or narrowly ("trending Rust CLI tools", "new LLM agent repos").

## Sequence for every trending request

1. If the user named a language, time window (daily/weekly/monthly), or
   topic, call `set_filters` to record it.
2. Call `find_trending_repos(thread_id=...)`. It returns a ranked list with
   stars, description, and topics. Pull the top 5–8 unless the user asked
   for more.
3. For each repo you'll describe, call `get_repo_readme(full_name=...)` to
   learn what it does. Optionally call `get_repo_languages` for the stack.
   Don't fetch READMEs for repos you won't include.
4. For each repo write:
     - `summary`: 2–3 sentences — what the project is, who it's for, and what
       problem it solves. Ground this in the README; don't invent features.
     - `offers`: 2–5 concrete bullets (capabilities, integrations, notable
       design choices).
     - `why_trending`: one sentence on why it's getting attention now.
5. Call `save_repos(thread_id=..., repos_json=...)` with the full board.
   This step is REQUIRED and is the PRIMARY output — the panel on the right
   is what the user reads. You MUST call it before you reply, even if you
   only have partial results.
6. Reply with a SHORT framing ONLY — 1–2 sentences pointing the user to the
   panel (e.g. how many repos trended and the filters used). Do NOT repeat
   the full structured detail in prose; the panel already shows the ranked
   cards, summaries, and offers.

## Rules
- Never invent stars, descriptions, or features. If a README is empty, say
  the project is sparsely documented and summarize from the description.
- If `find_trending_repos` returns `rate_limited`, tell the user plainly and
  suggest setting GITHUB_TOKEN or retrying shortly.
- Keep the prose reply tight — the right panel shows the detailed cards.

## Thread ID
You will receive the thread_id in every user message (format:
"[thread:<UUID>]"). Always extract it and pass it unchanged to every tool
call that requires thread_id.
"""


# ── CUGA policies ─────────────────────────────────────────────────────────
# Leverage CUGA's policy system to harden the agent: an output_formatter
# locks the board-save + reply contract the UI depends on, and a tool_guide
# enriches the trending search with etiquette the system prompt can only
# loosely suggest. Attached once, lazily, and defensively — if the policy
# store (sqlite-vec) is unavailable the app still runs.
async def _attach_policies(agent) -> None:
    try:
        await agent.policies.add_output_formatter(
            name="repo_board_formatter",
            format_config=(
                "Before replying, ALWAYS call save_repos with the full board "
                "(each repo needs full_name, url, stars, language, a grounded "
                "summary, an offers list, and why_trending). Then reply with a "
                "tight numbered list — each repo as a markdown link with its "
                "star count and a one-line description. No preamble."
            ),
            format_type="markdown",
            keywords=["trending", "repos", "repositories", "stars", "github"],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("output_formatter skipped: %s", exc)
    try:
        await agent.policies.add_tool_guide(
            name="trending_search_etiquette",
            content=(
                "Pull the top 5–8 results unless the user asks for more. Skip "
                "repos whose description AND README are both empty rather than "
                "padding the list. Never fetch the same repo's README twice. If "
                "find_trending_repos returns rate_limited, tell the user to set "
                "GITHUB_TOKEN — do not retry in a loop."
            ),
            target_tools=["find_trending_repos", "get_repo_readme"],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("tool_guide skipped: %s", exc)


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

    app = FastAPI(title="GitHub Trending", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    _agent = None
    _policies_attached = False

    async def _get_agent():
        nonlocal _agent, _policies_attached
        if _agent is None:
            log.info("Initialising CugaAgent…")
            _agent = make_agent()
            log.info("CugaAgent ready.")
        if not _policies_attached:
            try:
                await _attach_policies(_agent)
                log.info("CUGA policies attached.")
            except Exception as exc:  # noqa: BLE001
                log.warning("policy attach failed (continuing without): %s", exc)
            _policies_attached = True
        return _agent

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.post("/ask")
    async def api_ask(req: AskReq):
        from _usage import track_utterance; track_utterance(req.question)
        # Stateless: the panel id keys the per-turn data the UI polls, but we
        # reset it each turn and run the agent on a fresh memory thread, so
        # nothing carries over from the previous question.
        thread_id = req.thread_id or uuid.uuid4().hex
        _sessions.pop(thread_id, None)
        augmented = f"[thread:{thread_id}] {req.question}"
        try:
            agent = await _get_agent()
            result = await agent.invoke(augmented, thread_id=uuid.uuid4().hex)
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

    print(f"\n  GitHub Trending  →  http://127.0.0.1:{port}\n")
    # Public deployment: layered, in-memory rate limiting on POST.
    from _ratelimit import install_rate_limit
    install_rate_limit(app)
    from _usage import install_usage
    install_usage(app)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI entry point ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="GitHub Trending — CUGA demo app")
    parser.add_argument("--port", type=int, default=28823)
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
