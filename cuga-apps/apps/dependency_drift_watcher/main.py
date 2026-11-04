"""
Dependency Drift Watcher — CUGA Demo App

Our code stays still. Its dependencies don't. Point this app at any public
GitHub repo: it inventories the models and Python packages the repo depends on,
finds where the outside world has drifted from what the code assumes, and
suggests the fix.

  * Our side  — the repo is downloaded as a public snapshot (no token) and
                inventoried by inline tools: model ids with file:line, and
                package specs from requirements*.txt and pyproject.toml.
  * The world — PyPI's public JSON API gives each package's latest release and
                whether our version spec still admits it; Tavily's MCP server
                (search, extract, map, crawl, research) reads official sources
                for what changed and why.
  * The rules — CUGA policies (intent guard, playbook, tool guide, output
                formatter) plus code guards on every Tavily call: no secrets or
                internal names leave, and searches stay on the pack's official
                domains. Fixes are suggestions to copy; the app never writes to
                any repository.

Usage:
  python main.py [--port 28843] [--provider watsonx] [--model openai/gpt-oss-120b]

Required env vars:
  LLM_PROVIDER, LLM_MODEL, AGENT_SETTING_CONFIG
  TAVILY_API_KEY          — Tavily's hosted MCP server (search, extract, map, crawl, research)

Optional env vars:
  DDW_DEFAULT_REPO        — repo scanned when none is given (default cuga-project/cuga-apps)
  DDW_REPO_MAX_MB         — refuse repos whose download is larger (default 60)
  DDW_SCAN_EVERY_HOURS    — background scan of the default repo, every pack (default 0 = off)
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

_STATUS: dict = {"tavily": "not loaded"}
_POLICIES: list[str] = []


# ---------------------------------------------------------------------------
# Store — findings (per repo), suggested fixes, decisions
# ---------------------------------------------------------------------------

_DB_PATH = _DIR / "drift.db"


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    cols = {r[1] for r in con.execute("PRAGMA table_info(findings)")}
    if cols and "repo" not in cols:
        # Store from before findings were per repo: start over (local data only).
        con.executescript("DROP TABLE IF EXISTS findings; DROP TABLE IF EXISTS proposals;")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS findings (
            id TEXT PRIMARY KEY, repo TEXT, pack TEXT, dependency TEXT, kind TEXT, severity TEXT,
            summary TEXT, quote TEXT, source_url TEXT, effective_date TEXT,
            locations TEXT, recommendation TEXT, status TEXT DEFAULT 'open',
            note TEXT DEFAULT '', created_at TEXT, updated_at TEXT,
            UNIQUE(repo, pack, dependency, kind)
        );
        CREATE TABLE IF NOT EXISTS suggestions (
            id TEXT PRIMARY KEY, repo TEXT, title TEXT, rationale TEXT, file_path TEXT,
            evidence_url TEXT, diff TEXT, created_at TEXT
        );
    """)
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _save_findings(repo: str, pack: str, findings: list[dict]) -> None:
    now = _now()
    with _db() as con:
        for f in findings:
            pk = f.get("pack") or pack
            con.execute("""
                INSERT INTO findings (id, repo, pack, dependency, kind, severity, summary, quote,
                    source_url, effective_date, locations, recommendation, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(repo, pack, dependency, kind) DO UPDATE SET
                    severity=excluded.severity, summary=excluded.summary, quote=excluded.quote,
                    source_url=excluded.source_url, effective_date=excluded.effective_date,
                    locations=excluded.locations, recommendation=excluded.recommendation,
                    updated_at=excluded.updated_at
            """, (uuid.uuid4().hex[:10], repo, pk, f["dependency"], f["kind"], f["severity"],
                  f["summary"], f["quote"], f["source_url"], f.get("effective_date"),
                  json.dumps(f["locations"]), f["recommendation"], now, now))


def _list_findings(repo: Optional[str] = None, pack: Optional[str] = None) -> list[dict]:
    q, where, args = "SELECT * FROM findings", [], []
    if repo:
        where.append("repo = ?"); args.append(repo)
    if pack:
        where.append("pack = ?"); args.append(pack)
    if where:
        q += " WHERE " + " AND ".join(where)
    order = " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'review' THEN 1 WHEN 'fyi' THEN 2 ELSE 3 END, updated_at DESC"
    with _db() as con:
        rows = [dict(r) for r in con.execute(q + order, args)]
    for r in rows:
        r["locations"] = json.loads(r["locations"] or "[]")
    return rows


def _list_suggestions(repo: Optional[str] = None) -> list[dict]:
    q, args = "SELECT * FROM suggestions", []
    if repo:
        q, args = q + " WHERE repo = ?", [repo]
    with _db() as con:
        return [dict(r) for r in con.execute(q + " ORDER BY created_at DESC LIMIT 50", args)]


# ---------------------------------------------------------------------------
# Run context — one agent run at a time, so guards can report what they did
# ---------------------------------------------------------------------------

_RUN_LOCK = asyncio.Lock()
_RUN: dict = {"pack": DEFAULT_PACK, "repo": drift.DEFAULT_REPO, "root": None,
              "events": [], "sources": [], "counts": {}, "suggestions": []}


def _reset_run(pack: str, snapshot: dict, job: Optional[dict] = None) -> None:
    _RUN.update(pack=pack, repo=snapshot["repo"], root=Path(snapshot["root"]),
                events=[], sources=[], counts={}, suggestions=[], job=job, pypi_checked=[],
                pypi_rows=[])


def _event(policy: str, outcome: str, detail: str) -> None:
    _RUN["events"].append({"policy_name": policy, "policy_type": "app_guard",
                           "outcome": outcome, "reasoning": detail})


def _count(kind: str) -> None:
    _RUN["counts"][kind] = _RUN["counts"].get(kind, 0) + 1


def _step(text: str) -> None:
    """A line of live progress for the job the UI is polling."""
    job = _RUN.get("job")
    if job is not None:
        job["steps"].append({"t": round(time.time() - job["started"], 1), "text": text[:160]})


def _target(name: str, kwargs: dict) -> str:
    if name == "tavily_search":
        return f'"{kwargs.get("query", "")}"'
    if name == "tavily_extract":
        urls = kwargs.get("urls") or []
        return ", ".join(drift._host(u) for u in urls[:3]) + (f" +{len(urls) - 3}" if len(urls) > 3 else "")
    return drift._host(kwargs.get("url") or "")


def _add_sources(result) -> None:
    """Record the pages a Tavily call returned (its results' URLs, not every URL in
    the payload — the hosted server's JSON also carries links to its own docs)."""
    urls: list[str] = []
    if isinstance(result, dict):
        for key in ("results", "failed_results"):
            for r in result.get(key) or []:
                if isinstance(r, dict) and r.get("url"):
                    urls.append(r["url"])
                elif isinstance(r, str) and r.startswith("http"):     # tavily_map returns plain URLs
                    urls.append(r)
        if not urls and result.get("base_url"):
            urls.append(result["base_url"])
    else:
        urls = drift.urls_in(result)
    for url in urls:
        if "docs.tavily.com" in url:
            continue
        if url not in _RUN["sources"] and len(_RUN["sources"]) < 25:
            _RUN["sources"].append(url)


# Budgets that keep one check inside a few minutes. Tavily's crawl defaults to
# 50 pages and follows external links; whole pages then flood the model's
# context and every later LLM call slows down. Capped here, not just asked for.
_CRAWL_LIMITS = {"limit": 8, "max_depth": 1, "max_breadth": 10}
_MAP_LIMITS = {"limit": 30, "max_depth": 1, "max_breadth": 20}
_PAGE_CHARS = {"tavily_crawl": 3000, "tavily_extract": 6000, "tavily_search": 1500}


def _clamp(name: str, kwargs: dict) -> None:
    """Cap crawl/map size and keep them on the starting site."""
    limits = _CRAWL_LIMITS if name == "tavily_crawl" else _MAP_LIMITS if name == "tavily_map" else None
    if not limits:
        return
    for key, cap in limits.items():
        try:
            kwargs[key] = min(int(kwargs.get(key) or cap), cap)
        except (TypeError, ValueError):
            kwargs[key] = cap
    kwargs["allow_external"] = False
    if name == "tavily_crawl" and kwargs.get("instructions"):
        kwargs.setdefault("chunks_per_source", 3)      # only the relevant parts of each page


def _trim(name: str, result):
    """Shorten page text in a Tavily result before the model reads it."""
    cap = _PAGE_CHARS.get(name)
    if not cap or not isinstance(result, dict):
        return result
    for r in result.get("results") or []:
        if isinstance(r, dict):
            for key in ("raw_content", "content"):
                text = r.get(key)
                if isinstance(text, str) and len(text) > cap:
                    r[key] = text[:cap] + f"\n…[trimmed {len(text) - cap} characters]"
    return result


def _guard_tavily(tool):
    """Wrap a Tavily tool: egress guard, official-domain guard, size budget, source capture."""
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
        _clamp(name, kwargs)
        _count("tavily")
        _step(f"{name} · " + _target(name, kwargs))
        result = await original(*args, **kwargs)
        _add_sources(result)
        return _trim(name, result)

    tool.coroutine = guarded
    return tool


# ---------------------------------------------------------------------------
# Inline tools — the repo side of the gap, PyPI, and suggested fixes
# ---------------------------------------------------------------------------

def _make_local_tools():
    from langchain_core.tools import tool

    @tool
    def inventory_models() -> dict:
        """List every LLM model id referenced in the repo's code and config.

        Returns {models: [{model, provider, locations: ["path:line", ...], apps: [...],
        shared: bool}], note}. shared=true means a shared default every app can fall back to.
        """
        _count("internal")
        _step("Inventory · model ids in code and config")
        return drift.inventory_models(_RUN["root"])

    @tool
    def inventory_packages(only: Optional[list[str]] = None) -> dict:
        """List the Python packages in the repo's requirements*.txt and pyproject.toml files.

        Args:
            only: optional package names to limit the result to (e.g. the pack's priority list).

        Returns {dependency_files, total_packages, unpinned, packages: [{package, specs,
        pinned, files, file_count}]}. specs are the version constraints the repo declares.
        """
        _count("internal")
        _step("Inventory · packages in requirements and pyproject")
        return drift.inventory_packages(_RUN["root"], only=only)

    @tool
    def check_pypi(packages: list[str]) -> list:
        """Latest release of each package on PyPI, compared with the repo's version specs.

        Args:
            packages: package names from inventory_packages (at most 40 per call).

        Returns one entry per package: {package, latest, released (date), yanked,
        requires_python, inactive (no release in 18 months), links (changelog/source),
        our_specs, latest_allowed (false = a pin or cap in the repo blocks the latest
        release), blocked_by}. Use this for versions; use Tavily to find out what changed.
        """
        _count("pypi")
        _step(f"PyPI · latest releases of {len(packages)} package(s)")
        _RUN["pypi_checked"].extend(packages)
        specs = {p["package"]: p["specs"]
                 for p in drift.inventory_packages(_RUN["root"], only=packages)["packages"]}
        try:
            from _usage import track_call
            track_call("pypi", n=len(packages))
        except Exception:  # noqa: BLE001 — usage tracking is optional
            pass
        rows = drift.pypi_latest(packages, specs)
        _RUN["pypi_rows"].extend(rows)
        return rows

    @tool
    def get_usage() -> dict:
        """Real usage of this gallery's apps from the usage collector: requests per app and
        calls per provider. Only meaningful when the repo is cuga-project/cuga-apps.

        Returns {available, apps: [...], providers: [...]} or {available: false, reason}.
        Use it to rank impact: a change to a heavily used app matters more.
        """
        _count("internal")
        if _RUN["repo"] != "cuga-project/cuga-apps":
            return {"available": False, "reason": "usage is only recorded for cuga-project/cuga-apps"}
        return _usage_stats()

    @tool
    def get_watch_pack() -> dict:
        """The active watch pack: official source domains, seed pages, crawl
        instructions, severity rules and (for packages) a priority list."""
        return PACKS.get(_RUN["pack"], {})

    @tool
    def list_accepted_risks() -> list:
        """Findings a person has marked as accepted risk for this repo. Do not raise these again."""
        return [{"pack": f["pack"], "dependency": f["dependency"], "kind": f["kind"], "note": f["note"]}
                for f in _list_findings(repo=_RUN["repo"]) if f["status"] == "accepted"]

    @tool
    def suggest_fix(title: str, rationale: str, file_path: str, find: str,
                    replace: str, evidence_url: str) -> dict:
        """Prepare a one-line fix as a diff the user can copy. This changes nothing anywhere.

        Args:
            title: short title, e.g. "Raise the mcp cap to allow 2.x".
            rationale: one or two sentences: what drifted, quoting the source.
            file_path: repo-relative path from the inventory results, e.g. "build/requirements.apps.txt".
            find: exact text currently in the file (copy it, one line is best).
            replace: the replacement text.
            evidence_url: the official URL that proves the change.

        Returns {id, diff} or {error}. Tell the user the suggested fix is in the
        Suggested fixes tab. Never say it was applied.
        """
        _count("internal")
        _step(f"Suggested fix · {file_path}")
        return _create_suggestion(title, rationale, file_path, find, replace, evidence_url)

    return [inventory_models, inventory_packages, check_pypi, get_usage, get_watch_pack,
            list_accepted_risks, suggest_fix]


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


def _create_suggestion(title, rationale, file_path, find, replace, evidence_url) -> dict:
    root = _RUN["root"]
    rel = file_path.strip().lstrip("/")
    path = (root / rel).resolve()
    if root.resolve() not in path.parents or not path.is_file():
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
    sid = uuid.uuid4().hex[:8]
    with _db() as con:
        con.execute("""INSERT INTO suggestions (id, repo, title, rationale, file_path,
            evidence_url, diff, created_at) VALUES (?,?,?,?,?,?,?,?)""",
            (sid, _RUN["repo"], title, rationale, rel, evidence_url, diff, _now()))
    _RUN["suggestions"].append(sid)
    return {"id": sid, "diff": diff}


# ---------------------------------------------------------------------------
# System prompt + policies
# ---------------------------------------------------------------------------

_SYSTEM = """\
# Dependency Drift Watcher

You find drift: places where the outside world has changed but a repository's code
still assumes the old state. Each request names the repository being checked and an
active watch pack (Models or Packages).

## Workflow
1. The request includes the repo's inventory, computed by the app: it is the complete
   list of dependencies. Never mention a model, package or file that is not in it.
   Call inventory_models / inventory_packages only for more locations. For packages,
   start with the pack's priority list when the repo uses those packages, then the
   most widely used ones. Call get_usage when ranking impact (cuga-apps only).
2. For packages, call check_pypi for latest versions and for specs that block them.
3. Read the world's side from official sources only, with the Tavily tools:
   - tavily_search for recent notices (set include_domains to the pack's domains),
   - tavily_map / tavily_crawl on the pack's seed pages to find lifecycle, pricing or
     release pages,
   - tavily_extract with a `query` to pull the exact sentence that proves a change,
   - tavily_research only when the user asks for a comparison of replacements.
4. Compare: does the change affect a model or package the repo actually uses? Where (file:line)?
5. Skip anything in list_accepted_risks.
6. For a clear one-line fix (a model id, a version pin), call suggest_fix. It only
   prepares a diff to copy; never say a fix was applied.

## Rules
- Every finding needs a quote copied from a page you read in this check and that page's
  URL. No quote, no finding. Findings citing pages you did not read are removed.
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
5. Draft: for a one-line fix, call suggest_fix; never claim a fix was applied.
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


def _pack_preamble(pack_id: str, snapshot: dict) -> str:
    p = PACKS[pack_id]
    lines = [
        f"[Repository: {snapshot['repo']} ({snapshot['ref']}), {snapshot['url']}; "
        f"paths in the inventory are relative to its root]",
        f"[Active watch pack: {p['title']}] {p['summary']}",
        f"Official source domains (Tavily calls are limited to these): {', '.join(p['domains'])}",
        f"Seed pages for tavily_map / tavily_crawl: {', '.join(p.get('seeds', []))}",
        f"Crawl instructions: {p.get('crawl_instructions', '')}",
        f"Search time_range: {p.get('time_range', 'month')}",
        "Severity rules: " + "; ".join(f"{k}: {v}" for k, v in p.get("severity", {}).items()),
    ]
    if p.get("priority"):
        lines.append("Priority packages (check these first when the repo uses them): "
                     + ", ".join(p["priority"]))
    return "\n".join(lines)


_SCAN_QUESTIONS = {
    "models": ("Run a full Models drift check: inventory our models, check each provider's "
               "official lifecycle and pricing sources, and report what drifted."),
    "packages": ("Run a Packages drift check: compare the repo's version specs with the latest "
                 "releases on PyPI, and look for advisories, inactive projects and pins or caps "
                 "that block upgrades."),
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
        "pypi_calls": _RUN["counts"].get("pypi", 0),
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
    repo: str = ""          # owner/repo, owner/repo@ref or a github.com URL; "" = default


class ScanRequest(BaseModel):
    pack: str = DEFAULT_PACK
    repo: str = ""


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

    async def _run(question: str, pack: str, repo: str = "", job: Optional[dict] = None) -> dict:
        if pack not in PACKS:
            pack = DEFAULT_PACK
        # Raises drift.RepoError (bad name, private/missing, too big) before any LLM call.
        snapshot = await asyncio.to_thread(drift.fetch_repo, repo)
        if job is not None:
            job["steps"].append({"t": round(time.time() - job["started"], 1),
                                 "text": f"Repo · {snapshot['repo']} ({snapshot['files']} files read"
                                         + (", cached" if snapshot.get("cached") else "") + ")"})
        agent = await _get_agent()
        async with _RUN_LOCK:
            if job is not None:
                job["status"] = "running"
            _reset_run(pack, snapshot, job)
            started = time.time()
            # Ground the agent: the app computes the inventory itself and hands it
            # over as fact, so the model can't invent dependencies or files.
            brief = await asyncio.to_thread(drift.inventory_brief, pack, _RUN["root"])
            _step(f"Inventory · {len(brief['known'])} {'packages' if pack == 'packages' else 'model ids'} found")
            prompt = f"{_pack_preamble(pack, snapshot)}\n{brief['text']}\n\n{question}"
            result = await agent.invoke(prompt, thread_id=uuid.uuid4().hex)
            read_nothing = not _RUN["counts"].get("tavily") and not _RUN["counts"].get("pypi")
            if read_nothing:
                # The model sometimes answers from memory on its first turn. Retry
                # once, saying so; whatever survives is still checked below.
                _step("Retry · the agent answered without reading any source")
                _event("Grounding check", "applied", "First answer read no sources; asked the agent to check them")
                result = await agent.invoke(
                    prompt + "\n\nImportant: answer only from what the tools return in this check. "
                    "Call check_pypi (packages) or the Tavily tools (models) on official sources before "
                    "you answer; quote only text you read here.", thread_id=uuid.uuid4().hex)
            answer = result.answer if hasattr(result, "answer") else str(result)
            clean, raw = drift.split_findings(answer)
            findings, dropped = drift.verify_findings(raw, brief["known"], pack, _RUN["sources"],
                                                      _RUN["pypi_checked"])
            if pack == "packages":
                # PyPI facts don't depend on the model formatting its findings block.
                have = {f["dependency"] for f in findings if f.get("severity") != "none"}
                findings += [f for f in drift.pypi_findings(_RUN["pypi_rows"], brief["known"])
                             if f["dependency"] not in have]
            read_nothing = not _RUN["counts"].get("tavily") and not _RUN["counts"].get("pypi")
            if read_nothing:
                findings = [f for f in findings if f.get("severity") == "none"]
                clean = ("⚠ This check read no outside sources, so none of its claims are verified and "
                         "nothing was saved. Please ask again.")
                _event("Grounding check", "blocked", "No sources were read; findings discarded")
            elif dropped:
                # The model's prose may repeat what was dropped; show only verified data.
                clean = drift.render_findings(findings) + "\n\n" + "\n".join(
                    [f"⚠ Removed {len(dropped)} finding(s) that could not be verified:"]
                    + [f"- {d.get('dependency', '?')}: {d['reason']}" for d in dropped[:10]])
                _event("Grounding check", "applied",
                       f"Removed {len(dropped)} unverified finding(s); answer rebuilt from verified data")
            if findings and not read_nothing:
                _save_findings(snapshot["repo"], pack, findings)
            return {
                "answer": clean,
                "pack": pack,
                "repo": {k: snapshot[k] for k in ("repo", "ref", "url", "files", "fetched_at")},
                "findings": findings,
                "dropped": [{"dependency": d.get("dependency"), "reason": d["reason"]} for d in dropped],
                "suggestions": list(_RUN["suggestions"]),
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
                    await _run(_SCAN_QUESTIONS.get(pack, "Run a drift check."), pack, drift.DEFAULT_REPO)
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
            "pypi": "public API · no key",
            "policies": list(_POLICIES),
            "model": os.getenv("LLM_MODEL"),
            "default_repo": drift.DEFAULT_REPO,
            "scan_every_hours": _sched["every_hours"],
            "last_scan": _sched["last_scan"],
        }

    @app.get("/packs")
    async def packs():
        return [{"id": p["id"], "title": p["title"], "summary": p["summary"],
                 "domains": p["domains"], "examples": p.get("examples", [])} for p in PACKS.values()]

    # Checks run as background jobs. A Models check can take several minutes, longer
    # than Code Engine's 300 s request timeout, so POST /ask and /scan return a job
    # id at once and the UI polls GET /jobs/{id} for live steps and the result.
    jobs: dict[str, dict] = {}

    def _start_job(question: str, pack: str, repo: str) -> dict:
        drift.parse_repo(repo)                       # bad names fail now, with a 400
        now = time.time()
        for jid in [j for j, v in jobs.items() if now - v["created"] > 3600]:
            jobs.pop(jid, None)
        waiting = sum(1 for v in jobs.values() if v["status"] in ("queued", "running"))
        job = {"id": uuid.uuid4().hex[:12], "status": "queued", "question": question, "pack": pack,
               "repo": repo or drift.DEFAULT_REPO, "created": now, "started": now,
               "ahead": waiting, "steps": [], "result": None, "error": None}
        jobs[job["id"]] = job

        async def work():
            try:
                job["result"] = await _run(question, pack, repo, job)
                job["status"] = "done"
            except drift.RepoError as exc:
                job.update(status="error", error=str(exc))
            except Exception as exc:  # noqa: BLE001
                log.exception("drift check failed")
                job.update(status="error", error=f"The check failed: {exc}")
            finally:
                job["seconds"] = round(time.time() - job["started"], 1)

        asyncio.create_task(work())
        return job

    def _public(job: dict) -> dict:
        return {k: job.get(k) for k in ("id", "status", "pack", "repo", "ahead", "steps",
                                        "result", "error", "seconds")} | {
            "elapsed": round(time.time() - job["started"], 1)}

    @app.get("/jobs/{job_id}")
    async def job_status(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            return JSONResponse(status_code=404, content={"error": "No such check (they expire after an hour)."})
        return _public(job)

    @app.get("/repo")
    async def repo_info(repo: str = ""):
        """Check a repo can be scanned (and warm its snapshot) before asking."""
        try:
            snap = await asyncio.to_thread(drift.fetch_repo, repo)
        except drift.RepoError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        return {k: snap[k] for k in ("repo", "ref", "url", "files", "fetched_at", "cached")}

    @app.post("/ask")
    async def ask(req: AskRequest):
        from _usage import track_utterance
        track_utterance(f"[{req.repo or drift.DEFAULT_REPO}] {req.question}")
        try:
            return JSONResponse(status_code=202, content=_public(_start_job(req.question, req.pack, req.repo)))
        except drift.RepoError as exc:
            return JSONResponse(status_code=400, content={"answer": str(exc), "error": str(exc)})

    @app.post("/scan")
    async def scan(req: ScanRequest):
        try:
            job = _start_job(_SCAN_QUESTIONS.get(req.pack, "Run a drift check."), req.pack, req.repo)
        except drift.RepoError as exc:
            return JSONResponse(status_code=400, content={"answer": str(exc), "error": str(exc)})
        _sched["last_scan"] = _now()
        return JSONResponse(status_code=202, content=_public(job))

    @app.get("/findings")
    async def findings(repo: Optional[str] = None, pack: Optional[str] = None):
        if repo:
            try:
                repo = drift.parse_repo(repo)[0]
            except drift.RepoError:
                return []
        return _list_findings(repo, pack)

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

    @app.get("/suggestions")
    async def suggestions(repo: Optional[str] = None):
        if repo:
            try:
                repo = drift.parse_repo(repo)[0]
            except drift.RepoError:
                return []
        return _list_suggestions(repo)

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
