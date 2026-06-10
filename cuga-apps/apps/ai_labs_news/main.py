"""
AI Labs News — CUGA Demo App
============================

Get a curated digest of the latest posts from the major AI labs and research
groups — OpenAI, Anthropic, Google DeepMind / Research, Microsoft Research,
IBM Research, Meta AI, Hugging Face, and more. Ask broadly ("what's new in AI
this week?") or narrowly ("latest from Anthropic and OpenAI on agents"), and
the agent pulls each lab's blog feed, dedupes, and summarizes the themes.

All tools are inline @tool defs. The live data comes from each lab's public
RSS/Atom feed via httpx + feedparser — no MCP servers, no API keys.

Run:
    python main.py
    python main.py --port 28824
    python main.py --provider anthropic

Then open: http://127.0.0.1:28824

Environment variables:
    LLM_PROVIDER          rits | anthropic | openai | watsonx | litellm | ollama
    LLM_MODEL             model name override
    AGENT_SETTING_CONFIG  path to CUGA settings TOML (defaulted in make_agent)
"""
from __future__ import annotations

import argparse
import html as _html
import json
import logging
import os
import re
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


# ── Lab registry ─────────────────────────────────────────────────────────
# slug → (display name, [candidate feed URLs tried in order]). Feeds move and
# break; listing fallbacks per lab makes the tool resilient. The first feed
# that parses to >0 entries wins.

def _gnews(query: str) -> str:
    """A Google News RSS search feed for `query`. Used as a reliable fallback
    for labs that don't publish a working native blog feed (Anthropic, Meta AI,
    IBM Research as of 2026 all 404 on their old RSS paths). Returns recent
    news items about the lab — not their own blog posts — but it keeps the lab
    reachable instead of silently dropping out of the digest."""
    from urllib.parse import quote_plus
    return ("https://news.google.com/rss/search?q="
            + quote_plus(query)
            + "&hl=en-US&gl=US&ceid=US:en")


_LABS: dict[str, dict] = {
    "openai": {
        "name": "OpenAI",
        "feeds": ["https://openai.com/news/rss.xml", "https://openai.com/blog/rss.xml"],
    },
    "anthropic": {
        "name": "Anthropic",
        # Anthropic publishes no working RSS feed (all known paths 404), so we
        # fall back to a Google News search scoped to Anthropic/Claude.
        "feeds": [_gnews("Anthropic Claude AI")],
    },
    "google-deepmind": {
        "name": "Google DeepMind",
        "feeds": ["https://deepmind.google/blog/rss.xml",
                  "https://deepmind.google/discover/blog/rss.xml"],
    },
    "google-research": {
        "name": "Google Research",
        "feeds": ["https://research.google/blog/rss/",
                  "http://feeds.feedburner.com/blogspot/gJZg"],
    },
    "microsoft-research": {
        "name": "Microsoft Research",
        "feeds": ["https://www.microsoft.com/en-us/research/feed/"],
    },
    "ibm-research": {
        "name": "IBM Research",
        # Native blog RSS paths 404 as of 2026 — fall back to Google News.
        "feeds": ["https://research.ibm.com/blog/rss.xml",
                  _gnews('"IBM Research" AI')],
    },
    "meta-ai": {
        "name": "Meta AI",
        # Native blog RSS paths 404 as of 2026 — fall back to Google News.
        "feeds": ["https://ai.meta.com/blog/rss/",
                  _gnews('"Meta AI" OR "Meta FAIR" research')],
    },
    "huggingface": {
        "name": "Hugging Face",
        "feeds": ["https://huggingface.co/blog/feed.xml"],
    },
    "bair": {
        "name": "Berkeley AI Research",
        "feeds": ["https://bair.berkeley.edu/blog/feed.xml"],
    },
}

_DEFAULT_LABS = ["openai", "anthropic", "google-deepmind", "microsoft-research",
                 "ibm-research", "huggingface"]


# ── Per-thread session store ────────────────────────────────────────────
# thread_id → {focus_labs, topics, digest}
_sessions: dict[str, dict] = {}


def _get_session(thread_id: str) -> dict:
    if thread_id not in _sessions:
        _sessions[thread_id] = {
            "focus_labs": [],     # restricts which labs to pull
            "topics":     [],     # keyword filter applied to entries
            "digest":     None,   # structured digest the right panel renders
        }
    return _sessions[thread_id]


def _append_unique(lst: list[str], value: str) -> None:
    if value and value.lower() not in [v.lower() for v in lst]:
        lst.append(value)


def _clean_html(raw: str, limit: int = 400) -> str:
    """Strip tags + collapse whitespace from a feed summary."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = _html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def _entry_iso(entry) -> str:
    for key in ("published_parsed", "updated_parsed"):
        tm = entry.get(key)
        if tm:
            try:
                return datetime(*tm[:6], tzinfo=timezone.utc).isoformat()
            except Exception:  # noqa: BLE001
                pass
    return ""


# ── Tools ────────────────────────────────────────────────────────────────
def _make_tools():
    import httpx
    import feedparser
    from langchain_core.tools import tool

    def _fetch_feed(slug: str):
        meta = _LABS.get(slug)
        if not meta:
            return None, "unknown lab"
        last_err = "no entries"
        for url in meta["feeds"]:
            try:
                with httpx.Client(timeout=20, follow_redirects=True,
                                  headers={"User-Agent": "Mozilla/5.0 (cuga-apps ai-labs-news)"}) as client:
                    resp = client.get(url)
                resp.raise_for_status()
                parsed = feedparser.parse(resp.content)
                if parsed.entries:
                    return parsed, url
                last_err = "feed parsed but empty"
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
                continue
        return None, last_err

    @tool
    def list_labs() -> str:
        """List the AI labs / research groups this app can pull news from, with
        their slugs. Call this if the user asks "which labs do you cover?" or
        names a lab you're unsure how to address.
        """
        return json.dumps({"ok": True, "data": {
            "labs": [{"slug": s, "name": m["name"]} for s, m in _LABS.items()],
            "default": _DEFAULT_LABS,
        }})

    @tool
    def set_focus(thread_id: str, labs_csv: str = "", topics_csv: str = "") -> str:
        """Record which labs and/or topics to focus on for this session.

        Args:
            thread_id:  The current session/thread ID (always pass through).
            labs_csv:   Comma-separated lab slugs (see list_labs), e.g.
                        "openai,anthropic". Empty leaves the focus unchanged.
            topics_csv: Comma-separated keyword filters, e.g. "agents,safety".
                        Entries must match at least one to be included.
        """
        session = _get_session(thread_id)
        if labs_csv.strip():
            slugs = [s.strip().lower() for s in labs_csv.split(",") if s.strip()]
            unknown = [s for s in slugs if s not in _LABS]
            if unknown:
                return json.dumps({"ok": False, "code": "bad_input",
                                   "error": f"unknown lab slug(s): {', '.join(unknown)}. "
                                            f"Valid: {', '.join(_LABS)}"})
            session["focus_labs"] = slugs
        if topics_csv.strip():
            for t in topics_csv.split(","):
                _append_unique(session["topics"], t.strip())
        return json.dumps({"ok": True, "data": {
            "focus_labs": session["focus_labs"] or _DEFAULT_LABS,
            "topics":     session["topics"],
        }})

    @tool
    def fetch_lab_news(lab: str, limit: int = 6) -> str:
        """Fetch the most recent posts from ONE lab's blog feed.

        Args:
            lab:   Lab slug (see list_labs), e.g. "anthropic".
            limit: Max entries to return (1–15, default 6).
        """
        slug = (lab or "").strip().lower()
        limit = max(1, min(int(limit or 6), 15))
        parsed, info = _fetch_feed(slug)
        if not parsed:
            return json.dumps({"ok": False, "code": "feed_error",
                               "error": f"could not load feed for '{slug}': {info}"})
        name = _LABS[slug]["name"]
        items = []
        for e in parsed.entries[:limit]:
            items.append({
                "lab":       name,
                "lab_slug":  slug,
                "title":     _clean_html(e.get("title", ""), 200),
                "url":       e.get("link", ""),
                "published": _entry_iso(e),
                "summary":   _clean_html(e.get("summary", e.get("description", "")), 400),
            })
        log.info("[news] %s → %d entries", slug, len(items))
        return json.dumps({"ok": True, "data": {"lab": name, "slug": slug,
                                                "count": len(items), "items": items}})

    @tool
    def fetch_all_news(thread_id: str, labs_csv: str = "", per_lab: int = 4) -> str:
        """Fetch recent posts across MULTIPLE labs at once and return them merged,
        newest first. Use this as the main gathering step for a digest.

        Args:
            thread_id: The current session/thread ID.
            labs_csv:  Comma-separated lab slugs; empty uses the session focus,
                       or the default lab set if no focus is set.
            per_lab:   Max entries per lab (1–10, default 4).
        """
        session = _get_session(thread_id)
        per_lab = max(1, min(int(per_lab or 4), 10))
        if labs_csv.strip():
            slugs = [s.strip().lower() for s in labs_csv.split(",") if s.strip()]
        else:
            slugs = session["focus_labs"] or _DEFAULT_LABS
        slugs = [s for s in slugs if s in _LABS]

        all_items, failed = [], []
        for slug in slugs:
            parsed, info = _fetch_feed(slug)
            if not parsed:
                failed.append({"slug": slug, "error": info})
                continue
            name = _LABS[slug]["name"]
            for e in parsed.entries[:per_lab]:
                all_items.append({
                    "lab":       name,
                    "lab_slug":  slug,
                    "title":     _clean_html(e.get("title", ""), 200),
                    "url":       e.get("link", ""),
                    "published": _entry_iso(e),
                    "summary":   _clean_html(e.get("summary", e.get("description", "")), 400),
                })

        all_items.sort(key=lambda d: d["published"], reverse=True)
        log.info("[news] aggregated %d items from %d labs (%d failed)",
                 len(all_items), len(slugs) - len(failed), len(failed))
        return json.dumps({"ok": True, "data": {
            "count":     len(all_items),
            "labs_ok":   [s for s in slugs if s not in [f["slug"] for f in failed]],
            "labs_failed": failed,
            "items":     all_items,
        }})

    @tool
    def save_digest(thread_id: str, digest_json: str) -> str:
        """Persist the structured news digest so the right-panel UI can render it.
        Call this at the END of every digest turn.

        Args:
            thread_id:   The current session/thread ID.
            digest_json: A JSON object with this shape:
                {
                  "headline": str,            # one-line "state of AI this week"
                  "themes":   [str, ...],     # 2–4 cross-lab themes you noticed
                  "items": [                  # the posts, newest first
                    {"lab": str, "title": str, "url": str,
                     "published": str, "summary": str, "tags": [str, ...]}
                  ]
                }
        """
        session = _get_session(thread_id)
        try:
            digest = json.loads(digest_json)
            if not isinstance(digest, dict):
                return json.dumps({"ok": False, "code": "bad_input",
                                   "error": "digest_json must be a JSON object"})
            digest["_at"] = datetime.now(timezone.utc).isoformat()
            session["digest"] = digest
            log.info("[%s] digest saved (%d items)",
                     thread_id[:8], len(digest.get("items", [])))
            return json.dumps({"ok": True, "data": {"saved": True,
                                                    "items": len(digest.get("items", []))}})
        except json.JSONDecodeError as exc:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": f"invalid JSON: {exc}"})

    return [list_labs, set_focus, fetch_lab_news, fetch_all_news, save_digest]


# ── System prompt ────────────────────────────────────────────────────────
_SYSTEM = """\
# AI Labs News

You produce a clean, glanceable digest of the latest posts from the major AI
labs and research groups, pulled live from their blog feeds.

## Sequence for every request

1. If the user named specific labs ("from OpenAI and Anthropic") or topics
   ("on agents", "about safety"), call `set_focus` with the matching slugs /
   topics. Use `list_labs` if you're unsure of a slug.
2. Call `fetch_all_news(thread_id=...)` to gather recent posts across the
   focused labs (or the defaults). If the user asked about exactly one lab,
   you may use `fetch_lab_news` instead.
3. If topics were set, keep only entries whose title or summary plausibly
   matches a topic; drop the rest.
4. Identify 2–4 cross-lab `themes` (e.g. "agentic tooling", "smaller models",
   "evals/safety"). Write a one-line `headline`.
5. For each item, copy `lab`, `title`, `url`, `published`, and a 1–2 sentence
   `summary` straight from the feed (don't embellish). Add 1–3 short `tags`.
6. Call `save_digest(thread_id=..., digest_json=...)`. This step is REQUIRED and
   is the PRIMARY output — the panel on the right is what the user reads. You
   MUST call it before you reply, even if you only have partial results.
7. Reply with a SHORT framing ONLY — 1–2 sentences pointing the user to the
   panel (e.g. the headline plus a nudge to scan the posts on the right). Do NOT
   repeat the full structured rundown in prose; the panel already shows it.
   Mention if any lab's feed couldn't be reached.

## Rules
- Never invent posts, dates, or quotes. Only report what the feeds returned.
- If `labs_failed` is non-empty, note which labs were unreachable rather than
  guessing their news.
- Keep the prose tight — the right panel shows the full item list.

## Thread ID
You will receive the thread_id in every user message (format:
"[thread:<UUID>]"). Always extract it and pass it unchanged to every tool
call that requires thread_id.
"""


# ── CUGA policies ─────────────────────────────────────────────────────────
# Leverage CUGA's policy system: an output_formatter locks the digest-save +
# reply contract, and a tool_guide enforces the "never invent news" rule on
# the feed-gathering tools. Attached once, lazily, and defensively.
async def _attach_policies(agent) -> None:
    try:
        await agent.policies.add_output_formatter(
            name="digest_formatter",
            format_config=(
                "Before replying, ALWAYS call save_digest with a one-line "
                "headline, 2–4 cross-lab themes, and the items list. Then in "
                "prose lead with the headline, give a short grouped rundown "
                "citing posts as markdown links, and note any lab whose feed "
                "was unreachable. Keep it tight."
            ),
            format_type="markdown",
            keywords=["news", "digest", "latest", "what's new", "posts", "labs"],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("output_formatter skipped: %s", exc)
    try:
        await agent.policies.add_tool_guide(
            name="feed_integrity_guide",
            content=(
                "Only report entries the feeds actually returned — never invent "
                "posts, dates, titles, or quotes. If labs_failed is non-empty, "
                "name those labs as unreachable rather than guessing their news. "
                "Respect the session's focus labs and topic filters."
            ),
            target_tools=["fetch_all_news", "fetch_lab_news"],
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
        # Each question is independent. Disable the persistent knowledge store
        # and on-disk policy auto-load so nothing learned/saved in one question
        # leaks into the next via the shared .cuga folder. The output formatter
        # we need is attached explicitly in _attach_policies().
        enable_knowledge=False,
        auto_load_policies=False,
    )


# ── Request models ──────────────────────────────────────────────────────
class AskReq(BaseModel):
    question: str
    thread_id: str = ""


# ── HTTP server ──────────────────────────────────────────────────────────
def _web(port: int) -> None:
    import uvicorn

    app = FastAPI(title="AI Labs News", docs_url=None, redoc_url=None)
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
            # Use the agent's synthesised answer, NOT str(result): the result
            # object's repr dumps the CUGA plan + generated code, which is what
            # was leaking into the chat as an unformatted blob.
            answer = result.answer if hasattr(result, "answer") else str(result)
            return {"answer": answer, "thread_id": thread_id}
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

    print(f"\n  AI Labs News  →  http://127.0.0.1:{port}\n")
    # Public deployment: layered, in-memory rate limiting on POST.
    from _ratelimit import install_rate_limit
    install_rate_limit(app)
    from _usage import install_usage
    install_usage(app)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI entry point ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="AI Labs News — CUGA demo app")
    parser.add_argument("--port", type=int, default=28824)
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
