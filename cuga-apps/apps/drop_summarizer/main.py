"""
Drop Summarizer — upload-driven summarizer with web UI
==========================================

Upload a .txt, .md, .pdf, or image file via the browser. The server extracts
the content, sends it to the agent, and the resulting summary appears in the
in-page feed. There is no folder watcher and no email path — every summary
is the result of an active upload from the browser.

Supports: .txt, .md, .pdf, .png, .jpg, .jpeg, .tiff, .bmp, .gif
Images and PDFs are processed via docling for rich content extraction.

Run:
    python main.py
    python main.py --port 28794
    python main.py --provider anthropic

Then open: http://127.0.0.1:28794

Environment variables:
    LLM_PROVIDER     rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL        model override

Required for images/PDFs:
    pip install docling
"""

import argparse
import asyncio
import logging
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent

for _p in [str(_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _carbon import carbon_head, carbon_css  # noqa: E402  (apps root on sys.path)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

TEXT_EXTENSIONS  = {".txt", ".md"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif"}
PDF_EXTENSIONS   = {".pdf"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | PDF_EXTENSIONS

# ---------------------------------------------------------------------------
# Upload staging area — files written here transiently while we extract +
# summarize them in a background task. No persistent watching, no email.
# ---------------------------------------------------------------------------

_UPLOADS_DIR = _DIR / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# SQLite summary log
# ---------------------------------------------------------------------------

_DATA_DIR = _DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DATA_DIR / "summaries.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS summaries (
    id         TEXT PRIMARY KEY,
    filename   TEXT NOT NULL,
    summary    TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    word_count INTEGER DEFAULT 0,
    alerted    INTEGER DEFAULT 0,
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
        # migrate existing DBs that predate the content column
        try:
            con.execute("ALTER TABLE summaries ADD COLUMN content TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass  # column already exists


def _save_summary(filename: str, summary: str, content: str = "",
                  alerted: bool = False) -> dict:
    entry_id = uuid.uuid4().hex[:8]
    now      = datetime.now(timezone.utc).isoformat()
    wc       = len(summary.split())
    with _db() as con:
        con.execute(
            "INSERT INTO summaries (id, filename, summary, content, word_count, alerted, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (entry_id, filename, summary, content, wc, int(alerted), now),
        )
    return {"id": entry_id, "filename": filename, "summary": summary,
            "content": content, "word_count": wc, "alerted": alerted, "created_at": now}


def _list_summaries(limit: int = 50) -> list[dict]:
    with _db() as con:
        # exclude content from list view (can be large); content fetched per-file on demand
        rows = con.execute(
            "SELECT id, filename, summary, word_count, alerted, created_at "
            "FROM summaries ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def _get_summary_content(filename: str) -> str | None:
    """Return the stored full content for a specific filename (most recent)."""
    with _db() as con:
        row = con.execute(
            "SELECT content FROM summaries WHERE filename=? ORDER BY created_at DESC LIMIT 1",
            (filename,)
        ).fetchone()
    return row["content"] if row else None



# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _extract(path: Path) -> str:
    """Extract text via mcp-text's extract_text tool (docling under the hood).

    Runs in a separate container/process — an OOM in extraction doesn't take
    down this app. Models are pre-downloaded inside the mcp-text image.
    """
    ext = path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8", errors="replace")
    from _mcp_bridge import call_tool
    try:
        result = call_tool(
            "text",
            "extract_text",
            {"file_path": str(path), "max_chars": 200_000},
            timeout=180.0,
        )
    except RuntimeError as exc:
        return f"(extraction error: {exc})"
    except Exception as exc:
        return f"(extraction error: {exc})"
    md = (result or {}).get("markdown", "").strip()
    return md or "(no text extracted — file may be image-only)"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a document analyst. The user will provide extracted file content directly.
Do not ask for tools or file paths — the content is already in the message.

When summarizing, use this format:

<one sentence TL;DR>

Key points:
- <point 1>
- <point 2>
- <point 3>

Action items (if any):
- <action item with owner if mentioned>

Rules:
- Lead with a one-sentence TL;DR.
- 3–5 bullet points covering key points, decisions, or facts.
- Call out action items if present (meeting notes, task lists).
- For code or specs, summarize purpose and main components.
- Keep the whole summary under 15 lines.
- Do not repeat the filename or say "this document is about".
"""


def make_agent():
    from cuga import CugaAgent
    from _llm import create_llm

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=[],
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
        # CUGA's policy DB is a global sqlite store shared by every app. Don't
        # auto-load it, or an output-formatter persisted by another app (e.g.
        # find_a_doctor's doctor board) bleeds in and the model emits that board
        # instead of this app's answer.
        auto_load_policies=False,
    )


# ---------------------------------------------------------------------------
# Per-upload processor — runs as a background asyncio task per file.
# No folder watching, no scheduled polling: every summary is the result of an
# active /upload from the browser.
# ---------------------------------------------------------------------------

_pending_files: set[str] = set()  # filenames currently being processed


async def _process_file(agent, path: Path, original_name: str) -> None:
    """Extract content, summarize, persist. One asyncio task per upload."""
    _pending_files.add(original_name)
    log.info("Processing: %s", original_name)
    try:
        stored_content = await asyncio.get_event_loop().run_in_executor(
            None, _extract, path
        )
        result = await agent.invoke(
            f"File: {original_name}\n\nContent:\n{stored_content[:15000]}\n\nSummarize this document.",
            thread_id=f"sum-{path.stem}-{uuid.uuid4().hex[:6]}",
        )
        _save_summary(original_name, result.answer,
                      content=stored_content, alerted=False)
        log.info("Done: %s", original_name)
    except Exception as exc:
        log.error("Error processing %s: %s", original_name, exc)
        _save_summary(original_name, f"Error: {exc}", content="", alerted=False)
    finally:
        _pending_files.discard(original_name)
        try:
            path.unlink(missing_ok=True)   # clean up the staging file
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class AskReq(BaseModel):
    question: str
    filename: str | None = None


# ---------------------------------------------------------------------------
# Web app
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn

    _init_db()
    agent = make_agent()

    app = FastAPI(title="Drop Summarizer")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    # ── Summaries ──────────────────────────────────────────────────────────
    @app.get("/summaries")
    async def api_summaries():
        return _list_summaries()

    # ── Upload file directly ───────────────────────────────────────────────
    @app.post("/upload")
    async def api_upload(file: UploadFile = File(...)):
        # Stage in uploads/ with a uuid prefix so concurrent uploads with the
        # same filename don't collide; original filename is what the user sees.
        safe_name  = Path(file.filename).name or "upload"
        if Path(safe_name).suffix.lower() not in SUPPORTED_EXTENSIONS:
            return JSONResponse(
                {"error": f"Unsupported file type. Allowed: {sorted(SUPPORTED_EXTENSIONS)}"},
                status_code=400,
            )
        staging   = _UPLOADS_DIR / f"{uuid.uuid4().hex[:8]}-{safe_name}"
        content   = await file.read()
        staging.write_bytes(content)
        asyncio.create_task(_process_file(agent, staging, safe_name))
        return {"ok": True, "filename": safe_name,
                "message": "File queued for summarization."}

    # ── Chat (ask over files) ──────────────────────────────────────────────
    @app.get("/files/pending")
    async def api_pending():
        return {"pending": list(_pending_files)}

    @app.post("/ask")
    async def api_ask(req: AskReq):
        from _usage import track_utterance; track_utterance(req.question)
        if req.filename and req.filename in _pending_files:
            return JSONResponse(
                {"error": f"'{req.filename}' is still being processed. Please wait a moment."},
                status_code=400,
            )
        if req.filename:
            all_s = _list_summaries(200)
            if not any(s["filename"] == req.filename for s in all_s):
                return JSONResponse(
                    {"error": f"'{req.filename}' hasn't been processed yet."},
                    status_code=400,
                )
        try:
            if req.filename:
                # Scoped to a specific file — inject stored content directly
                all_s   = _list_summaries(200)
                match   = next((s for s in all_s if s["filename"] == req.filename), None)
                thread  = f"file-{match['id']}" if match else "chat"
                content = _get_summary_content(req.filename) or ""
                if content.startswith("(extraction error:"):
                    return {"answer": f"This file could not be extracted when it was uploaded. Please re-upload it."}
                prompt = (
                    f"File: {req.filename}\n\nContent:\n{content[:15000]}\n\n"
                    f"Question: {req.question}"
                )
            else:
                # General — inject recent summaries as context
                recent  = _list_summaries(10)
                context = "\n\n".join(
                    f"File: {s['filename']}\nSummary: {s['summary']}"
                    for s in recent
                )
                prompt = (
                    f"Recent file summaries:\n{context}\n\nQuestion: {req.question}"
                ) if recent else req.question
                thread = "chat"
            result = await agent.invoke(prompt, thread_id=thread)
            return {"answer": result.answer}
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    # ── HTML ───────────────────────────────────────────────────────────────
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
# HTML UI
# ---------------------------------------------------------------------------

_APP_CSS = """<style>
  body { background: var(--cds-background); }

  .layout { display: grid; grid-template-columns: 320px 1fr; gap: var(--cds-sp-06);
    max-width: 1280px; margin: 0 auto; padding: var(--cds-sp-06) var(--cds-sp-06); }
  @media (max-width: 820px) { .layout { grid-template-columns: 1fr; } }

  .card { background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    overflow: hidden; margin-bottom: var(--cds-sp-05); }
  .card-header { padding: var(--cds-sp-04) var(--cds-sp-05);
    border-bottom: 1px solid var(--cds-border-subtle);
    display: flex; align-items: center; gap: var(--cds-sp-03); }
  .card-header h2 { font-size: 0.875rem; font-weight: 600; color: var(--cds-text-primary); }
  .card-body { padding: var(--cds-sp-05); }

  .hdr-stat { font-size: 0.75rem; color: var(--cds-text-helper); }

  /* Drop zone */
  .drop-zone { border: 1px dashed var(--cds-border-strong); border-radius: 0;
    padding: var(--cds-sp-07) var(--cds-sp-05); text-align: center; cursor: pointer;
    transition: all var(--cds-dur-mod) var(--cds-ease-productive); position: relative; overflow: hidden;
    background: var(--cds-field-01); }
  .drop-zone:hover, .drop-zone.drag-over { border-color: var(--cds-interactive);
    background: var(--cds-support-info-bg); }
  .drop-zone input[type=file] { position: absolute; inset: 0; width: 100%; height: 100%;
    opacity: 0; cursor: pointer; z-index: 2; }
  .drop-zone .dz-icon { font-size: 28px; margin-bottom: var(--cds-sp-03); }
  .drop-zone p { font-size: 0.875rem; color: var(--cds-text-secondary); line-height: 1.5; }
  .drop-zone small { font-size: 0.75rem; color: var(--cds-text-helper); }

  /* Buttons (Carbon) */
  .btn { display: inline-flex; align-items: center; justify-content: center;
    padding: 0 var(--cds-sp-05); min-height: 2.5rem; border-radius: 0; border: 1px solid transparent;
    font-family: var(--cds-font-sans); font-size: 0.875rem; font-weight: 400; letter-spacing: 0.16px;
    cursor: pointer; background: var(--cds-button-primary); color: var(--cds-text-on-color);
    transition: background var(--cds-dur-mod) var(--cds-ease-productive); }
  .btn:hover { background: var(--cds-button-primary-hover); }
  .btn:active { background: var(--cds-button-primary-active); }
  .btn:focus, .btn:focus-visible { outline: 2px solid var(--cds-focus); outline-offset: -2px;
    box-shadow: inset 0 0 0 1px var(--cds-focus-inset); }
  .btn:disabled { background: var(--cds-layer-accent); color: var(--cds-text-placeholder);
    cursor: default; box-shadow: none; }
  .btn-sm { min-height: 2rem; padding: 0 var(--cds-sp-04); font-size: 0.75rem; }
  .btn-ghost { background: transparent; border: 1px solid var(--cds-border-strong);
    color: var(--cds-text-secondary); }
  .btn-ghost:hover { background: var(--cds-layer-hover); color: var(--cds-text-primary); }

  /* Chips (suggested questions) */
  .chips { display: flex; flex-wrap: wrap; gap: var(--cds-sp-03); margin-bottom: var(--cds-sp-04); }
  .chip { padding: var(--cds-sp-02) var(--cds-sp-04); border-radius: 0.9375rem; font-size: 0.75rem;
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle); color: var(--cds-text-secondary);
    cursor: pointer; transition: all var(--cds-dur-fast) var(--cds-ease-productive); }
  .chip:hover { background: var(--cds-interactive); border-color: var(--cds-interactive); color: #fff; }

  /* Chat */
  .chat-row { display: flex; gap: 0; }
  .chat-input { flex: 1; padding: 0 var(--cds-sp-05); min-height: 3rem; border-radius: 0; font-size: 0.875rem;
    background: var(--cds-field-01); border: none; border-bottom: 1px solid var(--cds-border-strong);
    color: var(--cds-text-primary); outline: none; font-family: var(--cds-font-sans); }
  .chat-input::placeholder { color: var(--cds-text-placeholder); }
  .chat-input:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; }
  .chat-send { padding: 0 var(--cds-sp-05); min-height: 3rem; border-radius: 0; font-size: 0.875rem;
    cursor: pointer; border: 1px solid transparent; background: var(--cds-button-primary); color: #fff;
    white-space: nowrap; flex: none; transition: background var(--cds-dur-mod) var(--cds-ease-productive); }
  .chat-send:hover { background: var(--cds-button-primary-hover); }
  .chat-send:focus, .chat-send:focus-visible { outline: 2px solid var(--cds-focus); outline-offset: -2px;
    box-shadow: inset 0 0 0 1px var(--cds-focus-inset); }
  .chat-send:disabled { background: var(--cds-layer-accent); color: var(--cds-text-placeholder); cursor: default; }
  .chat-result { margin-top: var(--cds-sp-04); padding: var(--cds-sp-05); border-radius: 0;
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle); font-size: 0.875rem;
    line-height: 1.6; color: var(--cds-text-primary); white-space: pre-wrap; display: none; }
  .chat-result.vis { display: block; }

  /* Summary feed */
  .sum-entry { border: 1px solid var(--cds-border-subtle); border-radius: 0; margin-bottom: var(--cds-sp-04);
    background: var(--cds-layer-02); }
  .sum-header { padding: var(--cds-sp-04) var(--cds-sp-05); display: flex; align-items: center;
    gap: var(--cds-sp-03); cursor: pointer; }
  .sum-header:hover { background: var(--cds-layer-hover); }
  .sum-filename { font-size: 0.8125rem; font-weight: 600; color: var(--cds-text-primary); flex: 1;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sum-time { font-size: 0.6875rem; color: var(--cds-text-helper); }
  .sum-wc { font-size: 0.6875rem; color: var(--cds-text-helper); }
  .sum-alert-badge { font-size: 0.6875rem; background: var(--cds-support-warning-bg); color: var(--cds-text-primary);
    padding: 1px 8px; border-radius: 0.9375rem; }
  .sum-body { padding: var(--cds-sp-04) var(--cds-sp-05); font-size: 0.8125rem; line-height: 1.6;
    color: var(--cds-text-secondary); white-space: pre-wrap; border-top: 1px solid var(--cds-border-subtle);
    background: var(--cds-layer-01); display: none; }
  .sum-body.open { display: block; }
  .sum-entry.sum-active { border-color: var(--cds-interactive); }
  .sum-entry.sum-active .sum-header { background: var(--cds-support-info-bg); }
  .empty-state { font-size: 0.875rem; color: var(--cds-text-placeholder); text-align: center; padding: var(--cds-sp-08); }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Drop&nbsp;Summarizer</div>
  <div class="cds-header__actions">
    <span class="hdr-stat" id="hdr-stat">—</span>
    <span class="cds-tag cds-tag--blue">Powered by CugaAgent</span>
  </div>
</header>

<div class="layout">

  <!-- ── Left: Settings + Upload ─────────────────────────────── -->
  <div>

    <!-- Drop zone -->
    <div class="card">
      <div class="card-header"><h2>📥 Upload File</h2></div>
      <div class="card-body">
        <div class="drop-zone" id="drop-zone"
             ondragover="event.preventDefault();this.classList.add('drag-over')"
             ondragleave="this.classList.remove('drag-over')"
             ondrop="handleDrop(event)">
          <input type="file" id="file-input"
                 accept=".txt,.md,.pdf,.png,.jpg,.jpeg,.tiff,.bmp,.gif"
                 onchange="uploadFile(this.files[0])">
          <div class="dz-icon">⬆️</div>
          <p>Drop a file here or click to upload</p>
          <small>.txt · .md · .pdf · .png · .jpg · .tiff · .bmp</small>
          <small style="color:var(--cds-support-error);margin-top:6px;display:block">⚠️ Do not upload confidential or sensitive data</small>
        </div>
        <div id="upload-status" style="font-size:0.75rem;margin-top:var(--cds-sp-03);display:none"></div>
      </div>
    </div>


  </div><!-- /left -->

  <!-- ── Right: Chat + Feed ───────────────────────────────────── -->
  <div>

    <!-- Chat -->
    <div class="card">
      <div class="card-header">
        <h2>💬 Ask About Your Documents</h2>
        <button id="clear-active-btn" class="btn btn-sm btn-ghost" style="margin-left:auto;display:none" onclick="clearActiveFile()">✕ Clear focus</button>
      </div>
      <div class="card-body">
        <!-- Active file banner -->
        <div id="active-file-banner" style="display:none;background:var(--cds-support-info-bg);border-left:3px solid var(--cds-interactive);padding:var(--cds-sp-03) var(--cds-sp-05);margin-bottom:var(--cds-sp-04);align-items:center;gap:var(--cds-sp-04)">
          <span style="font-size:0.75rem;color:var(--cds-text-secondary)">Talking to:</span>
          <span id="active-file-name" style="font-size:0.8125rem;font-weight:600;color:var(--cds-text-primary);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>
          <button onclick="clearActiveFile()" style="background:none;border:none;color:var(--cds-link-primary);cursor:pointer;font-size:0.75rem;padding:0">✕ ask all docs</button>
        </div>
        <div class="chips">
          <span class="chip" onclick="ask(this.textContent)">What were today's key themes?</span>
          <span class="chip" onclick="ask(this.textContent)">Summarize everything from this week</span>
          <span class="chip" onclick="ask(this.textContent)">What action items were mentioned?</span>
          <span class="chip" onclick="ask(this.textContent)">Which documents had urgent items?</span>
          <span class="chip" onclick="ask(this.textContent)">List all decisions made</span>
          <span class="chip" onclick="ask(this.textContent)">Compare the last two documents</span>
          <span class="chip" onclick="ask(this.textContent)">What were the main topics?</span>
          <span class="chip" onclick="ask(this.textContent)">Any financial figures mentioned?</span>
        </div>
        <div class="chat-row">
          <input class="chat-input" id="chat-input" type="text"
            placeholder="Ask anything about your summarized documents…"
            onkeydown="if(event.key==='Enter')ask()">
          <button class="chat-send" id="chat-send" onclick="ask()">Ask</button>
        </div>
        <div class="chat-result" id="chat-result"></div>
      </div>
    </div>

    <!-- Summary feed -->
    <div class="card">
      <div class="card-header">
        <h2>📋 Summary Feed</h2>
        <span id="sum-count" style="font-size:0.75rem;color:var(--cds-text-helper);margin-left:auto"></span>
        <button class="btn btn-sm btn-ghost" style="margin-left:var(--cds-sp-03)" onclick="loadSummaries()">↺ Refresh</button>
      </div>
      <div class="card-body" id="feed-body">
        <div class="empty-state">No summaries yet — upload a file above.</div>
      </div>
    </div>

  </div><!-- /right -->
</div>

<script>
let _activeFile = null;  // { filename, id }

function setActiveFile(filename, id) {
  _activeFile = { filename, id };
  const banner = document.getElementById('active-file-banner');
  banner.style.display = 'flex';
  document.getElementById('active-file-name').textContent = filename;
  document.getElementById('clear-active-btn').style.display = 'inline-block';
  document.getElementById('chat-input').placeholder = `Ask about "${filename}"…`;
  // highlight the active entry
  document.querySelectorAll('.sum-entry').forEach(el => el.classList.remove('sum-active'));
  const match = [...document.querySelectorAll('.sum-entry')].find(
    el => el.dataset.filename === filename
  );
  if (match) match.classList.add('sum-active');
}

function clearActiveFile() {
  _activeFile = null;
  document.getElementById('active-file-banner').style.display = 'none';
  document.getElementById('clear-active-btn').style.display = 'none';
  document.getElementById('chat-input').placeholder = 'Ask anything about your summarized documents…';
  document.querySelectorAll('.sum-entry').forEach(el => el.classList.remove('sum-active'));
}

// ── Init ───────────────────────────────────────────────────────────
async function init() {
  await loadSummaries();
  setInterval(loadSummaries, 10000);
}

// ── Upload ──────────────────────────────────────────────────────────
async function uploadFile(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  const status = document.getElementById('upload-status');
  status.style.display = 'block';
  status.textContent = `Uploading ${file.name}…`;
  try {
    const res = await fetch('/upload', { method: 'POST', body: fd });
    const data = await res.json();
    status.textContent = `⏳ ${file.name} queued — processing…`;
    status.style.color = 'var(--cds-link-primary)';
    _pollForFile(data.filename, status);
  } catch(e) {
    status.style.color = 'var(--cds-support-error)';
    status.textContent = 'Upload failed: ' + e.message;
  }
}

async function _pollForFile(filename, statusEl) {
  const maxWait = 10 * 60 * 1000; // 10 minutes
  const interval = 5000;
  const start = Date.now();
  while (Date.now() - start < maxWait) {
    await new Promise(r => setTimeout(r, interval));
    try {
      const summaries = await fetch('/summaries').then(r => r.json());
      const match = summaries.find(s => s.filename === filename);
      if (match) {
        renderFeed(summaries);
        statusEl.style.color = 'var(--cds-support-success)';
        statusEl.textContent = `✓ ${filename} ready`;
        setTimeout(() => { statusEl.style.display = 'none'; }, 3000);
        return;
      }
    } catch(e) {}
  }
  statusEl.style.color = 'var(--cds-support-error)';
  statusEl.textContent = `Processing ${filename} is taking longer than expected.`;
}

function handleDrop(event) {
  event.preventDefault();
  document.getElementById('drop-zone').classList.remove('drag-over');
  const file = event.dataTransfer.files[0];
  if (file) uploadFile(file);
}

// ── Summaries ───────────────────────────────────────────────────────
async function loadSummaries() {
  try {
    const entries = await fetch('/summaries').then(r => r.json());
    renderFeed(entries);
  } catch(e) {}
}

function fmtTime(iso) {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}
function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function renderFeed(entries) {
  const body = document.getElementById('feed-body');
  document.getElementById('sum-count').textContent = entries.length + ' summaries';
  if (!entries.length) {
    body.innerHTML = '<div class="empty-state">No summaries yet — drop a file above or into the inbox folder.</div>';
    return;
  }
  body.innerHTML = entries.map((e, i) => `
    <div class="sum-entry" data-filename="${esc(e.filename)}" data-id="${e.id}">
      <div class="sum-header">
        <span class="sum-filename" style="cursor:pointer" onclick="setActiveFile('${esc(e.filename)}','${e.id}')" title="Focus chat on this file">${esc(e.filename)}</span>
        <span class="sum-wc">${e.word_count}w</span>
        <span class="sum-time">${fmtTime(e.created_at)}</span>
        <button class="btn btn-sm btn-ghost" style="margin-left:6px" onclick="setActiveFile('${esc(e.filename)}','${e.id}')">Focus</button>
        <span id="si-${i}" style="font-size:0.75rem;color:var(--cds-text-helper);margin-left:4px;cursor:pointer" onclick="toggleSum('se-${i}','si-${i}')">▸</span>
      </div>
      <div class="sum-body" id="se-${i}">${esc(e.summary)}</div>
    </div>`).join('');
}

function toggleSum(bodyId, iconId) {
  const body = document.getElementById(bodyId);
  const icon = document.getElementById(iconId);
  const open = body.classList.toggle('open');
  icon.textContent = open ? '▾' : '▸';
}

// ── Chat ─────────────────────────────────────────────────────────────
async function ask(question) {
  const inp = document.getElementById('chat-input');
  const res = document.getElementById('chat-result');
  const btn = document.getElementById('chat-send');
  const q   = question || inp.value.trim();
  if (!q) return;
  inp.value = '';
  btn.disabled = true; btn.textContent = 'Thinking…';
  res.className = 'chat-result vis';
  const focusLabel = _activeFile ? ` [${_activeFile.filename}]` : '';
  res.textContent = `Asking agent${focusLabel}…`;
  try {
    const body = { question: q };
    if (_activeFile) body.filename = _activeFile.filename;
    const r = await fetch('/ask', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body) });
    const d = await r.json();
    res.textContent = d.answer || d.error || '(no response)';
  } catch(e) { res.textContent = 'Error: ' + e.message; }
  btn.disabled = false; btn.textContent = 'Ask';
}

init();
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("Drop Summarizer")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drop Summarizer — docs & images web UI")
    parser.add_argument("--port",     type=int, default=28794)
    parser.add_argument("--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model",    "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    print(f"\n  Drop Summarizer (docs + images)  →  http://127.0.0.1:{args.port}\n")
    _web(args.port)
