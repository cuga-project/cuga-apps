"""
Web Researcher — research with evidence, powered by Tavily's MCP server
=======================================================================

Every research mode puts one Tavily strength to work, through Tavily's hosted
MCP server — all five of the tools it offers:

  Quick answer   tavily_search (fast)
  Deep dive      tavily_search (advanced) → tavily_extract with a query
  Site study     tavily_map → tavily_crawl / tavily_extract on one website
  Report         tavily_research → tavily_extract to quote the key sources
  Watch          tavily_search (news, since the last run) on a schedule
  Rating         a 👍/👎 is saved, and sent to Tavily with tavily_feedback once the
                 hosted server offers that tool (Tavily's open-source server has it)

CUGA plans the work and governs it: policies (intent guard, playbook, tool
guide, output formatter), code guards on every Tavily call (no secrets or
internal names leave; the user's source rules and the mode's tools and budget
are enforced), and a claim check after every answer — each claim's quote must
appear on a page the run actually read, or it is marked "not verified".

Run:
    python main.py --port 28798
Then open: http://127.0.0.1:28798

Environment variables:
    LLM_PROVIDER, LLM_MODEL, AGENT_SETTING_CONFIG
    TAVILY_API_KEY    Tavily's hosted MCP server (mcp.tavily.com)
    WR_INTERNAL_TERMS extra comma-separated words the egress guard blocks
    WR_FEEDBACK       set to 0 to turn off sending ratings to Tavily
"""

import argparse
import asyncio
import functools
import json
import logging
import os
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

_DIR       = Path(__file__).parent
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

# This app's CUGA policies live in their own store (the default store is shared
# by every app on the filesystem; another app clearing it would wipe these), and
# CUGA's run receipt is on so each answer shows tokens and LLM calls. Set before
# cuga is imported — Dynaconf reads the environment once.
(_DIR / ".cuga").mkdir(exist_ok=True)
os.environ.setdefault("DYNACONF_POLICY__POLICY_DB_PATH", str(_DIR / ".cuga" / "policies.db"))
os.environ.setdefault("DYNACONF_ADVANCED_FEATURES__RUN_RECEIPT", "true")

import research  # noqa: E402
import verifier  # noqa: E402
from ui import _HTML  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

TAVILY_TOOLS = {"tavily_search", "tavily_extract", "tavily_crawl", "tavily_map", "tavily_research"}
_STATUS: dict = {"tavily": "not loaded"}
_POLICIES: list[str] = []
_TAVILY_RAW: dict = {}          # unguarded tools, for the app's own claim checks
_VCTX: dict = {}                # the verifier's view of the current run (see verifier.make_tools)

# ---------------------------------------------------------------------------
# Persistent store
# ---------------------------------------------------------------------------

_STORE_PATH = _DIR / ".store.json"


def _load_store() -> dict:
    try:
        if _STORE_PATH.exists():
            return json.loads(_STORE_PATH.read_text())
    except Exception:
        pass
    return {}


def _save_store(data: dict) -> None:
    _STORE_PATH.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# SQLite research log
# ---------------------------------------------------------------------------

_DB_PATH = _DIR / "research.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS research_log (
    id         TEXT PRIMARY KEY,
    topic      TEXT NOT NULL,
    report     TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'chat',
    emailed    INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
"""
# Added for evidence-backed reports; older databases get them on start.
_EXTRA_COLUMNS = {"mode": "TEXT", "claims": "TEXT", "sources": "TEXT", "receipt": "TEXT",
                  "extra": "TEXT", "rating": "TEXT"}


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def _init_db() -> None:
    with _db() as con:
        con.execute(_CREATE_SQL)
        have = {r["name"] for r in con.execute("PRAGMA table_info(research_log)")}
        for col, kind in _EXTRA_COLUMNS.items():
            if col not in have:
                con.execute(f"ALTER TABLE research_log ADD COLUMN {col} {kind}")


def _save_report(topic: str, report: str, source: str = "chat", emailed: bool = False,
                 mode: str = "", claims: list | None = None, sources: list | None = None,
                 receipt: dict | None = None, extra: dict | None = None) -> dict:
    rid = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).isoformat()
    with _db() as con:
        con.execute(
            "INSERT INTO research_log (id, topic, report, source, emailed, created_at, mode, claims, "
            "sources, receipt, extra) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (rid, topic, report, source, int(emailed), now, mode, json.dumps(claims or []),
             json.dumps(sources or []), json.dumps(receipt or {}), json.dumps(extra or {})),
        )
    return {"id": rid, "topic": topic, "report": report, "source": source,
            "emailed": emailed, "created_at": now}


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("claims", "sources", "receipt", "extra"):
        try:
            d[k] = json.loads(d.get(k) or ("[]" if k in ("claims", "sources") else "{}"))
        except (TypeError, json.JSONDecodeError):
            d[k] = [] if k in ("claims", "sources") else {}
    return d


def _list_reports(limit: int = 50) -> list[dict]:
    with _db() as con:
        rows = con.execute(
            "SELECT * FROM research_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row(r) for r in rows]


def _get_report(rid: str) -> Optional[dict]:
    with _db() as con:
        r = con.execute("SELECT * FROM research_log WHERE id = ?", (rid,)).fetchone()
    return _row(r) if r else None


# ---------------------------------------------------------------------------
# Run context — one agent run at a time, so the guards can report what they did
# ---------------------------------------------------------------------------

_RUN_LOCK = asyncio.Lock()
_RUN: dict = {}


def _reset_run(mode: str, rules: dict, job: Optional[dict], report_model: str, since: str = "") -> None:
    _RUN.clear()
    _RUN.update(mode=mode, rules=rules, job=job, report_model=report_model, since=since,
                events=[], sources=[], counts={}, by_tool={}, pages={}, cache={}, request_ids=[])


def _event(policy: str, outcome: str, detail: str) -> None:
    _RUN.setdefault("events", []).append({"policy_name": policy, "policy_type": "app_guard",
                                          "outcome": outcome, "reasoning": detail})


def _step(text: str) -> None:
    job = _RUN.get("job")
    if job is not None:
        job["steps"].append({"t": round(time.time() - job["started"], 1), "text": text[:180]})


def _target(name: str, kwargs: dict) -> str:
    if name == "tavily_search":
        return f'"{kwargs.get("query", "")}"'
    if name == "tavily_extract":
        urls = kwargs.get("urls") or []
        return ", ".join(research._host(u) for u in urls[:3]) + (f" +{len(urls) - 3}" if len(urls) > 3 else "")
    if name == "tavily_research":
        return f'{kwargs.get("model", "")} · "{str(kwargs.get("input", ""))[:80]}"'
    return research._host(kwargs.get("url") or "")


# Per-call shaping. Crawl/map default to 50 pages and follow external links;
# whole pages would flood the model's context. Capped here, not just asked for.
_CRAWL = {"limit": 12, "max_depth": 2, "max_breadth": 12}
_MAP = {"limit": 40, "max_depth": 2, "max_breadth": 20}
_PAGE_CHARS = {"tavily_search": 1500, "tavily_extract": 6000, "tavily_crawl": 3500, "tavily_research": 9000}


def _shape(name: str, kwargs: dict) -> None:
    mode = _RUN.get("mode")
    if name == "tavily_search":
        kwargs.setdefault("search_depth", "fast" if mode == "quick" else "advanced")
        try:
            kwargs["max_results"] = max(5, min(int(kwargs.get("max_results") or 6), 8))
        except (TypeError, ValueError):
            kwargs["max_results"] = 6
        kwargs["include_raw_content"] = False
        if mode == "watch" and _RUN.get("since"):
            kwargs["start_date"] = _RUN["since"]
            kwargs["topic"] = "news"
            kwargs.pop("time_range", None)
    elif name in ("tavily_crawl", "tavily_map"):
        caps = _CRAWL if name == "tavily_crawl" else _MAP
        for key, cap in caps.items():
            try:
                kwargs[key] = min(int(kwargs.get(key) or cap), cap)
            except (TypeError, ValueError):
                kwargs[key] = cap
        kwargs["allow_external"] = False
    elif name == "tavily_extract":
        kwargs["urls"] = list(kwargs.get("urls") or [])[:4]
        kwargs.setdefault("format", "markdown")
    elif name == "tavily_research":
        kwargs["model"] = _RUN.get("report_model") or "mini"


def _remember(name: str, result) -> None:
    """Keep every page's full text (to check quotes against), its URL, and the
    request id (for feedback to Tavily). Map results are URLs only, not pages read."""
    if not isinstance(result, dict):
        return
    if result.get("request_id"):
        _RUN["request_ids"].append({"tool": name, "id": result["request_id"]})
    urls = []
    if name == "tavily_research":
        for s in result.get("sources") or []:
            if isinstance(s, dict) and s.get("url"):
                urls.append(s["url"])
    elif name != "tavily_map":
        for r in result.get("results") or []:
            if isinstance(r, dict) and r.get("url"):
                urls.append(r["url"])
                text = ((r.get("title") or "") + "\n" + (r.get("raw_content") or "") + "\n"
                        + (r.get("content") or ""))
                _RUN["pages"][r["url"]] = _RUN["pages"].get(r["url"], "") + "\n" + text
    for u in urls:
        if u not in _RUN["sources"] and len(_RUN["sources"]) < 30 and "docs.tavily.com/documentation/api" not in u:
            _RUN["sources"].append(u)


def _trim(name: str, result):
    cap = _PAGE_CHARS.get(name)
    if not cap or not isinstance(result, dict):
        return result
    out = dict(result)
    if name == "tavily_research" and isinstance(out.get("content"), str) and len(out["content"]) > cap:
        out["content"] = out["content"][:cap] + "\n…[trimmed]"
    rows = []
    for r in out.get("results") or []:
        if isinstance(r, dict):
            r = dict(r)
            for key in ("raw_content", "content"):
                text = r.get(key)
                if isinstance(text, str) and len(text) > cap:
                    r[key] = text[:cap] + f"\n…[trimmed {len(text) - cap} characters]"
        rows.append(r)
    if rows:
        out["results"] = rows
    out.pop("auth_mode", None)
    return out


def _guard_tavily(tool):
    """Wrap a Tavily tool: egress guard, mode tools, source rules, budget, evidence capture."""
    original = tool.coroutine
    name = tool.name

    @functools.wraps(original)
    async def guarded(*args, **kwargs):
        mode = _RUN.get("mode", "deep")
        spec = research.MODES.get(mode, research.MODES["deep"])
        reasons = research.egress_violations(kwargs)
        if reasons:
            _event("Egress guard", "blocked", f"{name}: {', '.join(reasons)} in the request")
            _step(f"Blocked · {name}: {', '.join(reasons)}")
            return (f"BLOCKED by egress guard: the request contained {', '.join(reasons)}. Secrets, "
                    "personal emails and internal names never go to outside services. Do not retry "
                    "with the same data; tell the user what was blocked and why.")
        if name not in spec["tools"]:
            _event("Mode tools", "blocked", f"{name} is not part of {spec['title']}")
            return (f"NOT AVAILABLE in {spec['title']} mode: use {', '.join(sorted(spec['tools']))}.")
        if mode == "site" and name in ("tavily_search", "tavily_extract") and not _RUN["by_tool"].get("tavily_map"):
            # A site study starts by laying out the site; reading comes after.
            _event("Mode tools", "applied", f"{name} held until tavily_map has laid out the site")
            return ("Start this Site study with tavily_map on the website URL (with `instructions`), "
                    "then tavily_crawl the relevant section. Search and extract come after that.")
        if name == "tavily_research" and _RUN["by_tool"].get("tavily_research"):
            _event("Read budget", "blocked", "tavily_research already ran in this report")
            return "tavily_research already ran for this question. Use its report and sources."
        applied, refused = research.apply_source_rules(name, kwargs, _RUN["rules"])
        if refused:
            _event("Source rules", "blocked", f"{name}: {refused}")
            _step(f"Blocked · {name}: {refused}")
            return f"BLOCKED by your source rules: {refused}. Stay within: {_RUN['rules']['summary']}."
        if applied:
            _event("Source rules", "applied", f"{name}: " + ", ".join(applied))
        _shape(name, kwargs)
        key = name + json.dumps(kwargs, sort_keys=True, default=str)
        if key in _RUN["cache"]:
            _event("Read budget", "applied", f"{name}: repeated call answered from this run's earlier read")
            return {"note": "You already read this. Use what you have; do not repeat it.",
                    "result": _RUN["cache"][key]}
        budget = int(spec["budget"])
        if _RUN["counts"].get("tavily", 0) >= budget:
            _event("Read budget", "blocked", f"{name}: this run's {budget} outside reads are used up")
            return (f"BUDGET REACHED: this {spec['title']} may make {budget} outside reads. "
                    "Do not call Tavily again; answer now from what you have read.")
        _RUN["counts"]["tavily"] = _RUN["counts"].get("tavily", 0) + 1
        _RUN["by_tool"][name] = _RUN["by_tool"].get(name, 0) + 1
        _step(f"{name} · {_target(name, kwargs)}")
        result = await original(*args, **kwargs)
        _remember(name, result)
        if name == "tavily_map" and isinstance(result, dict):
            _step(f"Mapped · {len(result.get('results') or [])} pages on {research._host(kwargs.get('url', ''))}")
        result = _trim(name, result)
        _RUN["cache"][key] = result
        return result

    tool.coroutine = guarded
    return tool


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_SYSTEM = """\
# Web Researcher

You research questions on the live web with Tavily's tools and answer with evidence.
Each request starts with a [Mode] block (which tools to use and how), [Source rules]
and a read budget. Follow them; the app enforces them anyway.

## Evidence rules
- Answer only from what the tools return in this run. Never from memory.
- Every claim you make needs a quote copied word for word from a page you read here,
  and that page's URL: one continuous sentence, no ellipses, no paraphrase. Pick the
  sentence that states the claim most directly, not the page's introduction.
  Prefer primary sources (the organisation, paper or docs itself).
- Use tavily_extract with a `query` to get the exact passage before you quote a page.
- If sources disagree, say so. If you could not find something, say so.
- Check dates against [Today]. If your sources are older than the question needs, say how old
  they are rather than presenting them as current.
- If a tool answers BLOCKED, NOT AVAILABLE or BUDGET REACHED, do not retry it; work
  with what you have and tell the user what was blocked and why.

## Answer format
1. **Answer** — 2-5 sentences that answer the question directly, citing sources as [1], [2].
2. **Key findings** — 3-6 bullets, each with its source number.
3. **Sources** — numbered list: title — URL.
4. End with a fenced json block, exactly this shape:
```json
{"claims": [{"claim": "one factual statement from your answer",
             "quote": "the exact sentence from the page that supports it",
             "source_url": "https://..."}],
 "follow_ups": ["a useful next question", "another"]}
```
Include 3-6 claims (your most important ones) and 2-3 follow-up questions.
"""

_PLAYBOOK = """\
# Research method

1. Read the [Mode] block and use only its tools, in its order.
2. Search narrowly: short queries in the words the page itself would use.
3. Read before you quote: tavily_extract (with a query) the pages you rely on.
4. Write the answer, then the claims block — every claim with an exact quote and its URL.
"""


async def _setup_policies(agent) -> None:
    p = agent.policies
    try:
        await p.clear()
    except Exception as exc:  # noqa: BLE001
        log.debug("policy clear skipped: %s", exc)

    async def add(label: str, coro) -> None:
        try:
            await coro
            _POLICIES.append(label)
        except Exception as exc:  # noqa: BLE001
            log.warning("policy %s skipped: %s", label, exc)

    await add("Intent guard · No profiling private people", p.add_intent_guard(
        name="No profiling private people",
        description="Refuse to dig up personal information about private individuals.",
        keywords=["home address", "phone number of", "dox", "where does she live", "where does he live",
                  "personal email of", "find everything about my"],
        intent_examples=[
            "Find the home address and phone number of my neighbour",
            "Dig up everything you can about this private person",
            "Where does this person live and who are their family members?",
        ],
        response=("I don't research private individuals' personal details. I can research public "
                  "topics, organisations, products, or public figures' public roles and statements."),
    ))
    await add("Playbook · Research method", p.add_playbook(
        name="Research method",
        content=_PLAYBOOK,
        keywords=["research", "find", "latest", "compare", "explain", "report"],
        natural_language_trigger=["Research this question and answer with sources"],
    ))
    await add("Tool guide · Quote primary sources", p.add_tool_guide(
        name="Quote primary sources",
        content=("Stay within the run's source rules. Prefer primary sources. Before quoting a page, "
                 "read it with tavily_extract and a `query`; quote its sentences word for word."),
        target_tools=sorted(TAVILY_TOOLS),
    ))
    await add("Output formatter · Answer with evidence", p.add_output_formatter(
        name="Answer with evidence",
        format_config=("Keep the Answer, Key findings and Sources sections, and the final fenced "
                       "```json claims block exactly as written. Never drop the json block."),
        format_type="markdown",
        keywords=["research", "answer", "report"],
    ))
    log.info("policies registered: %s", ", ".join(_POLICIES) or "none")


def _make_tools():
    from _mcp_bridge import load_tools, remote_mcp_configured
    _TAVILY_RAW.clear()
    if not remote_mcp_configured("tavily"):
        _STATUS["tavily"] = "TAVILY_API_KEY not set"
        return []
    try:
        offered = load_tools(["tavily"])
        _STATUS["offered"] = sorted(t.name for t in offered)
        tav = [t for t in offered if t.name in TAVILY_TOOLS]
    except Exception as exc:  # noqa: BLE001
        _STATUS["tavily"] = f"error: {exc}"
        log.exception("Tavily MCP failed to load")
        return []
    for t in tav:
        _TAVILY_RAW[t.name] = t.coroutine
    _STATUS["tavily"] = f"ready · {len(tav)} tools"
    return [_guard_tavily(t) for t in tav]


def make_agent():
    from cuga import CugaAgent
    from _llm import create_llm

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
        # Each question is independent — no persistent knowledge store; the
        # policies are registered in code, not auto-loaded from disk.
        enable_knowledge=False,
        auto_load_policies=False,
    )


def _preamble(mode: str, rules: dict, site_url: str, since: str, report_model: str) -> str:
    spec = research.MODES[mode]
    lines = [
        f"[Today] {datetime.now(timezone.utc).date().isoformat()}",
        f"[Mode: {spec['title']}] {spec['how']}",
        f"Tools for this mode: {', '.join(sorted(spec['tools']))}. Read budget: {spec['budget']} Tavily calls.",
        f"[Source rules] {rules['summary']}",
    ]
    if rules.get("include_domains"):
        lines.append("include_domains: " + ", ".join(rules["include_domains"]))
    if rules.get("exclude_domains"):
        lines.append("exclude_domains: " + ", ".join(rules["exclude_domains"]))
    if site_url:
        lines.append(f"[Website] {site_url}")
    if mode == "report":
        lines.append(f"[tavily_research model] {report_model}")
    if since:
        lines.append(f"[New since] {since} — use it as start_date.")
    if rules.get("recent"):
        year = datetime.now(timezone.utc).year
        lines.append(f"[Recency] The question asks for the current state. Put {year} in your search "
                     "queries, search the official site first (for example with include_domains), and "
                     "state the date of the sources you rely on. Older pages may be out of date.")
    return "\n".join(lines)


_CLAIMS_PROMPT = """From the research answer below, return ONLY a JSON object, no prose:
{"claims": [{"claim": "...", "quote": "...", "source_url": "https://..."}], "follow_ups": ["..."]}
Use the answer's 3-6 most important factual statements about the topic. Copy quotes and URLs exactly
as written in the answer; if a statement has no quote, use the statement's own words; if it has no
URL, use "". Statements about the search itself ("no source was found") are not claims. If the
answer found nothing, return {"claims": [], "follow_ups": []}.

Answer:
"""


async def _claims_from_prose(answer: str) -> tuple[list[dict], list[str]]:
    """The model answered but left out the claims block: pull the claims out
    (one small LLM call) so they can still be checked."""
    from _llm import create_llm
    try:
        llm = create_llm(provider=os.getenv("LLM_PROVIDER"), model=os.getenv("LLM_MODEL"))
        msg = await llm.ainvoke(_CLAIMS_PROMPT + answer[:12000])
        text = getattr(msg, "content", "") or ""
        if "```" not in text:
            text = f"```json\n{text.strip()}\n```"
        _, claims, follow = research.split_claims(text)
        return claims, follow
    except Exception as exc:  # noqa: BLE001
        log.warning("claims extraction failed: %s", exc)
        return [], []


async def _extract_page(url: str, query: str) -> str:
    """App-side read of one page (for claim checks), outside the agent's budget."""
    extract = _TAVILY_RAW.get("tavily_extract")
    if not extract or research.egress_violations({"url": url, "query": query}):
        return ""
    try:
        res = await extract(urls=[url], query=query[:300], format="text")
    except Exception as exc:  # noqa: BLE001
        log.warning("claim check read failed for %s: %s", url, exc)
        return ""
    if isinstance(res, dict) and res.get("request_id") and _RUN.get("request_ids") is not None:
        _RUN["request_ids"].append({"tool": "tavily_extract", "id": res["request_id"]})
    rows = (res.get("results") if isinstance(res, dict) else None) or []
    return "\n".join((r.get("raw_content") or "") for r in rows if isinstance(r, dict))


async def _check_claims(claims: list[dict], max_rereads: int = 3) -> list[dict]:
    """Mark each claim verified (its quote is on a page this run read) or not.
    A claim citing a page the run hasn't read in full is re-read once with
    tavily_extract — the app checking the agent, not the agent checking itself."""
    rereads = 0
    out = []
    for c in claims:
        c = dict(c)
        url, quote = c.get("source_url", ""), c.get("quote", "")
        page = research.find_page(url, _RUN["pages"]) if url else None
        ok = bool(page and quote and research.quote_supported(quote, page))
        how = "on a page read in this run" if ok else ""
        if not ok and url and quote and rereads < max_rereads:
            rereads += 1
            _RUN["counts"]["check"] = _RUN["counts"].get("check", 0) + 1
            _step(f"Claim check · re-reading {research._host(url)}")
            fresh = await _extract_page(url, c.get("claim") or quote)
            if fresh:
                _RUN["pages"][url] = (_RUN["pages"].get(url, "") + "\n" + fresh)
                ok = research.quote_supported(quote, fresh)
                how = "re-read by the app with tavily_extract" if ok else ""
                page = (page or "") + "\n" + fresh
        c["verified"] = ok
        c["on_page"] = ok
        c["_page"] = page or ""
        c["checked"] = how or ("no source URL" if not url else "quote not found on the page")
        if not ok and page:
            c["passage"] = research.best_passage(c.get("claim", ""), page)
        out.append(c)
    return out


_SUPPORT_PROMPT = """For each numbered pair, decide whether the QUOTE backs up the CLAIM.
Say true when the quote states the claim's main point or directly implies it; a fair paraphrase is fine.
Say false only when the quote is about something else, contradicts the claim, or the claim adds a
specific fact the quote doesn't contain (a number, version, date or name).
Return ONLY JSON: {"results": [{"n": 1, "supports": true, "why": "short reason"}]}

"""


async def _ask_support(pairs: list[tuple[str, str]]) -> dict[int, dict]:
    """One batched LLM call: does each quote back up its claim? {n: {supports, why}}."""
    from _llm import create_llm
    text_pairs = "\n\n".join(f"{n}. CLAIM: {c}\n   QUOTE: {q}" for n, (c, q) in enumerate(pairs, 1))
    llm = create_llm(provider=os.getenv("LLM_PROVIDER"), model=os.getenv("LLM_MODEL"))
    msg = await llm.ainvoke(_SUPPORT_PROMPT + text_pairs)
    text = getattr(msg, "content", "") or ""
    start, end = text.find("{"), text.rfind("}")
    _RUN["counts"]["judge"] = _RUN["counts"].get("judge", 0) + 1
    return {int(r["n"]): r for r in json.loads(text[start:end + 1]).get("results", [])
            if isinstance(r, dict) and "n" in r}


async def _judge_support(claims: list[dict]) -> list[dict]:
    """Second check: does each claim's quote actually back it up?

    1. Claims whose quote is on the page are judged as they stand.
    2. Claims that fail, and claims whose quote wasn't found word for word but whose
       page the run did read, get the page's own best-matching passage, judged once
       more. A passage that backs the claim up replaces the quote.
    A claim is "verified" only when its final quote is on the page AND supports it."""
    retry: list[tuple[dict, str]] = []
    try:
        todo = [c for c in claims if c.get("on_page")]
        if todo:
            verdicts = await _ask_support([(c["claim"], c["quote"]) for c in todo])
            for n, c in enumerate(todo, 1):
                v = verdicts.get(n)
                if v is None:
                    continue
                c["supports"] = bool(v.get("supports"))
                if not c["supports"]:
                    c["verified"] = False
                    c["checked"] = ("the quote is on the page but doesn't back up the claim: "
                                    + str(v.get("why", ""))[:200])
        for c in claims:
            if c.get("verified") or not c.get("_page"):
                continue
            alt = research.best_passages(c["claim"], c["_page"])
            if alt and research._words(alt) != research._words(c.get("quote", "")):
                retry.append((c, alt))
        if retry:
            _step(f"Claim check · looking for stronger passages for {len(retry)} claim(s)")
            second = await _ask_support([(c["claim"], alt) for c, alt in retry])
            for n, (c, alt) in enumerate(retry, 1):
                if (second.get(n) or {}).get("supports"):
                    why = "was too general" if c.get("on_page") else "wasn't word for word"
                    c.update(agent_quote=c.get("quote", ""), quote=alt, supports=True, verified=True,
                             checked=f"backed up by this passage on the same page (the agent's own quote {why})")
    except Exception as exc:  # noqa: BLE001 — keep the page check's result
        log.warning("support check failed: %s", exc)
    for c in claims:
        c.pop("_page", None)
    return claims


async def _make_verifier():
    """The second agent. Its own policy store (separate file and collection), so the
    researcher's policies never fire inside it and clearing one leaves the other."""
    from cuga import CugaAgent
    from cuga.backend.cuga_graph.policy.configurable import PolicyConfigurable
    from _llm import create_llm

    policies = PolicyConfigurable()
    await policies.initialize(policy_db_path=str(_DIR / ".cuga" / "verifier_policies.db"),
                              collection_name="web_researcher_verifier")
    agent = await asyncio.to_thread(lambda: CugaAgent(
        model=create_llm(provider=os.getenv("LLM_PROVIDER"), model=os.getenv("LLM_MODEL")),
        tools=verifier.make_tools(_VCTX),
        special_instructions=verifier.VERIFIER_SYSTEM,
        cuga_folder=str(_DIR / ".cuga_verifier"),
        enable_knowledge=False,
        auto_load_policies=False,
        policy_system=policies,
    ))
    try:
        await agent.policies.clear()
        await agent.policies.add_playbook(
            name="Verify claims", content=verifier.VERIFIER_PLAYBOOK,
            keywords=["verify", "claims", "check"],
            natural_language_trigger=["Check these claims and record a verdict for each"])
        _POLICIES.append("Verifier playbook · Verify claims")
    except Exception as exc:  # noqa: BLE001
        log.warning("verifier policy skipped: %s", exc)
    return agent


async def _verify(claims: list[dict], agent) -> tuple[list[dict], object]:
    """Hand the claims to the verifier agent. Code has already checked which quotes
    are on their pages; the verifier judges support and fixes what fails. Any claim
    it leaves without a verdict falls back to the batched support check."""
    _VCTX.update(run=_RUN, claims=claims, step=_step,
                 extract=_TAVILY_RAW.get("tavily_extract"), search=_TAVILY_RAW.get("tavily_search"))
    _RUN["verdicts"] = {}
    _step(f"Verifier · checking {len(claims)} claim(s)")
    result = None
    try:
        result = await agent.invoke(verifier.brief(claims, _RUN["pages"]), thread_id=uuid.uuid4().hex)
    except Exception as exc:  # noqa: BLE001
        log.warning("verifier failed: %s", exc)
        _event("Verifier agent", "flagged", f"The verifier stopped early ({exc}); the support check covered its claims")
    claims, missing = verifier.apply_verdicts(claims, _RUN.get("verdicts", {}))
    if missing:
        _step(f"Verifier · no verdict for {len(missing)} claim(s); the support check covers them")
        sub = [claims[n - 1] for n in missing]
        await _judge_support(sub)
        for c in sub:
            c.update(by="support check", status="verified" if c.get("verified") else "not_verified")
    for c in claims:
        c.pop("_page", None)
    return claims, result


def _decisions(result) -> list[dict]:
    out = []
    for d in getattr(result, "policy_decisions", None) or []:
        row = {}
        for k in ("policy_name", "policy_type", "stage", "outcome", "tool_name", "reasoning"):
            v = d.get(k) if isinstance(d, dict) else getattr(d, k, None)
            v = getattr(v, "value", v)
            row[k] = str(v) if v is not None else None
        out.append(row)
    return out


def _blocked(policy: str) -> bool:
    return any(e["policy_name"] == policy and e["outcome"] == "blocked" for e in _RUN.get("events", []))


def _refused(result) -> str:
    """Name of a CUGA intent guard that refused this request, or ''."""
    for d in _decisions(result):
        if (d.get("policy_type") or "").lower() == "intent_guard" and "block" in (d.get("outcome") or "").lower():
            return d.get("policy_name") or "intent guard"
    return ""


def _receipt(result, started: float) -> dict:
    r = getattr(result, "receipt", None)
    out = {"tavily_calls": _RUN["counts"].get("tavily", 0), "by_tool": dict(_RUN["by_tool"]),
           "claim_checks": _RUN["counts"].get("check", 0), "support_checks": _RUN["counts"].get("judge", 0),
           "seconds": round(time.time() - started, 1), "model": os.getenv("LLM_MODEL", "")}
    if r is not None:
        out.update(tokens=getattr(r, "total_tokens", None), llm_calls=getattr(r, "llm_calls", None))
    return out


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class ResearchReq(BaseModel):
    question: str
    mode: str = "auto"                 # auto | quick | deep | site | report
    site_url: str = ""
    profile: str = "web"               # see research.SOURCE_PROFILES
    include_domains: list[str] = []
    exclude_domains: list[str] = []
    time_window: str = "any"           # any | day | week | month | year
    news: bool = False
    report_model: str = "mini"         # mini | pro (tavily_research)


class AskReq(BaseModel):
    question: str


class CredsReq(BaseModel):
    tavily_key: str = ""


class TopicAddReq(BaseModel):
    query: str
    schedule: str = "daily"   # hourly | daily | weekly


class TopicDeleteReq(BaseModel):
    id: str


class TopicToggleReq(BaseModel):
    id: str
    enabled: bool


class TopicRunReq(BaseModel):
    id: str


class VerifyReq(BaseModel):
    claim: str
    quote: str
    url: str


class FeedbackReq(BaseModel):
    report_id: str
    rating: str               # up | down
    comment: str = ""


# ---------------------------------------------------------------------------
# Web app
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn

    _init_db()
    app = FastAPI(title="Web Researcher")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    # The agent (and its policies) start on first use, so startup is instant
    # and a key saved in the UI takes effect on the next question.
    state = {"agent": None, "verifier": None}
    agent_lock = asyncio.Lock()
    sched = {"last_run": None, "next_topic": None}

    async def _get_agent():
        async with agent_lock:
            if state["agent"] is None:
                log.info("Initialising the researcher and verifier agents…")
                agent = await asyncio.to_thread(make_agent)
                _POLICIES.clear()
                await _setup_policies(agent)
                state["verifier"] = await _make_verifier()
                state["agent"] = agent
                log.info("Agents ready.")
        return state["agent"]

    async def _run(req: ResearchReq, source: str = "chat", job: Optional[dict] = None,
                   since: str = "", watch: bool = False) -> dict:
        mode, why = ("watch", "scheduled topic") if watch else research.pick_mode(
            req.question, req.mode, req.site_url)
        site_url = (req.site_url or research.first_url(req.question) or "") if mode == "site" else ""
        rules = research.source_rules(req.profile, req.include_domains, req.exclude_domains,
                                      req.time_window, req.news or watch, site_url,
                                      question="" if watch else req.question)
        report_model = req.report_model if req.report_model in ("mini", "pro") else "mini"
        agent = await _get_agent()
        if not _TAVILY_RAW:
            raise RuntimeError(f"Tavily is not available: {_STATUS['tavily']}")
        async with _RUN_LOCK:
            if job is not None:
                job["status"] = "running"
            _reset_run(mode, rules, job, report_model, since)
            started = time.time()
            _step(f"Mode · {research.MODES[mode]['title']} ({why})")
            _step(f"Sources · {rules['summary']}")
            prompt = f"{_preamble(mode, rules, site_url, since, report_model)}\n\nQuestion: {req.question}"
            result = await agent.invoke(prompt, thread_id=uuid.uuid4().hex)
            refused = _refused(result)
            if refused:
                _step(f"Refused · {refused} (CUGA intent guard)")
            if not _RUN["counts"].get("tavily") and not refused and not _blocked("Egress guard"):
                # The model sometimes answers from memory on its first turn. Retry once.
                _step("Retry · the agent answered without reading any source")
                _event("Grounding check", "applied", "First answer read no sources; asked the agent to search")
                result = await agent.invoke(
                    prompt + "\n\nImportant: answer only from what the Tavily tools return in this run. "
                    "Call them before you answer.", thread_id=uuid.uuid4().hex)
            answer = result.answer if hasattr(result, "answer") else str(result)
            clean, claims, follow = research.split_claims(answer)
            if refused:
                claims, follow = [], []
            if not claims and clean.strip() and _RUN["sources"] and not refused:
                _step("Claims · reading the claims out of the answer to check them")
                claims, follow2 = await _claims_from_prose(clean)
                follow = follow or follow2
            claims = await _check_claims(claims)        # plain code: is each quote on its page?
            on_page = sum(1 for c in claims if c.get("on_page"))
            vresult = None
            if claims:
                _step(f"Claim check · {on_page} of {len(claims)} quotes found word for word on their source pages")
                claims, vresult = await _verify(claims, state["verifier"])
            ok = sum(1 for c in claims if c.get("verified"))
            if claims:
                tally = {s: sum(1 for c in claims if c.get("status") == s) for s in verifier.STATUSES}
                _step(f"Verifier · {ok} of {len(claims)} claims verified")
                _event("Verifier agent", "applied" if ok == len(claims) else "flagged",
                       f"{ok} of {len(claims)} claims verified ({tally['revised']} with a better passage, "
                       f"{tally['softened']} narrowed, {tally['not_verified']} not verified, "
                       f"{tally['dropped']} dropped). Quotes checked in code; support judged by the verifier.")
                clean += verifier.changes_note(claims)
            if refused:
                pass                                   # the guard's response is the answer
            elif _blocked("Egress guard"):
                what = next(e["reasoning"] for e in _RUN["events"] if e["policy_name"] == "Egress guard")
                clean = ("⛔ **Blocked before it left the app.** The search contained "
                         f"{what.split(': ', 1)[-1].replace(' in the request', '')}. Secrets, personal emails "
                         "and internal names are never sent to outside services, so nothing was searched. "
                         "Rotate any exposed key and check it with your internal secret scanner.")
                claims, follow = [], []
            elif not _RUN["counts"].get("tavily"):
                clean = ("⚠ This answer read no web sources, so none of it is verified. Please ask again.\n\n"
                         + clean)
                _event("Grounding check", "blocked", "No sources were read")
            receipt = _receipt(result, started)
            vr = getattr(vresult, "receipt", None) if vresult is not None else None
            receipt["verifier"] = {"tavily_calls": _RUN["counts"].get("verifier_tavily", 0),
                                   "tokens": getattr(vr, "total_tokens", None),
                                   "llm_calls": getattr(vr, "llm_calls", None)}
            extra = {"follow_ups": follow, "request_ids": _RUN["request_ids"][:12],
                     "rules": rules["summary"], "site_url": site_url, "why": why,
                     "report_model": report_model if mode == "report" else None, "since": since or None}
            entry = _save_report(req.question, clean, source=source, mode=mode, claims=claims,
                                 sources=list(_RUN["sources"]), receipt=receipt, extra=extra)
            return {
                "report_id": entry["id"],
                "answer": clean,
                "mode": mode,
                "mode_title": research.MODES[mode]["title"],
                "why": why,
                "rules": rules["summary"],
                "claims": claims,
                "follow_ups": follow,
                "sources": list(_RUN["sources"]),
                "policy_decisions": _decisions(result) + [
                    dict(d, policy_name=f"Verifier · {d.get('policy_name')}") for d in _decisions(vresult)
                ] + list(_RUN["events"]),
                "receipt": receipt,
                "error": getattr(result, "error", None),
            }

    # Research runs as background jobs: a report or site study can take minutes,
    # longer than Code Engine's request timeout. The UI polls /jobs/{id}.
    jobs: dict[str, dict] = {}

    def _start_job(req: ResearchReq, source: str = "chat", since: str = "",
                   watch: bool = False, on_done=None) -> dict:
        now = time.time()
        for jid in [j for j, v in jobs.items() if now - v["created"] > 3600]:
            jobs.pop(jid, None)
        waiting = sum(1 for v in jobs.values() if v["status"] in ("queued", "running"))
        job = {"id": uuid.uuid4().hex[:12], "status": "queued", "question": req.question,
               "created": now, "started": now, "ahead": waiting, "steps": [],
               "result": None, "error": None}
        jobs[job["id"]] = job

        async def work():
            try:
                job["result"] = await _run(req, source, job, since, watch)
                job["status"] = "done"
                if on_done:
                    on_done(job["result"])
            except Exception as exc:  # noqa: BLE001
                log.exception("research failed")
                job.update(status="error", error=f"The research failed: {exc}")
            finally:
                job["seconds"] = round(time.time() - job["started"], 1)

        asyncio.create_task(work())
        return job

    def _public(job: dict) -> dict:
        return {k: job.get(k) for k in ("id", "status", "question", "ahead", "steps", "result",
                                        "error", "seconds")} | {
            "elapsed": round(time.time() - job["started"], 1)}

    def _since(topic: dict) -> str:
        last = topic.get("last_run")
        try:
            d = datetime.fromisoformat(last) if last else datetime.now(timezone.utc) - timedelta(days=7)
        except ValueError:
            d = datetime.now(timezone.utc) - timedelta(days=7)
        return d.date().isoformat()

    def _mark_ran(topic_id: str) -> None:
        data = _load_store()
        for t in data.get("topics", []):
            if t["id"] == topic_id:
                t["last_run"] = datetime.now(timezone.utc).isoformat()
        _save_store(data)

    async def _research_scheduler() -> None:
        """Check scheduled topics every 5 min and run the ones that are due."""
        while True:
            await asyncio.sleep(300)
            data = _load_store()
            now = datetime.now(timezone.utc)
            for topic in data.get("topics", []):
                if not topic.get("enabled", True):
                    continue
                last = topic.get("last_run")
                every = {"hourly": 3600, "daily": 86400, "weekly": 604800}.get(topic.get("schedule"), 86400)
                try:
                    due = last is None or (now - datetime.fromisoformat(last)).total_seconds() >= every
                except ValueError:
                    due = True
                if not due:
                    continue
                sched["next_topic"] = topic["query"]
                try:
                    await _run(ResearchReq(question=topic["query"]), "scheduled",
                               since=_since(topic), watch=True)
                    _mark_ran(topic["id"])
                except Exception as exc:  # noqa: BLE001
                    log.error("Scheduled research error: %s", exc)
            sched["last_run"] = now.isoformat()

    @app.on_event("startup")
    async def _startup():
        stored_key = _load_store().get("tavily_key", "")
        if stored_key and not os.getenv("TAVILY_API_KEY"):
            os.environ["TAVILY_API_KEY"] = stored_key
        asyncio.create_task(_research_scheduler())
        log.info("Research scheduler started.")

    @app.post("/research")
    async def api_research(req: ResearchReq):
        """Start a research job; poll GET /jobs/{id} for live steps and the result."""
        from _usage import track_utterance; track_utterance(req.question)
        if not req.question.strip():
            return JSONResponse({"error": "Ask a question first."}, status_code=400)
        return _public(_start_job(req))

    @app.get("/jobs/{job_id}")
    async def api_job(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            return JSONResponse({"error": "No such job (they expire after an hour)."}, status_code=404)
        return _public(job)

    @app.post("/ask")
    async def api_ask(req: AskReq):
        """Synchronous research (auto mode) — kept for scripts and tests."""
        from _usage import track_utterance; track_utterance(req.question)
        try:
            return await _run(ResearchReq(question=req.question))
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.post("/verify")
    async def api_verify(req: VerifyReq):
        """Check one claim again: read the cited page with tavily_extract (query = the
        claim) and look for the quote. No LLM involved."""
        if research.egress_violations(req.model_dump()):
            return JSONResponse({"error": "The claim contains data that can't be sent out."}, status_code=400)
        await _get_agent()
        extract = _TAVILY_RAW.get("tavily_extract")
        if not extract:
            return JSONResponse({"error": f"Tavily is not available: {_STATUS['tavily']}"}, status_code=503)
        try:
            res = await extract(urls=[req.url], query=(req.claim or req.quote)[:300], format="text")
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"error": f"Could not read the page: {exc}"}, status_code=502)
        rows = (res.get("results") if isinstance(res, dict) else None) or []
        text = "\n".join((r.get("raw_content") or "") for r in rows if isinstance(r, dict))
        if not text:
            failed = (res.get("failed_results") if isinstance(res, dict) else None) or []
            return {"verified": False, "read": False,
                    "note": (failed[0].get("error") if failed and isinstance(failed[0], dict) else None)
                            or "The page could not be read."}
        ok = research.quote_supported(req.quote, text)
        return {"verified": ok, "read": True,
                "passage": req.quote if ok else research.best_passage(req.claim, text),
                "note": "Quote found word for word on the page." if ok
                        else "Quote not found word for word; the closest passage is shown."}

    @app.post("/feedback")
    async def api_feedback(req: FeedbackReq):
        """A 👍/👎 on a report: stored, and sent to Tavily with tavily_feedback
        (which results were used and the quotes that were verified)."""
        rep = _get_report(req.report_id)
        if rep is None:
            return JSONResponse({"error": "report not found"}, status_code=404)
        if req.rating not in ("up", "down"):
            return JSONResponse({"error": "rating must be up or down"}, status_code=400)
        if req.comment and research.egress_violations({"comment": req.comment}):
            return JSONResponse({"error": "The comment contains data that can't be sent out."}, status_code=400)
        with _db() as con:
            con.execute("UPDATE research_log SET rating = ? WHERE id = ?", (req.rating, req.report_id))
        sent, note = False, "Rating saved."
        if "tavily_feedback" not in _STATUS.get("offered", []):
            # Tavily's open-source MCP server has tavily_feedback; the hosted server
            # doesn't list it yet. Send when it does — no code change needed then.
            return {"ok": True, "sent_to_tavily": False,
                    "note": "Rating saved. It will also go to Tavily once their hosted MCP server offers tavily_feedback."}
        # Feedback is scoped to one Tavily request: the run's first search if it made
        # one, otherwise its first other request (map, crawl, extract or research).
        reqs = (rep.get("extra") or {}).get("request_ids", [])
        ids = ([r["id"] for r in reqs if r.get("tool") == "tavily_search"]
               or [r["id"] for r in reqs if r.get("id")])
        if os.getenv("WR_FEEDBACK", "1") != "0" and ids:
            from _mcp_bridge import call_tool
            verified = [c for c in rep.get("claims", []) if c.get("verified")]
            payload = {
                "request_id": ids[0],
                "human_score": 1 if req.rating == "up" else 0,
                "used_urls": sorted({c["source_url"] for c in verified if c.get("source_url")})[:10],
                "used_citations": [c["quote"][:300] for c in verified if c.get("quote")][:6],
            }
            if req.comment:
                payload["comment"] = req.comment[:500]
            try:
                await asyncio.to_thread(call_tool, "tavily", "tavily_feedback", payload, 30.0)
                sent, note = True, "Rating saved and sent to Tavily."
            except Exception as exc:  # noqa: BLE001
                log.warning("tavily_feedback failed: %s", exc)
                note = "Rating saved; sending it to Tavily failed."
        return {"ok": True, "sent_to_tavily": sent, "note": note}

    @app.get("/reports")
    async def api_reports():
        return _list_reports()

    @app.get("/status")
    async def api_status():
        from _mcp_bridge import remote_mcp_configured
        return {
            "tavily": _STATUS["tavily"] if state["agent"] else
                      ("key set · loads on first question" if remote_mcp_configured("tavily")
                       else "TAVILY_API_KEY not set"),
            "policies": list(_POLICIES),
            "model": os.getenv("LLM_MODEL"),
            "modes": {k: {"title": v["title"], "tools": sorted(v["tools"]), "budget": v["budget"]}
                      for k, v in research.MODES.items()},
            "profiles": {k: v["title"] for k, v in research.SOURCE_PROFILES.items()},
            "feedback_to_tavily": os.getenv("WR_FEEDBACK", "1") != "0" and "tavily_feedback" in _STATUS.get("offered", []),
            "tavily_tools": _STATUS.get("offered", []),
            "scheduler": sched,
        }

    @app.get("/topics")
    async def api_topics():
        return _load_store().get("topics", [])

    @app.post("/topics/add")
    async def api_add_topic(req: TopicAddReq):
        data   = _load_store()
        topics = data.get("topics", [])
        topics.append({
            "id":       uuid.uuid4().hex[:8],
            "query":    req.query,
            "schedule": req.schedule,
            "enabled":  True,
            "last_run": None,
        })
        data["topics"] = topics
        _save_store(data)
        return {"ok": True}

    @app.post("/topics/delete")
    async def api_del_topic(req: TopicDeleteReq):
        data   = _load_store()
        data["topics"] = [t for t in data.get("topics", []) if t["id"] != req.id]
        _save_store(data)
        return {"ok": True}

    @app.post("/topics/toggle")
    async def api_toggle(req: TopicToggleReq):
        data = _load_store()
        for t in data.get("topics", []):
            if t["id"] == req.id:
                t["enabled"] = req.enabled
        _save_store(data)
        return {"ok": True}

    @app.post("/topics/run")
    async def api_run_topic(req: TopicRunReq):
        """Run a watch topic now: only what's new since its last run (a job)."""
        topic = next((t for t in _load_store().get("topics", []) if t["id"] == req.id), None)
        if not topic:
            return JSONResponse({"error": "Topic not found"}, status_code=404)
        job = _start_job(ResearchReq(question=topic["query"]), "manual", since=_since(topic),
                         watch=True, on_done=lambda _r: _mark_ran(topic["id"]))
        return {"ok": True, "job_id": job["id"]}

    @app.get("/settings")
    async def api_settings():
        data = _load_store()
        data.pop("tavily_key", None)
        data["tavily_configured"] = bool(os.getenv("TAVILY_API_KEY"))
        return data

    @app.post("/settings/credentials")
    async def api_creds(req: CredsReq):
        data = _load_store()
        if req.tavily_key:
            os.environ["TAVILY_API_KEY"] = req.tavily_key
            data["tavily_key"] = req.tavily_key
            state["agent"] = None          # reload Tavily's tools with the new key
        _save_store(data)
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def ui():
        return HTMLResponse(_HTML)

    # Public deployment: layered, in-memory rate limiting on POST.
    from _ratelimit import install_rate_limit
    install_rate_limit(app)
    from _usage import install_usage
    install_usage(app)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Web Researcher — web UI")
    parser.add_argument("--port",     type=int, default=28798)
    parser.add_argument("--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model",    "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    if not os.getenv("TAVILY_API_KEY"):
        print("  ⚠️  TAVILY_API_KEY not set — research needs Tavily's MCP server.\n")

    print(f"\n  Web Researcher  →  http://127.0.0.1:{args.port}\n")
    _web(args.port)
