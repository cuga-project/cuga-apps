"""
Dependency Drift Watcher — CUGA Demo App

Our code stays still. Its dependencies don't. This app watches the models and
Python packages our apps depend on, finds where the outside world has drifted
from what our code assumes, and drafts the fix for a person to approve.

  * Our side  — inline tools inventory this repo (model ids, requirements files,
                installed versions) and read real usage from usage_collector.
  * The world — Tavily's MCP server (search, extract, map, crawl, research) reads
                official sources; GitHub's MCP server reads upstream releases.
  * The rules — CUGA policies (intent guard, playbook, tool guide, output
                formatter) plus code guards on every Tavily call: no secrets or
                internal names leave, and searches stay on the pack's official
                domains. Fixes are proposals; nothing is written until a person
                approves it in the UI.

Usage:
  python main.py [--port 28843] [--provider watsonx] [--model openai/gpt-oss-120b]

Required env vars:
  LLM_PROVIDER, LLM_MODEL, AGENT_SETTING_CONFIG
  TAVILY_API_KEY          — Tavily's hosted MCP server (search, extract, map, crawl, research)

Optional env vars:
  GITHUB_TOKEN            — GitHub's MCP server: upstream release data, and PRs on approval
  DDW_GITHUB_REPO         — owner/repo that approved fixes open a draft PR against (use a fork)
  DDW_GITHUB_BASE         — base branch for those PRs (default main)
  DDW_GITHUB_PATH_PREFIX  — repo path of this checkout's root (default cuga-apps/)
  DDW_REPO_PATH           — directory to inventory (default: the cuga-apps root)
  DDW_SCAN_EVERY_HOURS    — background scan of every pack (default 0 = off)
  DDW_INTERNAL_TERMS      — extra comma-separated words the egress guard blocks
  USAGE_COLLECTOR_URL, USAGE_DASHBOARD_TOKEN — read real usage per app
"""

import argparse
import asyncio
import difflib
import functools
import json
import logging
import os
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Path bootstrap — must come before local imports
# ---------------------------------------------------------------------------
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

# This app's CUGA policies live in their own store. The default store is shared
# by every app in the process's filesystem, and in the all-in-one image another
# app clearing it on startup would wipe these policies. Set before cuga is
# imported (Dynaconf reads the env once). Also turn on CUGA's run receipt so the
# UI can show tokens, LLM calls and timing for each answer.
(_DIR / ".cuga").mkdir(exist_ok=True)
os.environ.setdefault("DYNACONF_POLICY__POLICY_DB_PATH", str(_DIR / ".cuga" / "policies.db"))
os.environ.setdefault("DYNACONF_ADVANCED_FEATURES__RUN_RECEIPT", "true")

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
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import drift
from ui import _HTML

PACKS = drift.load_packs()
DEFAULT_PACK = "models"

TAVILY_TOOLS = {"tavily_search", "tavily_extract", "tavily_crawl", "tavily_map", "tavily_research"}
# Read-only GitHub tools the agent may call. Writes (branch, file, PR) are made
# by this app, and only after a person approves a proposal.
GITHUB_READ_TOOLS = {"get_latest_release", "list_releases", "list_tags", "get_file_contents"}

_STATUS: dict = {"tavily": "not loaded", "github": "not loaded"}
_POLICIES: list[str] = []


# ---------------------------------------------------------------------------
# Store — findings, fix proposals, decisions
# ---------------------------------------------------------------------------

_DB_PATH = _DIR / "drift.db"


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS findings (
            id TEXT PRIMARY KEY, pack TEXT, dependency TEXT, kind TEXT, severity TEXT,
            summary TEXT, quote TEXT, source_url TEXT, effective_date TEXT,
            locations TEXT, recommendation TEXT, status TEXT DEFAULT 'open',
            note TEXT DEFAULT '', created_at TEXT, updated_at TEXT,
            UNIQUE(pack, dependency, kind)
        );
        CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY, title TEXT, rationale TEXT, file_path TEXT,
            find_text TEXT, replace_text TEXT, evidence_url TEXT, diff TEXT,
            status TEXT DEFAULT 'pending', pr_url TEXT DEFAULT '', note TEXT DEFAULT '',
            created_at TEXT, decided_at TEXT
        );
    """)
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _save_findings(pack: str, findings: list[dict]) -> None:
    now = _now()
    with _db() as con:
        for f in findings:
            pk = f.get("pack") or pack
            con.execute("""
                INSERT INTO findings (id, pack, dependency, kind, severity, summary, quote,
                    source_url, effective_date, locations, recommendation, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(pack, dependency, kind) DO UPDATE SET
                    severity=excluded.severity, summary=excluded.summary, quote=excluded.quote,
                    source_url=excluded.source_url, effective_date=excluded.effective_date,
                    locations=excluded.locations, recommendation=excluded.recommendation,
                    updated_at=excluded.updated_at
            """, (uuid.uuid4().hex[:10], pk, f["dependency"], f["kind"], f["severity"],
                  f["summary"], f["quote"], f["source_url"], f.get("effective_date"),
                  json.dumps(f["locations"]), f["recommendation"], now, now))


def _list_findings(pack: Optional[str] = None) -> list[dict]:
    q, args = "SELECT * FROM findings", []
    if pack:
        q, args = q + " WHERE pack = ?", [pack]
    order = " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'review' THEN 1 WHEN 'fyi' THEN 2 ELSE 3 END, updated_at DESC"
    with _db() as con:
        rows = [dict(r) for r in con.execute(q + order, args)]
    for r in rows:
        r["locations"] = json.loads(r["locations"] or "[]")
    return rows


def _list_proposals() -> list[dict]:
    with _db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM proposals ORDER BY created_at DESC LIMIT 50")]


# ---------------------------------------------------------------------------
# Run context — one agent run at a time, so guards can report what they did
# ---------------------------------------------------------------------------

_RUN_LOCK = asyncio.Lock()
_RUN: dict = {"pack": DEFAULT_PACK, "events": [], "sources": [], "counts": {}, "proposals": []}


def _reset_run(pack: str) -> None:
    _RUN.update(pack=pack, events=[], sources=[], counts={}, proposals=[])


def _event(policy: str, outcome: str, detail: str) -> None:
    _RUN["events"].append({"policy_name": policy, "policy_type": "app_guard",
                           "outcome": outcome, "reasoning": detail})


def _count(kind: str) -> None:
    _RUN["counts"][kind] = _RUN["counts"].get(kind, 0) + 1


def _add_sources(result) -> None:
    for url in drift.urls_in(result):
        if url not in _RUN["sources"] and len(_RUN["sources"]) < 25:
            _RUN["sources"].append(url)


def _guard_tavily(tool):
    """Wrap a Tavily tool: egress guard, official-domain guard, source capture."""
    original = tool.coroutine
    name = tool.name

    @functools.wraps(original)
    async def guarded(*args, **kwargs):
        pack = PACKS.get(_RUN["pack"], {})
        reasons = drift.egress_violations(kwargs)
        if reasons:
            _event("Egress guard", "blocked", f"{name}: {', '.join(reasons)} in the request")
            return (f"BLOCKED by egress guard: the request contained {', '.join(reasons)}. "
                    "Company secrets and internal names never go to outside services. "
                    "Do not retry with the same data; tell the user what was blocked and why.")
        domains = pack.get("domains") or []
        if name == "tavily_search" and domains and not kwargs.get("include_domains"):
            kwargs["include_domains"] = list(domains)
            _event("Official sources only", "applied",
                   f"tavily_search limited to the {pack.get('title', '')} pack's {len(domains)} domains")
        bad = drift.domain_violation(name, kwargs, domains)
        if bad:
            _event("Official sources only", "blocked", f"{name}: {bad}")
            return (f"BLOCKED by tool guide: {bad}. Use only official sources for this pack: "
                    f"{', '.join(domains)}.")
        _count("tavily")
        result = await original(*args, **kwargs)
        _add_sources(result)
        return result

    tool.coroutine = guarded
    return tool


def _count_github(tool):
    original = tool.coroutine

    @functools.wraps(original)
    async def counted(*args, **kwargs):
        _count("github")
        return await original(*args, **kwargs)

    tool.coroutine = counted
    return tool


# ---------------------------------------------------------------------------
# Inline tools — our side of the gap, and the proposal queue
# ---------------------------------------------------------------------------

def _make_local_tools():
    from langchain_core.tools import tool

    @tool
    def inventory_models() -> dict:
        """List every LLM model id referenced in this repo's code and config.

        Returns {repo_root, in_use_now: {provider, model}, models: [{model, provider,
        locations: ["path:line", ...], apps: [...], shared: bool}], note}.
        shared=true means a shared default every app can fall back to.
        """
        _count("internal")
        return drift.inventory_models()

    @tool
    def inventory_packages(only: Optional[list[str]] = None) -> dict:
        """List the Python packages in this repo's requirements*.txt files.

        Args:
            only: optional package names to limit the result to (e.g. the pack's watch list).

        Returns {requirements_files, unpinned, packages: [{package, specs, pinned,
        installed, files, file_count}]}. `installed` is the version in the running
        environment, i.e. what is actually deployed; None if not installed here.
        """
        _count("internal")
        return drift.inventory_packages(only=only)

    @tool
    def get_usage() -> dict:
        """Real usage from the usage collector: requests per app and calls per provider.

        Returns {available, apps: [...], providers: [...]} or {available: false, reason}.
        Use it to rank impact: a change to a heavily used app matters more.
        """
        _count("internal")
        return _usage_stats()

    @tool
    def get_watch_pack() -> dict:
        """The active watch pack: official source domains, seed pages, crawl
        instructions, severity rules and (for packages) the watch list with GitHub repos."""
        return PACKS.get(_RUN["pack"], {})

    @tool
    def list_accepted_risks() -> list:
        """Findings a person has marked as accepted risk. Do not raise these as new alerts."""
        return [{"pack": f["pack"], "dependency": f["dependency"], "kind": f["kind"], "note": f["note"]}
                for f in _list_findings() if f["status"] == "accepted"]

    @tool
    def propose_fix(title: str, rationale: str, file_path: str, find: str,
                    replace: str, evidence_url: str) -> dict:
        """Queue a one-line fix for a person to approve. This does NOT change anything.

        Args:
            title: short pull-request title, e.g. "Replace llama-3-3-70b-instruct before withdrawal".
            rationale: one or two sentences: what drifted, quoting the source.
            file_path: repo-relative path from inventory results, e.g. "apps/_llm.py".
            find: exact text currently in the file (copy it from the file, one line is best).
            replace: the replacement text.
            evidence_url: the official URL that proves the change.

        Returns {id, status: "pending", diff} or {error}. After calling it, tell the
        user the fix is waiting for approval in the panel. Never say it was applied.
        """
        _count("internal")
        return _create_proposal(title, rationale, file_path, find, replace, evidence_url)

    return [inventory_models, inventory_packages, get_usage, get_watch_pack,
            list_accepted_risks, propose_fix]


def _usage_stats() -> dict:
    import httpx
    track = os.getenv("USAGE_COLLECTOR_URL", "")
    if not track:
        return {"available": False, "reason": "USAGE_COLLECTOR_URL is not set"}
    url = re.sub(r"/track/?$", "", track) + "/api/stats"
    params = {"token": os.environ["USAGE_DASHBOARD_TOKEN"]} if os.getenv("USAGE_DASHBOARD_TOKEN") else {}
    try:
        data = httpx.get(url, params=params, timeout=8).json()
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"usage collector unreachable: {exc}"}
    keep_app = ("app", "requests_total", "requests_today", "calls_total", "calls_today")
    keep_prov = ("provider", "calls_total", "calls_today", "errors_total")
    return {
        "available": True,
        "apps": [{k: a.get(k) for k in keep_app if k in a} for a in data.get("apps", [])][:60],
        "providers": [{k: p.get(k) for k in keep_prov if k in p} for p in data.get("providers", [])],
    }


def _create_proposal(title, rationale, file_path, find, replace, evidence_url) -> dict:
    rel = file_path.strip().lstrip("/")
    path = (drift.REPO_ROOT / rel).resolve()
    if drift.REPO_ROOT not in path.parents or not path.is_file():
        return {"error": f"{file_path} is not a file in the repo; use a path from the inventory"}
    text = path.read_text(errors="ignore")
    if not find or find not in text:
        return {"error": "the `find` text is not in the file; copy it exactly from the file"}
    if find == replace:
        return {"error": "`replace` is the same as `find`"}
    new = text.replace(find, replace, 1)
    diff = "".join(difflib.unified_diff(
        text.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{rel}", tofile=f"b/{rel}", n=1))
    pid = uuid.uuid4().hex[:8]
    with _db() as con:
        con.execute("""INSERT INTO proposals (id, title, rationale, file_path, find_text,
            replace_text, evidence_url, diff, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (pid, title, rationale, rel, find, replace, evidence_url, diff, _now()))
    _RUN["proposals"].append(pid)
    return {"id": pid, "status": "pending", "diff": diff}


# ---------------------------------------------------------------------------
# Applying an approved proposal — GitHub MCP, called by the app, not the agent
# ---------------------------------------------------------------------------

async def _github_call(tool: str, args: dict) -> tuple[str, list[str]]:
    """Call a GitHub MCP tool; return (text blocks, resource texts)."""
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from _mcp_bridge import server_endpoint

    url, headers = server_endpoint("github")
    async with streamablehttp_client(url, headers=headers) as (read, write, _close):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(tool, args)
    texts, resources = [], []
    for block in res.content or []:
        if getattr(block, "type", "") == "text":
            texts.append(block.text)
        elif getattr(block, "resource", None) is not None:
            resources.append(getattr(block.resource, "text", "") or "")
    if res.isError:
        raise RuntimeError(f"GitHub {tool} failed: {' '.join(texts)[:300]}")
    return "\n".join(texts), resources


async def _apply_on_github(p: dict) -> str:
    owner, repo = os.environ["DDW_GITHUB_REPO"].split("/", 1)
    base = os.getenv("DDW_GITHUB_BASE", "main")
    path = os.getenv("DDW_GITHUB_PATH_PREFIX", "cuga-apps/") + p["file_path"]
    text, resources = await _github_call("get_file_contents",
                                         {"owner": owner, "repo": repo, "path": path, "ref": base})
    sha = re.search(r"SHA:\s*([0-9a-f]{40})", text)
    if not resources or not sha:
        raise RuntimeError(f"could not read {path} on {owner}/{repo}@{base}")
    content = resources[0]
    if p["find_text"] not in content:
        raise RuntimeError(f"{path} on {base} no longer contains the text to replace")
    branch = f"drift-watcher/{p['id']}"
    await _github_call("create_branch", {"owner": owner, "repo": repo, "branch": branch, "from_branch": base})
    await _github_call("create_or_update_file", {
        "owner": owner, "repo": repo, "path": path, "branch": branch, "sha": sha.group(1),
        "content": content.replace(p["find_text"], p["replace_text"], 1),
        "message": p["title"],
    })
    body = (f"{p['rationale']}\n\nEvidence: {p['evidence_url']}\n\n"
            "Drafted by Dependency Drift Watcher (CUGA + Tavily) and approved by a person.")
    pr_text, _ = await _github_call("create_pull_request", {
        "owner": owner, "repo": repo, "title": p["title"], "body": body,
        "head": branch, "base": base, "draft": True,
    })
    pr_urls = [u for u in drift.urls_in(pr_text) if "/pull/" in u]
    return pr_urls[0] if pr_urls else f"https://github.com/{owner}/{repo}/tree/{branch}"


# ---------------------------------------------------------------------------
# System prompt + policies
# ---------------------------------------------------------------------------

_SYSTEM = """\
# Dependency Drift Watcher

You find drift: places where the outside world has changed but our code still
assumes the old state. Each request names an active watch pack (Models or Packages).

## Workflow
1. Inventory our side first: inventory_models or inventory_packages (use the pack's
   watch list for packages). Call get_usage when ranking impact.
2. Read the world's side from official sources only, with the Tavily tools:
   - tavily_search for recent notices (set include_domains to the pack's domains),
   - tavily_map / tavily_crawl on the pack's seed pages to find lifecycle, pricing or
     release pages,
   - tavily_extract with a `query` to pull the exact sentence that proves a change,
   - tavily_research only when the user asks for a comparison of replacements.
   For packages, GitHub tools (get_latest_release, list_releases) give upstream versions.
3. Compare: does the change affect a model or package we actually use? Where (file:line)?
4. Skip anything in list_accepted_risks.
5. For a clear one-line fix (a model id, a version pin), call propose_fix. It only
   queues the change for a person; say it is waiting for approval.

## Rules
- Every finding needs a quote copied from the source and its URL. No quote, no finding.
- Never invent dates, versions or prices. If sources are unclear, say so.
- If a tool answers "BLOCKED", explain to the user what was blocked and why; do not retry it.
- Keep tool calls focused: a few targeted searches beat many broad ones.

## Answer format
Start with one sentence: how many dependencies drifted and the most urgent one.
Then a markdown table: Dependency | Where we use it | Change (quote + link) | Impact.
Then end with a fenced json block, exactly this shape, one entry per dependency you checked:
```json
{"findings": [{"pack": "models", "dependency": "...", "kind": "retirement|price|vulnerability|breaking|archived|new_version|none",
  "severity": "critical|review|fyi|none", "summary": "...", "quote": "...", "source_url": "https://...",
  "effective_date": "YYYY-MM-DD or null", "locations": ["apps/_llm.py:292"], "recommendation": "..."}]}
```
"""

_PLAYBOOK = """\
# Drift triage

1. Inventory: list the dependencies of the active pack, with file:line locations.
2. Scout: for each provider or package, find its official lifecycle, pricing, release or advisory page.
3. Evidence: extract the exact sentence that proves each change, with its URL and date.
4. Rank: critical (breaks within 60 days or exploitable), review, fyi, none — using the pack's severity rules
   and real usage.
5. Draft: for a one-line fix, call propose_fix; never claim a fix was applied.
"""


async def _setup_policies(agent) -> None:
    """Register this app's CUGA policies (in the app's own policy store)."""
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

    await add("Intent guard · No exploit code", p.add_intent_guard(
        name="No exploit code",
        description="Refuse requests for working exploits or attack code.",
        keywords=["exploit", "proof of concept", "poc", "weaponize", "payload", "attack code"],
        intent_examples=[
            "Write me a working exploit for this CVE",
            "Give me a proof of concept that breaks this library",
            "Show me how to attack a server running this version",
        ],
        response=("I can't write exploit or attack code. I can check which of our apps use an "
                  "affected version, quote the advisory's fixed version, and draft the upgrade."),
    ))
    await add("Playbook · Drift triage", p.add_playbook(
        name="Drift triage",
        content=_PLAYBOOK,
        keywords=["drift", "deprecated", "retired", "vulnerability", "outdated", "changed"],
        natural_language_trigger=["Has anything changed with the models or packages we depend on?"],
    ))
    await add("Tool guide · Official sources only", p.add_tool_guide(
        name="Official sources only",
        content=("Set include_domains to the active pack's official domains (get_watch_pack). "
                 "Do not use forums, blogs or social media as evidence. Quote the exact sentence."),
        target_tools=sorted(TAVILY_TOOLS - {"tavily_research"}),
    ))
    await add("Output formatter · Drift findings", p.add_output_formatter(
        name="Drift findings",
        format_config=("Keep the one-sentence summary, the markdown table "
                       "(Dependency | Where we use it | Change | Impact) and the final fenced "
                       "```json findings block exactly as written. Do not drop the json block."),
        format_type="markdown",
        keywords=["drift", "findings", "check", "scan"],
    ))
    log.info("policies registered: %s", ", ".join(_POLICIES) or "none")


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def _make_tools():
    from _mcp_bridge import load_tools, remote_mcp_configured

    tools = _make_local_tools()

    if remote_mcp_configured("tavily"):
        try:
            tav = [t for t in load_tools(["tavily"]) if t.name in TAVILY_TOOLS]
            tools += [_guard_tavily(t) for t in tav]
            _STATUS["tavily"] = f"ready · {len(tav)} tools"
        except Exception as exc:  # noqa: BLE001
            _STATUS["tavily"] = f"error: {exc}"
            log.exception("Tavily MCP failed to load")
    else:
        _STATUS["tavily"] = "TAVILY_API_KEY not set"

    if remote_mcp_configured("github"):
        try:
            gh = [t for t in load_tools(["github"]) if t.name in GITHUB_READ_TOOLS]
            tools += [_count_github(t) for t in gh]
            _STATUS["github"] = f"ready · {len(gh)} read tools"
        except Exception as exc:  # noqa: BLE001
            _STATUS["github"] = f"error: {exc}"
            log.exception("GitHub MCP failed to load")
    else:
        _STATUS["github"] = "GITHUB_TOKEN not set (optional)"

    return tools


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
        # Each check is independent — no persistent knowledge store, and the
        # policies are registered in code (below), not auto-loaded from disk.
        enable_knowledge=False,
        auto_load_policies=False,
    )


def _pack_preamble(pack_id: str) -> str:
    p = PACKS[pack_id]
    lines = [
        f"[Active watch pack: {p['title']}] {p['summary']}",
        f"Official source domains (Tavily calls are limited to these): {', '.join(p['domains'])}",
        f"Seed pages for tavily_map / tavily_crawl: {', '.join(p.get('seeds', []))}",
        f"Crawl instructions: {p.get('crawl_instructions', '')}",
        f"Search time_range: {p.get('time_range', 'month')}",
        "Severity rules: " + "; ".join(f"{k}: {v}" for k, v in p.get("severity", {}).items()),
    ]
    if p.get("watch"):
        lines.append("Watch list (package → GitHub repo): "
                     + ", ".join(f"{w['package']} → {w['repo']}" for w in p["watch"]))
    return "\n".join(lines)


_SCAN_QUESTIONS = {
    "models": ("Run a full Models drift check: inventory our models, check each provider's "
               "official lifecycle and pricing sources, and report what drifted."),
    "packages": ("Run a Packages drift check on the watch list: compare installed versions with "
                 "the latest releases, and look for advisories, archived repos and pins that "
                 "block upgrades."),
}


def _decisions(result) -> list[dict]:
    out = []
    for d in getattr(result, "policy_decisions", None) or []:
        row = {}
        for k in ("policy_name", "policy_type", "stage", "outcome", "tool_name", "reasoning"):
            v = d.get(k) if isinstance(d, dict) else getattr(d, k, None)
            v = getattr(v, "value", v)          # enums → their plain value
            row[k] = str(v) if v is not None else None
        out.append(row)
    return out


def _receipt(result, started: float) -> dict:
    r = getattr(result, "receipt", None)
    out = {
        "tavily_calls": _RUN["counts"].get("tavily", 0),
        "github_calls": _RUN["counts"].get("github", 0),
        "internal_calls": _RUN["counts"].get("internal", 0),
        "seconds": round(time.time() - started, 1),
        "model": os.getenv("LLM_MODEL", ""),
    }
    if r is not None:
        out.update(tokens=getattr(r, "total_tokens", None), llm_calls=getattr(r, "llm_calls", None))
    return out


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str
    pack: str = DEFAULT_PACK


class ScanRequest(BaseModel):
    pack: str = DEFAULT_PACK


class DecisionRequest(BaseModel):
    finding_id: str
    decision: str          # accepted | open | resolved
    note: str = ""


def _web(port: int):
    import uvicorn

    app = FastAPI(title="Dependency Drift Watcher", version="1.0.0")

    # Lazy-initialise the agent (and its policies) on first use so startup is instant.
    _agent = None
    _agent_lock = asyncio.Lock()
    _sched = {"last_scan": None, "every_hours": float(os.getenv("DDW_SCAN_EVERY_HOURS", "0") or 0)}

    async def _get_agent():
        nonlocal _agent
        async with _agent_lock:
            if _agent is None:
                log.info("Initialising CugaAgent…")
                agent = await asyncio.to_thread(make_agent)
                await _setup_policies(agent)
                _agent = agent
                log.info("CugaAgent ready.")
        return _agent

    async def _run(question: str, pack: str) -> dict:
        if pack not in PACKS:
            pack = DEFAULT_PACK
        agent = await _get_agent()
        async with _RUN_LOCK:
            _reset_run(pack)
            started = time.time()
            result = await agent.invoke(f"{_pack_preamble(pack)}\n\n{question}",
                                        thread_id=uuid.uuid4().hex)
            answer = result.answer if hasattr(result, "answer") else str(result)
            clean, findings = drift.split_findings(answer)
            if findings:
                _save_findings(pack, findings)
            return {
                "answer": clean,
                "pack": pack,
                "findings": findings,
                "proposals": list(_RUN["proposals"]),
                "policy_decisions": _decisions(result) + list(_RUN["events"]),
                "sources": list(_RUN["sources"]),
                "receipt": _receipt(result, started),
                "error": getattr(result, "error", None),
            }

    async def _scheduler() -> None:
        every = _sched["every_hours"]
        while True:
            await asyncio.sleep(every * 3600)
            for pack in PACKS:
                try:
                    await _run(_SCAN_QUESTIONS.get(pack, "Run a drift check."), pack)
                except Exception:  # noqa: BLE001
                    log.exception("scheduled scan failed for %s", pack)
            _sched["last_scan"] = _now()

    @app.on_event("startup")
    async def _startup():
        if _sched["every_hours"] > 0:
            asyncio.create_task(_scheduler())
            log.info("Background scan every %s h", _sched["every_hours"])

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/status")
    async def status():
        from _mcp_bridge import remote_mcp_configured
        return {
            "tavily": _STATUS["tavily"] if _agent else
                      ("key set · loads on first question" if remote_mcp_configured("tavily")
                       else "TAVILY_API_KEY not set"),
            "github": _STATUS["github"] if _agent else
                      ("token set · loads on first question" if remote_mcp_configured("github")
                       else "GITHUB_TOKEN not set (optional)"),
            "pr_target": os.getenv("DDW_GITHUB_REPO") or None,
            "policies": list(_POLICIES),
            "model": os.getenv("LLM_MODEL"),
            "repo_root": str(drift.REPO_ROOT),
            "scan_every_hours": _sched["every_hours"],
            "last_scan": _sched["last_scan"],
        }

    @app.get("/packs")
    async def packs():
        return [{"id": p["id"], "title": p["title"], "summary": p["summary"],
                 "domains": p["domains"], "examples": p.get("examples", [])} for p in PACKS.values()]

    @app.post("/ask")
    async def ask(req: AskRequest):
        from _usage import track_utterance; track_utterance(req.question)
        try:
            return await _run(req.question, req.pack)
        except Exception as exc:
            log.exception("Agent invocation failed")
            return JSONResponse(status_code=500, content={"answer": f"Error: {exc}"})

    @app.post("/scan")
    async def scan(req: ScanRequest):
        try:
            out = await _run(_SCAN_QUESTIONS.get(req.pack, "Run a drift check."), req.pack)
            _sched["last_scan"] = _now()
            return out
        except Exception as exc:
            log.exception("Scan failed")
            return JSONResponse(status_code=500, content={"answer": f"Error: {exc}"})

    @app.get("/findings")
    async def findings(pack: Optional[str] = None):
        return _list_findings(pack)

    @app.post("/decisions")
    async def decisions(req: DecisionRequest):
        if req.decision not in ("accepted", "open", "resolved"):
            return JSONResponse(status_code=400, content={"error": "decision must be accepted, open or resolved"})
        with _db() as con:
            cur = con.execute("UPDATE findings SET status = ?, note = ?, updated_at = ? WHERE id = ?",
                              (req.decision, req.note, _now(), req.finding_id))
        if cur.rowcount == 0:
            return JSONResponse(status_code=404, content={"error": "finding not found"})
        return {"ok": True}

    @app.get("/proposals")
    async def proposals():
        return _list_proposals()

    @app.post("/proposals/{pid}/{action}")
    async def decide_proposal(pid: str, action: str):
        if action not in ("approve", "reject"):
            return JSONResponse(status_code=400, content={"error": "action must be approve or reject"})
        with _db() as con:
            row = con.execute("SELECT * FROM proposals WHERE id = ?", (pid,)).fetchone()
        if row is None:
            return JSONResponse(status_code=404, content={"error": "proposal not found"})
        p = dict(row)
        if p["status"] != "pending":
            return JSONResponse(status_code=409, content={"error": f"proposal is already {p['status']}"})
        status, pr_url, note = "rejected", "", "Rejected. Nothing changed."
        if action == "approve":
            from _mcp_bridge import remote_mcp_configured
            if remote_mcp_configured("github") and os.getenv("DDW_GITHUB_REPO"):
                try:
                    pr_url = await _apply_on_github(p)
                    status, note = "approved", "Draft pull request opened."
                except Exception as exc:  # noqa: BLE001
                    log.exception("GitHub apply failed")
                    status, note = "failed", f"GitHub step failed: {exc}"
            else:
                status = "approved"
                note = ("Approved. GitHub is not configured (GITHUB_TOKEN + DDW_GITHUB_REPO), "
                        "so nothing was pushed: apply the diff locally.")
        with _db() as con:
            con.execute("UPDATE proposals SET status = ?, pr_url = ?, note = ?, decided_at = ? WHERE id = ?",
                        (status, pr_url, note, _now(), pid))
        return {"id": pid, "status": status, "pr_url": pr_url, "note": note, "diff": p["diff"]}

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
    parser = argparse.ArgumentParser(description="Dependency Drift Watcher — CUGA demo app")
    parser.add_argument("--port", type=int, default=28843)
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

    print(f"\n  Dependency Drift Watcher  →  http://127.0.0.1:{args.port}\n")
    _web(args.port)
