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
        return _load_store()

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

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Web Researcher</title>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    background:#0f1117;color:#e2e8f0;min-height:100vh}

  header{background:#1a1a2e;border-bottom:1px solid #2d2d4a;padding:14px 28px;
    display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}
  header h1{font-size:16px;font-weight:700;color:#fff}
  .badge{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
  .badge-teal{background:#0d3330;color:#5eead4}
  .badge-red{background:#450a0a;color:#f87171}
  .spacer{flex:1}
  .hdr-stat{font-size:11px;color:#4b5563}

  .layout{display:grid;grid-template-columns:320px 1fr;gap:20px;
    max-width:1280px;margin:0 auto;padding:20px 24px}

  .card{background:#1a1a2e;border:1px solid #2d2d4a;border-radius:10px;
    overflow:hidden;margin-bottom:16px}
  .card-header{padding:12px 16px 10px;border-bottom:1px solid #2d2d4a;
    display:flex;align-items:center;gap:8px}
  .card-header h2{font-size:13px;font-weight:600;color:#c5cae9}
  .card-body{padding:16px}

  .srow{display:flex;align-items:center;gap:8px;margin-bottom:9px}
  .srow label{font-size:12px;color:#9ca3af;min-width:90px}
  input[type=text],input[type=password],input[type=email]{flex:1;padding:5px 9px;
    border-radius:5px;font-size:12px;background:#0f1117;border:1px solid #374151;
    color:#e2e8f0;outline:none}
  input:focus{border-color:#0d9488}
  select{flex:1;padding:5px 9px;border-radius:5px;font-size:12px;
    background:#0f1117;border:1px solid #374151;color:#e2e8f0;outline:none}
  .btn{padding:5px 14px;border-radius:6px;font-size:12px;font-weight:500;
    cursor:pointer;border:none;background:#0d9488;color:#fff;transition:background .15s}
  .btn:hover{background:#0f766e}
  .btn:disabled{background:#374151;color:#6b7280;cursor:default}
  .btn-sm{padding:3px 10px;font-size:11px}
  .btn-ghost{background:#1f2937;border:1px solid #374151;color:#9ca3af}
  .btn-ghost:hover{background:#374151}
  .btn-red{background:#7f1d1d;color:#f87171}
  .btn-red:hover{background:#991b1b}
  .save-ok{color:#4ade80;font-size:11px;margin-left:6px;display:none}

  /* Topic list */
  .topic-item{padding:9px 12px;border:1px solid #2d2d4a;border-radius:6px;
    margin-bottom:7px;display:flex;align-items:flex-start;gap:8px}
  .topic-query{font-size:12px;color:#e2e8f0;flex:1;line-height:1.4}
  .topic-meta{font-size:10px;color:#6b7280;margin-top:3px}
  .topic-actions{display:flex;gap:4px;flex-shrink:0}
  .topic-disabled{opacity:.4}
  .sched-pill{font-size:10px;padding:1px 6px;border-radius:8px;
    background:#1e3a5f;color:#60a5fa}

  /* Chat */
  .chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:11px}
  .chip{padding:4px 10px;border-radius:12px;font-size:11px;background:#1f2937;
    border:1px solid #374151;color:#9ca3af;cursor:pointer;transition:all .15s}
  .chip:hover{background:#0d9488;border-color:#0d9488;color:#fff}
  .chat-row{display:flex;gap:8px}
  .chat-input{flex:1;padding:8px 12px;border-radius:7px;font-size:13px;
    background:#0f1117;border:1px solid #374151;color:#e2e8f0;outline:none}
  .chat-input:focus{border-color:#0d9488}
  .chat-send{padding:8px 16px;border-radius:7px;font-size:13px;cursor:pointer;
    border:none;background:#0d9488;color:#fff}
  .chat-send:hover{background:#0f766e}
  .chat-send:disabled{background:#374151;color:#6b7280;cursor:default}
  .chat-result{margin-top:12px;padding:12px;border-radius:7px;background:#0f1117;
    border:1px solid #2d2d4a;font-size:13px;line-height:1.6;color:#d1d5db;
    white-space:pre-wrap;display:none}
  .chat-result.vis{display:block}

  /* Report log */
  .report-item{border:1px solid #2d2d4a;border-radius:7px;margin-bottom:10px}
  .report-header{padding:10px 14px;display:flex;align-items:center;gap:8px;cursor:pointer}
  .report-header:hover{background:#1f2937;border-radius:7px 7px 0 0}
  .report-topic{font-size:12px;font-weight:600;color:#c5cae9;flex:1;
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .report-time{font-size:10px;color:#6b7280}
  .report-src{font-size:10px;padding:1px 6px;border-radius:8px}
  .src-chat{background:#1e3a5f;color:#60a5fa}
  .src-scheduled{background:#0d3330;color:#5eead4}
  .src-manual{background:#2e1065;color:#c4b5fd}
  .report-body{padding:10px 14px;font-size:12px;line-height:1.6;color:#d1d5db;
    white-space:pre-wrap;border-top:1px solid #2d2d4a;background:#0f1117;display:none}
  .report-body.open{display:block}
  .empty-state{font-size:13px;color:#4b5563;text-align:center;padding:32px}
  .api-warning{background:#451a03;border:1px solid #78350f;border-radius:7px;
    padding:10px 12px;font-size:12px;color:#fbbf24;margin-bottom:12px;display:none}
</style>
</head>
<body>

<header>
  <h1>🔬 Web Researcher</h1>
  <span class="badge" id="api-badge">Checking…</span>
  <div class="spacer"></div>
  <span class="hdr-stat">Scheduler checks every 5 min</span>
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
        <div style="border-top:1px solid #2d2d4a;padding-top:12px;margin-top:4px">
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
    if (s.tavily_key) document.getElementById('tavily-key').value = '••••••••••••••••';
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
    el.innerHTML = '<div style="font-size:12px;color:#4b5563;margin-bottom:10px">No scheduled topics yet.</div>';
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
        <span id="ri-${i}" style="font-size:11px;color:#4b5563;margin-left:4px">▸</span>
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
