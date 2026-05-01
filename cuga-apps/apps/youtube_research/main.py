"""
YouTube Research Agent — web UI powered by CugaAgent
=====================================================

Research any topic via YouTube: the agent finds relevant videos,
fetches transcripts, and synthesises findings with citations and
timestamps.  Or paste YouTube URLs directly for instant summaries.

Run:
    python main.py
    python main.py --port 28803
    python main.py --provider anthropic

Then open: http://127.0.0.1:28803

Environment variables:
    LLM_PROVIDER      rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL         model override
    TAVILY_API_KEY    Tavily search API key (required for topic research)
"""
from __future__ import annotations

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
# Persistent store — .store.json next to main.py
# ---------------------------------------------------------------------------

_STORE_PATH = _DIR / ".store.json"


def _load_store() -> dict:
    try:
        return json.loads(_STORE_PATH.read_text()) if _STORE_PATH.exists() else {}
    except Exception:
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
    query      TEXT NOT NULL,
    report     TEXT NOT NULL,
    videos     TEXT NOT NULL DEFAULT '[]',
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


def _save_report(query: str, report: str, videos: str = "[]") -> dict:
    rid = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).isoformat()
    with _db() as con:
        con.execute(
            "INSERT INTO research_log (id, query, report, videos, created_at) VALUES (?,?,?,?,?)",
            (rid, query, report, videos, now),
        )
    return {"id": rid, "query": query, "report": report, "videos": videos, "created_at": now}


def _list_reports(limit: int = 50) -> list[dict]:
    with _db() as con:
        rows = con.execute(
            "SELECT * FROM research_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Tools — all delegated to mcp-web (web_search + get_youtube_video_info +
# get_youtube_transcript live in mcp_servers/web/server.py).
# ---------------------------------------------------------------------------

def _make_tools():
    from _mcp_bridge import load_tools
    return load_tools(["web"])


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_SYSTEM = """\
# YouTube Research Assistant

You help users learn about topics by finding and synthesising YouTube video
content.  You have three tools: `web_search`, `get_youtube_video_info`, and
`get_youtube_transcript`.

## Modes of operation

### Mode 1 — Topic research (no URLs in the user message)
The user gives you a topic.  Your job is to find relevant YouTube videos and
synthesise what the top creators are saying.

Process:
1. Call `web_search` with 2-3 queries designed to surface YouTube videos.
   Good query patterns:
   - "{topic} youtube video explained"
   - "{topic} tutorial OR talk site:youtube.com"
   - "{topic} 2026" (for recency)
   Vary the angle across queries so results aren't redundant.
2. From the search results, identify YouTube URLs (youtube.com/watch or
   youtu.be links).  Prefer videos from known or credible channels.
   Aim for 3-5 candidate videos.
3. Call `get_youtube_video_info` on each candidate to check the title, channel, and
   relevance.  Skip videos that look off-topic based on their title.
4. Call `get_youtube_transcript` for each selected video.  Some will fail (no
   captions available) — skip those and work with what you have.
5. Synthesise across all transcripts.

### Mode 2 — Direct URLs (user message contains YouTube links)
The user gives you one or more YouTube URLs.  Fetch transcripts and
summarise or analyse as requested.  Do NOT call web_search — go straight
to `get_youtube_video_info` and `get_youtube_transcript`.

### Mode 3 — Follow-up questions
The user asks about videos already discussed in the conversation.  Answer
from transcript content already in context.  Cite timestamps.

## Citation format — CRITICAL

Every factual claim from a video MUST be attributed.  Use this format:

  [Channel Name](youtube_url) at [MM:SS]: "key quote or close paraphrase"

When multiple creators agree, say so explicitly:
  "Both **Andrej Karpathy** ([12:30]) and **Yannic Kilcher** ([08:15])
   emphasise that …"

When they disagree, highlight the tension:
  "Karpathy argues X ([14:20]), while Kilcher pushes back, noting Y ([22:05])."

## Output structure for topic research

Use this structure — adapt section lengths to the depth of content found:

**Topic**: <the topic>

**Videos analysed**
- [Title](url) by Channel Name (duration)
  (list each video; note any that had no transcript available)

**Synthesis**
Organise by THEMES, not by video.  Each paragraph should cite across
multiple sources where possible.  Use the citation format above.

**Points of agreement** (where multiple creators converge)

**Points of disagreement** (where they diverge — skip if none)

**Key quotes** (2-3 direct quotes with timestamps and attribution)

**Gaps** (what wasn't well covered — suggest further exploration)

## Output structure for direct URL summaries

**Video**: [Title](url) by Channel Name

**Summary** (5-8 bullet points covering the core content)

**Key moments**
- [MM:SS] — description of what's discussed at that point
- [MM:SS] — …

**Takeaways** (3-5 main points)

## Rules

- NEVER fabricate quotes or timestamps.  Every timestamp must come from an
  actual transcript segment.
- NEVER summarise a video you haven't fetched a transcript for.  A video's
  title and search snippet are not enough — you need the actual content.
- If fewer than 2 transcripts are available after searching, tell the user
  and offer to try different search terms.
- Keep topic-research synthesis to under 800 words unless the user asks for
  more depth.
- Prefer recent videos (last 12 months) unless the user asks for older
  content.
- When the user provides URLs directly, do NOT call web_search.
"""


def make_agent():
    from cuga import CugaAgent
    from _llm import create_llm

    tools = _make_tools()

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=tools,
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class AskReq(BaseModel):
    question: str


class CredentialsReq(BaseModel):
    tavily_key: str = ""


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse

    _init_db()

    app = FastAPI(title="YouTube Research", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    _agent = make_agent()

    # Restore persisted Tavily key
    stored_key = _load_store().get("tavily_key", "")
    if stored_key and not os.getenv("TAVILY_API_KEY"):
        os.environ["TAVILY_API_KEY"] = stored_key

    @app.post("/ask")
    async def api_ask(req: AskReq):
        question = req.question.strip()
        if not question:
            return JSONResponse({"error": "Empty question"}, status_code=400)
        try:
            result = await _agent.invoke(question, thread_id="research")
            report = result.answer
            _save_report(question, report)
            return {"answer": report}
        except Exception as exc:
            log.error("Agent error: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/reports")
    async def api_reports():
        return _list_reports()

    @app.get("/settings")
    async def api_settings():
        return {
            "tavily_configured": bool(os.getenv("TAVILY_API_KEY")),
        }

    @app.post("/settings/credentials")
    async def api_creds(req: CredentialsReq):
        data = _load_store()
        if req.tavily_key and not req.tavily_key.startswith("•"):
            os.environ["TAVILY_API_KEY"] = req.tavily_key
            data["tavily_key"] = req.tavily_key
        _save_store(data)
        return {"ok": True, "tavily_configured": bool(os.getenv("TAVILY_API_KEY"))}

    @app.get("/", response_class=HTMLResponse)
    async def ui():
        return HTMLResponse(_WEB_HTML)

    print(f"\n  YouTube Research  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_WEB_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>YouTube Research</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#0f0f13;color:#e2e2e8;min-height:100vh}

header{background:#1a1a24;border-bottom:1px solid #2e2e40;padding:14px 28px;
  display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}
header h1{font-size:17px;font-weight:700;color:#fff}
.sub{font-size:12px;color:#6b6b7e}.sub span{color:#f87171;font-weight:600}
.spacer{flex:1}
.badge{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
.badge-on{background:#0d3330;color:#5eead4}
.badge-off{background:#450a0a;color:#f87171}

.layout{display:grid;grid-template-columns:280px 1fr;gap:20px;
  max-width:1120px;margin:0 auto;padding:20px 24px}
@media(max-width:720px){.layout{grid-template-columns:1fr}}

.card{background:#1a1a24;border:1px solid #2e2e40;border-radius:12px;
  padding:18px;margin-bottom:16px}
.card:last-child{margin-bottom:0}
.card-title{font-size:11px;font-weight:700;color:#6b6b7e;letter-spacing:.08em;
  text-transform:uppercase;margin-bottom:14px}
.section-label{font-size:11px;font-weight:600;color:#4a4a60;letter-spacing:.06em;
  text-transform:uppercase;margin:16px 0 10px;padding-top:16px;
  border-top:1px solid #1e1e2e}
.section-label:first-child{margin-top:0;padding-top:0;border-top:none}

label{display:block;font-size:11px;color:#6b6b7e;margin-bottom:4px;font-weight:500;
  text-transform:uppercase;letter-spacing:.05em}
input[type=text],input[type=password]{width:100%;background:#0f0f13;
  border:1px solid #2e2e40;border-radius:7px;padding:8px 12px;font-size:13px;
  color:#e2e2e8;outline:none;transition:border-color .15s}
input:focus{border-color:#f87171;box-shadow:0 0 0 3px rgba(248,113,113,.1)}
input::placeholder{color:#4a4a60}
.field{margin-bottom:10px}

button{background:#dc2626;color:#fff;border:none;border-radius:7px;
  padding:8px 16px;font-size:13px;font-weight:600;cursor:pointer;
  transition:background .15s,opacity .15s;white-space:nowrap;width:100%;margin-top:10px}
button:hover{background:#b91c1c}
button:disabled{opacity:.45;cursor:default}

.status-row{display:flex;align-items:center;gap:7px;margin-top:10px;
  padding:8px 12px;background:#0f0f13;border:1px solid #1e1e2e;border-radius:7px;
  font-size:12px}
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.dot.on{background:#10b981;box-shadow:0 0 5px #10b981}
.dot.off{background:#374151}
.status-text{color:#6b6b7e;flex:1}
.status-text strong{color:#e2e2e8}

.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.chip{background:#111827;border:1px solid #1e293b;border-radius:6px;
  padding:5px 10px;font-size:12px;color:#94a3b8;cursor:pointer;transition:all .15s}
.chip:hover{background:#dc2626;border-color:#dc2626;color:#fff}

.chat-row{display:flex;gap:8px}
.chat-input{flex:1;padding:9px 14px;border-radius:8px;font-size:14px;
  background:#0f0f13;border:1px solid #2e2e40;color:#e2e2e8;outline:none}
.chat-input:focus{border-color:#f87171;box-shadow:0 0 0 3px rgba(248,113,113,.1)}
.chat-send{width:auto;margin-top:0;padding:9px 20px}

.result{margin-top:14px;padding:16px;background:#111827;border:1px solid #1e293b;
  border-radius:9px;font-size:14px;line-height:1.75;color:#e2e8f0;display:none;
  overflow-x:auto}
.result.visible{display:block}
.result a{color:#f87171;text-decoration:none}
.result a:hover{text-decoration:underline}
.result strong{color:#fff}
.thinking{color:#6b6b7e;font-style:italic;font-size:13px}
.spinner{display:inline-block;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.fadein{animation:fadein .2s ease}

.report-item{border:1px solid #2e2e40;border-radius:8px;margin-bottom:8px;overflow:hidden}
.report-header{padding:10px 14px;display:flex;align-items:center;gap:8px;cursor:pointer}
.report-header:hover{background:#1f2937}
.report-query{font-size:12px;font-weight:600;color:#c5cae9;flex:1;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.report-time{font-size:10px;color:#6b7280}
.report-toggle{font-size:11px;color:#4b5563}
.report-body{padding:12px 14px;font-size:13px;line-height:1.7;color:#d1d5db;
  border-top:1px solid #2e2e40;background:#0f0f13;display:none;white-space:pre-wrap}
.report-body.open{display:block}
.empty{font-size:13px;color:#4b5563;text-align:center;padding:28px}
</style>
</head>
<body>

<header>
  <h1>YouTube Research</h1>
  <p class="sub">Powered by <span>CugaAgent</span></p>
  <div class="spacer"></div>
  <span class="badge" id="apiBadge">Checking…</span>
</header>

<div class="layout">

  <!-- ══ Left panel ══ -->
  <div>
    <div class="card">
      <div class="section-label">API Keys</div>
      <div class="field">
        <label>Tavily <span style="font-weight:400;text-transform:none;letter-spacing:0;color:#4a4a60">— web search</span></label>
        <input id="tavilyKey" type="password" placeholder="tvly-…" />
      </div>
      <button id="saveBtn" onclick="saveCreds()">Save key</button>
      <div class="status-row">
        <span class="dot off" id="apiDot"></span>
        <span class="status-text" id="apiLabel">Not configured</span>
      </div>
    </div>

    <div class="card">
      <div class="section-label">How it works</div>
      <p style="font-size:12px;color:#6b6b7e;line-height:1.6">
        <strong style="color:#e2e2e8">Topic mode</strong> — type a topic and the agent
        searches the web for YouTube videos, fetches their transcripts, and synthesises
        findings with citations and timestamps.<br><br>
        <strong style="color:#e2e2e8">URL mode</strong> — paste one or more YouTube URLs
        directly and ask any question about the content.
      </p>
    </div>
  </div>

  <!-- ══ Right panel ══ -->
  <div>

    <!-- Research chat -->
    <div class="card">
      <div class="card-title">Research</div>
      <div class="chips">
        <span class="chip" onclick="ask(this.textContent)">Latest developments in AI agents</span>
        <span class="chip" onclick="ask(this.textContent)">How does RLHF work?</span>
        <span class="chip" onclick="ask(this.textContent)">Best practices for RAG pipelines</span>
        <span class="chip" onclick="ask(this.textContent)">Transformer architecture explained</span>
        <span class="chip" onclick="ask(this.textContent)">State of open source LLMs in 2026</span>
        <span class="chip" onclick="ask(this.textContent)">Kubernetes vs Docker explained</span>
        <span class="chip" onclick="ask(this.textContent)">How do vector databases work?</span>
        <span class="chip" onclick="ask(this.textContent)">Prompt engineering best practices</span>
      </div>
      <div class="chat-row">
        <input class="chat-input" id="chatInput" type="text"
          placeholder="Enter a topic to research, or paste YouTube URL(s)…"
          onkeydown="if(event.key==='Enter')ask()">
        <button class="chat-send" id="chatSend" onclick="ask()">Research</button>
      </div>
      <div class="result" id="chatResult"></div>
    </div>

    <!-- Research log -->
    <div class="card">
      <div class="card-title">Research History</div>
      <div id="reportsList">
        <div class="empty">No research yet — try a topic above.</div>
      </div>
    </div>

  </div>
</div>

<script>
async function ask(question) {
  const inp = document.getElementById('chatInput')
  const res = document.getElementById('chatResult')
  const btn = document.getElementById('chatSend')
  const q = question || inp.value.trim()
  if (!q) return
  inp.value = q
  btn.disabled = true; btn.textContent = 'Researching…'
  res.className = 'result visible fadein'
  res.innerHTML = '<span class="thinking"><span class="spinner">⟳</span> Searching YouTube and fetching transcripts… this may take a minute.</span>'

  try {
    const r = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ question: q })
    })
    if (!r.ok) {
      const e = await r.json()
      throw new Error(e.error || r.statusText)
    }
    const data = await r.json()
    res.innerHTML = renderMd(data.answer)
    await loadReports()
  } catch (err) {
    res.innerHTML = '<span style="color:#f87171">Error: ' + esc(err.message) + '</span>'
  } finally {
    btn.disabled = false; btn.textContent = 'Research'
  }
}

function renderMd(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    // Bold
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    // Links: [text](url)
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    // Timestamps [MM:SS] — highlight
    .replace(/\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g, '<span style="color:#f87171;font-weight:600">[$1]</span>')
    // Headings
    .replace(/^### (.+)$/gm, '<div style="font-size:13px;font-weight:700;color:#fff;margin:14px 0 6px">$1</div>')
    .replace(/^## (.+)$/gm, '<div style="font-size:14px;font-weight:700;color:#fff;margin:18px 0 8px">$1</div>')
    // Bullets
    .replace(/^- (.+)$/gm, '<div style="padding-left:16px;margin:3px 0">• $1</div>')
    // Newlines
    .replace(/\\n/g, '<br>')
    .replace(/\n/g, '<br>')
}

/* --- Reports --- */
async function loadReports() {
  try {
    const reports = await fetch('/reports').then(r => r.json())
    renderReports(reports)
  } catch(e) {}
}

function renderReports(reports) {
  const el = document.getElementById('reportsList')
  if (!reports.length) {
    el.innerHTML = '<div class="empty">No research yet — try a topic above.</div>'
    return
  }
  el.innerHTML = reports.map((r, i) => `
    <div class="report-item">
      <div class="report-header" onclick="toggleReport(${i})">
        <span class="report-query">${esc(r.query)}</span>
        <span class="report-time">${new Date(r.created_at).toLocaleString()}</span>
        <span class="report-toggle" id="ri${i}">▸</span>
      </div>
      <div class="report-body" id="rb${i}">${renderMd(r.report)}</div>
    </div>`).join('')
}

function toggleReport(i) {
  const body = document.getElementById('rb'+i)
  const icon = document.getElementById('ri'+i)
  body.classList.toggle('open')
  icon.textContent = body.classList.contains('open') ? '▾' : '▸'
}

/* --- Settings --- */
async function saveCreds() {
  const key = document.getElementById('tavilyKey').value.trim()
  if (!key) return
  const btn = document.getElementById('saveBtn')
  btn.disabled = true; btn.textContent = '…'
  try {
    const r = await fetch('/settings/credentials', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ tavily_key: key })
    })
    const d = await r.json()
    setApiUI(d.tavily_configured)
  } catch(e) { alert('Failed: ' + e.message) }
  finally { btn.disabled = false; btn.textContent = 'Save key' }
}

function setApiUI(configured) {
  document.getElementById('apiDot').className = 'dot ' + (configured ? 'on' : 'off')
  document.getElementById('apiLabel').textContent = configured
    ? 'Tavily key configured' : 'Tavily key not set'
  const badge = document.getElementById('apiBadge')
  badge.className = 'badge ' + (configured ? 'badge-on' : 'badge-off')
  badge.textContent = configured ? 'Tavily ready' : 'No API key'
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

/* --- Init --- */
fetch('/settings').then(r => r.json()).then(s => {
  setApiUI(s.tavily_configured)
  if (s.tavily_configured)
    document.getElementById('tavilyKey').value = '••••••••••••••••'
})
loadReports()
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="YouTube Research Agent — web UI")
    parser.add_argument("--port",     type=int, default=28803)
    parser.add_argument("--provider", "-p", default=None,
                        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model",    "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    if not os.getenv("TAVILY_API_KEY"):
        print("  ⚠  TAVILY_API_KEY not set — add it in the Settings panel in the UI.\n")

    _web(args.port)


if __name__ == "__main__":
    main()
