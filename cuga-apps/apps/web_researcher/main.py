"""
Web Researcher — Tavily-powered research assistant with web UI
=============================================================

Chat interface for on-demand research + scheduled research topics
that auto-run on a configurable schedule and optionally email results.

Run:
    python main.py
    python main.py --port 28798
    python main.py --provider anthropic

Then open: http://127.0.0.1:28798

Environment variables:
    LLM_PROVIDER      rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL         model override
    MCP_WEB_URL       override for the mcp-web server (optional)
    TAVILY_API_KEY    read by the mcp-web server, not this app
    SMTP_HOST         SMTP server (default: smtp.gmail.com)
    SMTP_USERNAME     sender email
    SMTP_PASSWORD     app password
    RESEARCH_TO       recipient for research digests
"""

import argparse
import asyncio
import json
import logging
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent

for _p in [str(_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _carbon import carbon_head, carbon_css

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

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


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def _init_db() -> None:
    with _db() as con:
        con.execute(_CREATE_SQL)


def _save_report(topic: str, report: str, source: str = "chat", emailed: bool = False) -> dict:
    rid = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).isoformat()
    with _db() as con:
        con.execute(
            "INSERT INTO research_log (id, topic, report, source, emailed, created_at) VALUES (?,?,?,?,?,?)",
            (rid, topic, report, source, int(emailed), now),
        )
    return {"id": rid, "topic": topic, "report": report, "source": source,
            "emailed": emailed, "created_at": now}


def _list_reports(limit: int = 50) -> list[dict]:
    with _db() as con:
        rows = con.execute(
            "SELECT * FROM research_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Tools — delegated to the mcp-web MCP server (see mcp_servers/web/server.py).
# The server owns the Tavily client + key; this app only knows the tool name.
# ---------------------------------------------------------------------------

def _make_tools():
    from _mcp_bridge import load_tools
    return load_tools(["web"])


_SYSTEM = """\
# Web Researcher

You are a sharp research assistant with access to real-time web search.

## When triggered by cron (scheduled research)

You will receive a research topic or question in your trigger message.

1. Use `web_search` to gather current information — run 2-4 targeted queries.
2. Synthesise findings into a structured report.
3. Be specific: include names, dates, numbers, and URLs where available.

## When triggered by webhook (on-demand query)

The payload will contain a `query` or `topic` field.  Research it immediately.

## Output format

**Topic**: <the topic>

**Summary** (3-5 sentences)
High-level answer to the research question.

**Key findings**
- Finding 1 (with source URL)
- Finding 2 (with source URL)
- ...

**Sources**
List the most useful URLs you consulted.

**Confidence**: High / Medium / Low — and why.

## Rules

- Always use `web_search` — do not rely on training data for current facts.
- Run multiple searches with different angles for comprehensive coverage.
- Cite URLs for every factual claim.
- Keep the full report under 500 words.
"""


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
    )


# ---------------------------------------------------------------------------
# Background scheduler — runs scheduled research topics
# ---------------------------------------------------------------------------

_sched_status = {"last_run": None, "next_topic": None}


async def _research_scheduler(agent) -> None:
    """Check scheduled topics every 5 min and run if due."""
    while True:
        await asyncio.sleep(300)  # check every 5 minutes
        data   = _load_store()
        topics = data.get("topics", [])
        now    = datetime.now(timezone.utc)

        for topic in topics:
            if not topic.get("enabled", True):
                continue
            schedule  = topic.get("schedule", "daily")
            last_run  = topic.get("last_run")

            due = False
            if last_run is None:
                due = True  # never run
            else:
                try:
                    elapsed = (now - datetime.fromisoformat(last_run)).total_seconds()
                    if schedule == "hourly"  and elapsed >= 3600:   due = True
                    if schedule == "daily"   and elapsed >= 86400:  due = True
                    if schedule == "weekly"  and elapsed >= 604800: due = True
                except Exception:
                    due = True

            if not due:
                continue

            log.info("Scheduled research: %s", topic["query"])
            _sched_status["next_topic"] = topic["query"]
            try:
                result = await agent.invoke(
                    f"Research this topic and produce a detailed structured report:\n\n{topic['query']}",
                    thread_id=f"sched-{topic['id']}",
                )
                report = result.answer
                _save_report(topic["query"], report, source="scheduled", emailed=False)
                topic["last_run"] = now.isoformat()
                log.info("Scheduled research complete: %s", topic["query"])
            except Exception as exc:
                log.error("Scheduled research error: %s", exc)

        data["topics"] = topics
        _save_store(data)
        _sched_status["last_run"] = now.isoformat()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


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


# ---------------------------------------------------------------------------
# Web app
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn

    _init_db()
    agent = make_agent()

    app = FastAPI(title="Web Researcher")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    @app.on_event("startup")
    async def _startup():
        stored_key = _load_store().get("tavily_key", "")
        if stored_key and not os.getenv("TAVILY_API_KEY"):
            os.environ["TAVILY_API_KEY"] = stored_key
        asyncio.create_task(_research_scheduler(agent))
        log.info("Research scheduler started.")

    @app.post("/ask")
    async def api_ask(req: AskReq):
        try:
            result = await agent.invoke(
                f"Research this and produce a structured report:\n\n{req.question}",
                thread_id="chat",
            )
            report = result.answer
            _save_report(req.question, report, source="chat", emailed=False)
            return {"answer": report}
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/reports")
    async def api_reports():
        return _list_reports()

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
        data   = _load_store()
        topics = data.get("topics", [])
        topic  = next((t for t in topics if t["id"] == req.id), None)
        if not topic:
            return JSONResponse({"error": "Topic not found"}, status_code=404)
        try:
            result = await agent.invoke(
                f"Research this topic and produce a detailed structured report:\n\n{topic['query']}",
                thread_id=f"run-{topic['id']}",
            )
            report = result.answer
            entry  = _save_report(topic["query"], report, source="manual", emailed=False)
            topic["last_run"] = datetime.now(timezone.utc).isoformat()
            _save_store(data)
            return {"ok": True, "entry": entry}
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/settings")
    async def api_settings():
        data = _load_store()
        # Report Tavily as configured if the key is present in the environment
        # (e.g. TAVILY_API_KEY from the container .env) OR was saved via the UI
        # form below — either way the mcp-web server can use it. Without this,
        # the UI showed "not set" even when the env key was present.
        data["tavily_configured"] = bool(os.getenv("TAVILY_API_KEY")) or bool(data.get("tavily_key"))
        return data

    @app.post("/settings/credentials")
    async def api_creds(req: CredsReq):
        data = _load_store()
        if req.tavily_key:
            os.environ["TAVILY_API_KEY"] = req.tavily_key
            data["tavily_key"] = req.tavily_key
        _save_store(data)
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
# HTML
# ---------------------------------------------------------------------------

_APP_CSS = """<style>
  /* ── Web Researcher — Carbon (White / g10) app layer ────────────────── */

  /* Header wordmark / status */
  header h1 { font-size: 0.875rem; font-weight: 600; color: #f4f4f4; display: flex; align-items: center; gap: var(--cds-sp-03); }
  .badge { padding: 0 var(--cds-sp-03); height: 1.5rem; display: inline-flex; align-items: center;
    border-radius: 0.9375rem; font-size: 0.75rem; font-weight: 400; letter-spacing: 0.16px; }
  .badge-teal { background: var(--cds-support-success-bg); color: var(--cds-support-success); }
  .badge-red  { background: var(--cds-support-error-bg);   color: var(--cds-support-error); }
  .spacer { flex: 1; }
  .hdr-stat { font-size: 0.75rem; color: #8d8d8d; letter-spacing: 0.32px; }

  .layout { display: grid; grid-template-columns: 320px 1fr; gap: var(--cds-sp-06);
    max-width: 80rem; margin: 0 auto; padding: var(--cds-sp-06) var(--cds-sp-06); }
  @media (max-width: 820px) { .layout { grid-template-columns: 1fr; } }

  /* Cards = Carbon tiles (square, 1px subtle border) */
  .card { background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    margin-bottom: var(--cds-sp-05); }
  .card-header { padding: var(--cds-sp-04) var(--cds-sp-05); border-bottom: 1px solid var(--cds-border-subtle);
    display: flex; align-items: center; gap: var(--cds-sp-03); }
  .card-header h2 { font-size: 0.875rem; font-weight: 600; color: var(--cds-text-primary); letter-spacing: 0.16px; }
  .card-body { padding: var(--cds-sp-05); }

  .srow { display: flex; align-items: center; gap: var(--cds-sp-03); margin-bottom: var(--cds-sp-04); }
  .srow label { font-size: 0.75rem; color: var(--cds-text-secondary); min-width: 90px; letter-spacing: 0.32px; }

  input[type=text], input[type=password], input[type=email] {
    flex: 1; min-height: 2.5rem; padding: 0 var(--cds-sp-05); font-size: 0.875rem;
    background: var(--cds-field-01); border: none; border-bottom: 1px solid var(--cds-border-strong);
    color: var(--cds-text-primary); outline: none; font-family: var(--cds-font-sans); }
  input::placeholder { color: var(--cds-text-placeholder); }
  input:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; }
  select { flex: 1; min-height: 2.5rem; padding: 0 var(--cds-sp-05); font-size: 0.875rem;
    background: var(--cds-field-01); border: none; border-bottom: 1px solid var(--cds-border-strong);
    color: var(--cds-text-primary); outline: none; font-family: var(--cds-font-sans);
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6l.7-.7L8 9.6l4.3-4.3.7.7z'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right var(--cds-sp-05) center; padding-right: var(--cds-sp-08); }
  select:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; }

  /* Buttons */
  .btn { min-height: 2.5rem; padding: 0 var(--cds-sp-05); font-size: 0.875rem; font-weight: 400;
    letter-spacing: 0.16px; cursor: pointer; border: 1px solid transparent;
    background: var(--cds-button-primary); color: var(--cds-text-on-color);
    font-family: var(--cds-font-sans); transition: background var(--cds-dur-mod) var(--cds-ease-productive);
    display: inline-flex; align-items: center; justify-content: center; }
  .btn:hover { background: var(--cds-button-primary-hover); }
  .btn:active { background: var(--cds-button-primary-active); }
  .btn:focus-visible, .btn:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; box-shadow: inset 0 0 0 1px var(--cds-focus-inset); }
  .btn:disabled { background: var(--cds-layer-accent); color: var(--cds-text-placeholder); cursor: default; box-shadow: none; }
  .btn-sm { min-height: 2rem; padding: 0 var(--cds-sp-04); font-size: 0.75rem; }
  .btn-ghost { background: transparent; border: 1px solid var(--cds-border-strong); color: var(--cds-text-secondary); }
  .btn-ghost:hover { background: var(--cds-layer-hover); color: var(--cds-text-primary); }
  .btn-red { background: var(--cds-button-danger); color: #fff; }
  .btn-red:hover { background: var(--cds-button-danger-hover); }
  .save-ok { color: var(--cds-support-success); font-size: 0.75rem; margin-left: var(--cds-sp-03); display: none; }

  /* Topic list */
  .topic-item { padding: var(--cds-sp-04); border: 1px solid var(--cds-border-subtle);
    margin-bottom: var(--cds-sp-03); display: flex; align-items: flex-start; gap: var(--cds-sp-03);
    background: var(--cds-layer-02); }
  .topic-query { font-size: 0.875rem; color: var(--cds-text-primary); flex: 1; line-height: 1.4; }
  .topic-meta { font-size: 0.75rem; color: var(--cds-text-helper); margin-top: var(--cds-sp-02); }
  .topic-actions { display: flex; gap: var(--cds-sp-02); flex-shrink: 0; }
  .topic-disabled { opacity: .45; }
  .sched-pill { font-size: 0.75rem; padding: 0 var(--cds-sp-03); height: 1.25rem; display: inline-flex;
    align-items: center; border-radius: 0.9375rem; background: var(--cds-support-info-bg); color: var(--cds-link-primary); }

  /* Chat */
  .chips { display: flex; flex-wrap: wrap; gap: var(--cds-sp-03); margin-bottom: var(--cds-sp-04); }
  .chip { padding: var(--cds-sp-02) var(--cds-sp-04); border-radius: 0.9375rem; font-size: 0.75rem;
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle); color: var(--cds-text-secondary);
    cursor: pointer; transition: all var(--cds-dur-mod) var(--cds-ease-productive); }
  .chip:hover { background: var(--cds-interactive); border-color: var(--cds-interactive); color: #fff; }
  .chat-row { display: flex; gap: 0; }
  .chat-input { flex: 1; min-height: 3rem; padding: 0 var(--cds-sp-05); font-size: 0.875rem;
    background: var(--cds-field-01); border: none; border-bottom: 1px solid var(--cds-border-strong);
    color: var(--cds-text-primary); outline: none; font-family: var(--cds-font-sans); }
  .chat-input:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; }
  .chat-send { min-height: 3rem; padding: 0 var(--cds-sp-05); font-size: 0.875rem; cursor: pointer;
    border: 1px solid transparent; background: var(--cds-button-primary); color: var(--cds-text-on-color);
    font-family: var(--cds-font-sans); min-width: 8rem; }
  .chat-send:hover { background: var(--cds-button-primary-hover); }
  .chat-send:focus-visible, .chat-send:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; box-shadow: inset 0 0 0 1px var(--cds-focus-inset); }
  .chat-send:disabled { background: var(--cds-layer-accent); color: var(--cds-text-placeholder); cursor: default; }
  .chat-result { margin-top: var(--cds-sp-04); padding: var(--cds-sp-05); background: var(--cds-layer-02);
    border: 1px solid var(--cds-border-subtle); font-size: 0.875rem; line-height: 1.6;
    color: var(--cds-text-primary); white-space: pre-wrap; display: none; }
  .chat-result.vis { display: block; }

  /* Report log */
  .report-item { border: 1px solid var(--cds-border-subtle); margin-bottom: var(--cds-sp-04); background: var(--cds-layer-02); }
  .report-header { padding: var(--cds-sp-04) var(--cds-sp-05); display: flex; align-items: center;
    gap: var(--cds-sp-03); cursor: pointer; transition: background var(--cds-dur-fast) var(--cds-ease-productive); }
  .report-header:hover { background: var(--cds-layer-hover); }
  .report-topic { font-size: 0.875rem; font-weight: 600; color: var(--cds-text-primary); flex: 1;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .report-time { font-size: 0.75rem; color: var(--cds-text-helper); }
  .report-src { font-size: 0.75rem; padding: 0 var(--cds-sp-03); height: 1.25rem; display: inline-flex;
    align-items: center; border-radius: 0.9375rem; }
  .src-chat      { background: var(--cds-support-info-bg);    color: var(--cds-link-primary); }
  .src-scheduled { background: var(--cds-support-success-bg); color: var(--cds-support-success); }
  .src-manual    { background: var(--cds-layer-accent);       color: var(--cds-text-secondary); }
  .report-body { padding: var(--cds-sp-04) var(--cds-sp-05); font-size: 0.875rem; line-height: 1.6;
    color: var(--cds-text-secondary); white-space: pre-wrap; border-top: 1px solid var(--cds-border-subtle);
    background: var(--cds-layer-01); display: none; }
  .report-body.open { display: block; }
  .empty-state { font-size: 0.875rem; color: var(--cds-text-placeholder); text-align: center; padding: var(--cds-sp-07); }
  .api-warning { border-left: 3px solid var(--cds-support-warning); background: var(--cds-support-warning-bg);
    padding: var(--cds-sp-04) var(--cds-sp-05); font-size: 0.875rem; color: var(--cds-text-primary);
    margin-bottom: var(--cds-sp-04); display: none; }
</style>"""

_BODY = r"""<body>

<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Web&nbsp;Researcher</div>
  <span class="badge" id="api-badge" style="margin-left:var(--cds-sp-04)">Checking…</span>
  <div class="cds-header__actions">
    <span class="hdr-stat">Scheduler checks every 5 min</span>
  </div>
</header>

<div class="layout">

  <!-- ── Left ─────────────────────────────────────────── -->
  <div>

    <!-- API Credentials -->
    <div class="card">
      <div class="card-header"><h2>🔑 Credentials</h2></div>
      <div class="card-body">
        <div id="api-warning" class="api-warning">
          ⚠️ TAVILY_API_KEY not set — web search will fail. Add your key below.
        </div>
        <div class="srow"><label>Tavily key</label>
          <input type="password" id="tavily-key" placeholder="tvly-…"></div>
        <button class="btn btn-sm" onclick="saveCreds()">Save</button>
        <span class="save-ok" id="creds-ok">✓ Saved</span>
      </div>
    </div>

    <!-- Scheduled topics -->
    <div class="card">
      <div class="card-header">
        <h2>📅 Scheduled Research</h2>
        <button class="btn btn-sm btn-ghost" style="margin-left:auto" onclick="loadTopics()">↺</button>
      </div>
      <div class="card-body">
        <div id="topics-list"></div>
        <div style="border-top:1px solid var(--cds-border-subtle);padding-top:12px;margin-top:4px">
          <input type="text" id="new-topic" placeholder="Research query…" style="width:100%;margin-bottom:8px">
          <div class="srow">
            <label>Schedule</label>
            <select id="new-schedule">
              <option value="hourly">Hourly</option>
              <option value="daily" selected>Daily</option>
              <option value="weekly">Weekly</option>
            </select>
          </div>
          <button class="btn btn-sm" onclick="addTopic()">+ Add topic</button>
        </div>
      </div>
    </div>

  </div><!-- /left -->

  <!-- ── Right ─────────────────────────────────────────── -->
  <div>

    <!-- Chat research -->
    <div class="card">
      <div class="card-header"><h2>🌐 On-Demand Research</h2></div>
      <div class="card-body">
        <div class="chips">
          <span class="chip" onclick="ask(this.textContent)">Latest AI agent frameworks 2026</span>
          <span class="chip" onclick="ask(this.textContent)">Recent LLM benchmark results</span>
          <span class="chip" onclick="ask(this.textContent)">What's new in multimodal AI this week?</span>
          <span class="chip" onclick="ask(this.textContent)">Open source LLM releases this month</span>
          <span class="chip" onclick="ask(this.textContent)">State of RAG systems in 2026</span>
          <span class="chip" onclick="ask(this.textContent)">Claude vs GPT-4o — key differences</span>
          <span class="chip" onclick="ask(this.textContent)">Latest AI safety research papers</span>
          <span class="chip" onclick="ask(this.textContent)">Top AI tools for developers right now</span>
          <span class="chip" onclick="ask(this.textContent)">Recent breakthroughs in AI reasoning</span>
          <span class="chip" onclick="ask(this.textContent)">Enterprise AI adoption trends 2026</span>
        </div>
        <div class="chat-row">
          <input class="chat-input" id="chat-input" type="text"
            placeholder="Type a research topic or question…"
            onkeydown="if(event.key==='Enter')ask()">
          <button class="chat-send" id="chat-send" onclick="ask()">Research</button>
        </div>
        <div class="chat-result" id="chat-result"></div>
      </div>
    </div>

    <!-- Research log -->
    <div class="card">
      <div class="card-header">
        <h2>📚 Research Log</h2>
        <button class="btn btn-sm btn-ghost" style="margin-left:auto" onclick="loadReports()">↺ Refresh</button>
      </div>
      <div class="card-body" id="reports-body">
        <div class="empty-state">No research yet — run a query above or add a scheduled topic.</div>
      </div>
    </div>

  </div><!-- /right -->

</div>

<script>
async function init() {
  await loadSettings();
  await loadTopics();
  await loadReports();
  checkApiKey();
  setInterval(loadReports, 30000);
  setInterval(loadTopics, 30000);
}

function checkApiKey() {
  const badge = document.getElementById('api-badge');
  const warn  = document.getElementById('api-warning');
  const key   = document.getElementById('tavily-key').value;
  const hasKey = key && key.trim().length > 0;
  badge.className = 'badge ' + (hasKey ? 'badge-teal' : 'badge-red');
  badge.textContent = hasKey ? 'Tavily ready' : 'No API key';
  warn.style.display = hasKey ? 'none' : 'block';
}

async function loadSettings() {
  try {
    const s = await fetch('/settings').then(r => r.json());
    if (s.tavily_configured) document.getElementById('tavily-key').value = '••••••••••••••••';
    checkApiKey();
  } catch(e) {}
}

async function saveCreds() {
  const tKey = document.getElementById('tavily-key').value;
  await fetch('/settings/credentials', { method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      tavily_key: (tKey.includes('•') ? '' : tKey),
    }) });
  flash('creds-ok');
  checkApiKey();
}

// ── Topics ──────────────────────────────────────────────────────────
async function loadTopics() {
  try {
    const topics = await fetch('/topics').then(r => r.json());
    renderTopics(topics);
  } catch(e) {}
}

function renderTopics(topics) {
  const el = document.getElementById('topics-list');
  if (!topics.length) {
    el.innerHTML = '<div style="font-size:0.75rem;color:var(--cds-text-placeholder);margin-bottom:10px">No scheduled topics yet.</div>';
    return;
  }
  el.innerHTML = topics.map(t => `
    <div class="topic-item ${t.enabled ? '' : 'topic-disabled'}">
      <div style="flex:1">
        <div class="topic-query">${esc(t.query)}</div>
        <div class="topic-meta">
          <span class="sched-pill">${t.schedule}</span>
          ${t.last_run ? ' · last: ' + new Date(t.last_run).toLocaleDateString() : ' · never run'}
        </div>
      </div>
      <div class="topic-actions">
        <button class="btn btn-sm btn-ghost" onclick="runTopic('${t.id}',this)" title="Run now">▶</button>
        <button class="btn btn-sm btn-ghost" onclick="toggleTopic('${t.id}',${!t.enabled})"
          title="${t.enabled ? 'Disable' : 'Enable'}">${t.enabled ? '⏸' : '▶️'}</button>
        <button class="btn btn-sm btn-red" onclick="deleteTopic('${t.id}')">✕</button>
      </div>
    </div>`).join('');
}

async function addTopic() {
  const q = document.getElementById('new-topic').value.trim();
  if (!q) return;
  await fetch('/topics/add', { method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      query:    q,
      schedule: document.getElementById('new-schedule').value,
    }) });
  document.getElementById('new-topic').value = '';
  await loadTopics();
}

async function deleteTopic(id) {
  await fetch('/topics/delete', { method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ id }) });
  await loadTopics();
}

async function toggleTopic(id, enabled) {
  await fetch('/topics/toggle', { method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ id, enabled }) });
  await loadTopics();
}

async function runTopic(id, btn) {
  btn.disabled = true; btn.textContent = '⏳';
  try {
    await fetch('/topics/run', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ id }) });
    await loadReports();
    await loadTopics();
  } catch(e) {}
  btn.disabled = false; btn.textContent = '▶';
}

// ── Chat ────────────────────────────────────────────────────────────
async function ask(question) {
  const inp = document.getElementById('chat-input');
  const res = document.getElementById('chat-result');
  const btn = document.getElementById('chat-send');
  const q   = question || inp.value.trim();
  if (!q) return;
  inp.value = q;
  btn.disabled = true; btn.textContent = 'Researching…';
  res.className = 'chat-result vis';
  res.textContent = 'Researching… (this may take a moment)';
  try {
    const r = await fetch('/ask', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ question: q }) });
    const d = await r.json();
    res.textContent = d.answer || d.error || '(no response)';
    await loadReports();
  } catch(e) { res.textContent = 'Error: ' + e.message; }
  btn.disabled = false; btn.textContent = 'Research';
}

// ── Reports ─────────────────────────────────────────────────────────
async function loadReports() {
  try {
    const reports = await fetch('/reports').then(r => r.json());
    renderReports(reports);
  } catch(e) {}
}

function renderReports(reports) {
  const body = document.getElementById('reports-body');
  if (!reports.length) {
    body.innerHTML = '<div class="empty-state">No research yet — run a query above.</div>';
    return;
  }
  body.innerHTML = reports.map((r, i) => `
    <div class="report-item">
      <div class="report-header" onclick="toggleReport('rb-${i}','ri-${i}')">
        <span class="report-topic">${esc(r.topic)}</span>
        <span class="report-src src-${r.source}">${r.source}</span>
        <span class="report-time">${new Date(r.created_at).toLocaleString()}</span>
        <span id="ri-${i}" style="font-size:11px;color:var(--cds-text-helper);margin-left:4px">▸</span>
      </div>
      <div class="report-body" id="rb-${i}">${esc(r.report)}</div>
    </div>`).join('');
}

function toggleReport(bodyId, iconId) {
  document.getElementById(bodyId).classList.toggle('open');
  const icon = document.getElementById(iconId);
  icon.textContent = document.getElementById(bodyId).classList.contains('open') ? '▾' : '▸';
}

function flash(id) {
  const el = document.getElementById(id);
  el.style.display = 'inline';
  setTimeout(() => el.style.display = 'none', 2000);
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

init();
</script>
</body>
</html>"""

_HTML = (
    '<!DOCTYPE html><html lang="en"><head>'
    + carbon_head("Web Researcher")
    + carbon_css("light")
    + _APP_CSS
    + "</head>"
    + _BODY
)


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
        print("  ⚠️  TAVILY_API_KEY not set in this process. mcp-web reads its own env;\n"
              "     make sure TAVILY_API_KEY is set wherever mcp-web runs.\n")

    print(f"\n  Web Researcher  →  http://127.0.0.1:{args.port}\n")
    _web(args.port)
