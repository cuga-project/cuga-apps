"""
Voice Journal — record, transcribe, reflect
============================================

Record audio in-browser or upload voice files. The agent transcribes each
entry with faster-whisper, generates a title, summary, and tags, then saves
to SQLite + dated Markdown files.

Browse your timeline, play back recordings, edit transcripts, and search.

Run:
    python main.py
    python main.py --port 28799
    python main.py --provider anthropic

Then open: http://127.0.0.1:28799

Environment variables:
    LLM_PROVIDER    rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL       model override
    WHISPER_MODEL   faster-whisper model size: tiny|base|small|medium (default: base)
"""

import argparse
import asyncio
import logging
import mimetypes
import os
import shutil
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

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

AUDIO_DIR       = _DIR / "journal" / "audio"
WHISPER_MODEL   = os.getenv("WHISPER_MODEL", "base")
SUPPORTED_AUDIO = {".mp3", ".wav", ".m4a", ".webm", ".ogg", ".flac", ".mp4", ".mov", ".mkv"}


# ---------------------------------------------------------------------------
# Agent tools
# ---------------------------------------------------------------------------

def _make_tools():
    import json as _json
    from langchain_core.tools import tool
    from store import save_entry, list_entries as _list, list_dates as _dates
    from _mcp_bridge import load_tools

    # transcribe_audio is delegated to mcp-local. The 3 journal-state tools below
    # (save_journal_entry, list_entries, list_dates) mutate this process's
    # SQLite store so they stay inline.
    local_tools = load_tools(["local"])

    @tool
    def save_journal_entry(
        body: str,
        title: str = "Journal Entry",
        summary: str = "",
        tags: str = "",
        source: str = "text",
        entry_date: str | None = None,
        entry_id: int | None = None,
    ) -> str:
        """
        Save or update a journal entry.

        For voice entries: pass entry_id to update the pending placeholder.
        For text entries typed in chat: omit entry_id (creates a new entry).

        Args:
            body:       Full journal entry text (cleaned transcript or written entry).
            title:      3-7 word title capturing the main theme.
            summary:    1-2 sentence summary.
            tags:       Comma-separated tags: one mood tag + 1-3 topic tags.
            source:     "text" | "voice"
            entry_date: ISO date YYYY-MM-DD. Defaults to today.
            entry_id:   If provided, update the pending entry with this ID.
        """
        result = save_entry(
            body=body, title=title, summary=summary, tags=tags,
            source=source, entry_date=entry_date, entry_id=entry_id,
        )
        return _json.dumps(result)

    @tool
    def list_entries(
        entry_date: str | None = None,
        since_date: str | None = None,
        until_date: str | None = None,
        limit: int = 10,
    ) -> str:
        """
        Return journal entries as JSON.

        Args:
            entry_date: Filter to a specific date (YYYY-MM-DD).
            since_date: Entries on or after this date.
            until_date: Entries on or before this date.
            limit:      Max entries to return.
        """
        return _json.dumps(_list(
            entry_date=entry_date, since_date=since_date,
            until_date=until_date, limit=limit,
        ))

    @tool
    def list_dates() -> str:
        """Return all dates that have journal entries, most recent first."""
        return _json.dumps(_dates())

    return [*local_tools, save_journal_entry, list_entries, list_dates]


_SYSTEM = """\
# Voice Journal Assistant

You are a thoughtful personal journal assistant. You help users capture and
reflect on their thoughts through voice recordings and written entries.

---

## When processing a voice entry

The message will include an **Entry ID** and an **Audio file path**.

1. Call `transcribe_audio(file_path)` to get the verbatim transcript.
2. Clean it up: fix punctuation, remove filler words ("um", "uh", "like"),
   add paragraph breaks where natural.
3. Extract a **title** (3–7 words, sentence-case, capturing the main theme).
4. Write a **summary** (1–2 sentences).
5. Identify **2–4 tags**: one mood tag + topic tags (comma-separated).
   - Mood: `grateful`, `reflective`, `anxious`, `excited`, `tired`, `happy`,
     `frustrated`, `calm`, `hopeful`, `energized`
   - Topics: `work`, `family`, `health`, `ideas`, `goals`, `travel`,
     `relationships`, `finances`, `creativity`, etc.
6. Call `save_journal_entry(entry_id=<given id>, body=<cleaned transcript>,
   title=<title>, summary=<summary>, tags=<comma,separated>, source="voice")`.
7. Confirm with: "✓ Saved: {title}"

---

## When the user types a journal entry directly

Format it as clean prose. Call `save_journal_entry(body=..., title=...,
summary=..., tags=..., source="text")` — no `entry_id`.

---

## When the user asks to read or search entries

Call `list_entries` (filtered by date if specified) and present clearly.
For "today" use today's date; for "last week" use `since_date`.

## When the user asks for reflection or themes

Call `list_entries` for recent entries, notice patterns, and offer a
thoughtful summary. Write like a thoughtful friend, not a report.

---

## Tone

- Warm, reflective, concise.
- Use the user's own words when possible.
- Never add unsolicited advice unless asked.
- Never say "I cannot" or "as an AI".

## Source labels

- Text typed directly → `source="text"`
- Voice note recorded/uploaded → `source="voice"`
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
# Background processing — agent handles transcription + save
# ---------------------------------------------------------------------------

async def _process_entry(agent, entry_id: int, audio_path: str) -> None:
    try:
        await agent.invoke(
            f"Process this voice journal entry.\n"
            f"Entry ID: {entry_id}\n"
            f"Audio file: {audio_path}\n\n"
            f"Call transcribe_audio to get the transcript, then call "
            f"save_journal_entry with entry_id={entry_id} to save it.",
            thread_id=f"journal-{entry_id}",
        )
        log.info("Entry %d processed", entry_id)
    except Exception as exc:
        log.error("Processing error for entry %d: %s", entry_id, exc)
        from store import update_entry
        update_entry(entry_id, title="Error processing audio", status="error")


# ---------------------------------------------------------------------------
# Inbox watcher — picks up dropped audio files
# ---------------------------------------------------------------------------

_watcher_status = {"running": False, "processed": 0, "last_check": None}


async def _inbox_watcher(agent) -> None:
    from store import create_pending_entry
    _watcher_status["running"] = True
    inbox     = _DIR / "inbox"
    processed = inbox / "processed"
    inbox.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)

    while True:
        _watcher_status["last_check"] = datetime.now(timezone.utc).isoformat()
        files = [
            f for f in inbox.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_AUDIO
        ]
        for fpath in files:
            dest = processed / fpath.name
            try:
                shutil.move(str(fpath), str(dest))
            except Exception as exc:
                log.warning("Move failed %s: %s", fpath.name, exc)
                continue
            log.info("Inbox audio: %s", fpath.name)
            entry = create_pending_entry(str(dest), source="voice")
            asyncio.create_task(_process_entry(agent, entry["id"], str(dest)))
            _watcher_status["processed"] += 1
        await asyncio.sleep(20)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AskReq(BaseModel):
    question: str


class UpdateReq(BaseModel):
    title: str | None = None
    body:  str | None = None
    tags:  str | None = None


# ---------------------------------------------------------------------------
# Web app
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn
    from store import (
        init_db, list_entries, get_entry, update_entry,
        delete_entry, search_entries, create_pending_entry,
    )

    init_db()
    agent = make_agent()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        asyncio.create_task(_inbox_watcher(agent))
        log.info("Voice Journal started on port %d", port)
        yield

    app = FastAPI(title="Voice Journal", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    # -- Record (MediaRecorder blob from browser) ----------------------------
    @app.post("/record")
    async def api_record(file: UploadFile = File(...)):
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        ext   = Path(file.filename or "audio.webm").suffix.lower() or ".webm"
        dest  = AUDIO_DIR / f"{uuid.uuid4().hex[:10]}{ext}"
        dest.write_bytes(await file.read())
        entry = create_pending_entry(str(dest), source="record")
        asyncio.create_task(_process_entry(agent, entry["id"], str(dest)))
        return entry

    # -- Upload (audio file from file picker) --------------------------------
    @app.post("/upload")
    async def api_upload(file: UploadFile = File(...)):
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        ext = Path(file.filename or "audio.mp3").suffix.lower()
        if ext not in SUPPORTED_AUDIO:
            return JSONResponse({"error": f"Unsupported format: {ext}"}, status_code=400)
        dest  = AUDIO_DIR / f"{uuid.uuid4().hex[:10]}{ext}"
        dest.write_bytes(await file.read())
        entry = create_pending_entry(str(dest), source="upload")
        asyncio.create_task(_process_entry(agent, entry["id"], str(dest)))
        return entry

    # -- Audio streaming (range-request support for HTML5 player) -----------
    @app.get("/audio/{entry_id}")
    async def api_audio(entry_id: str, request: Request):
        row = get_entry(entry_id)
        if not row:
            return JSONResponse({"error": "not found"}, status_code=404)
        path = Path(row["audio_path"])
        if not path.exists():
            return JSONResponse({"error": "audio file not found"}, status_code=404)
        file_size = path.stat().st_size
        mime      = mimetypes.guess_type(str(path))[0] or "audio/webm"
        rng       = request.headers.get("range")

        if rng:
            parts = rng.replace("bytes=", "").split("-")
            start = int(parts[0])
            end   = int(parts[1]) if parts[1] else file_size - 1
            clen  = end - start + 1

            def _iter_range():
                with open(path, "rb") as f:
                    f.seek(start)
                    rem = clen
                    while rem > 0:
                        chunk = f.read(min(65536, rem))
                        if not chunk:
                            break
                        rem -= len(chunk)
                        yield chunk

            return StreamingResponse(_iter_range(), status_code=206, headers={
                "Content-Range":  f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges":  "bytes",
                "Content-Length": str(clen),
                "Content-Type":   mime,
            })

        def _iter_full():
            with open(path, "rb") as f:
                while chunk := f.read(65536):
                    yield chunk

        return StreamingResponse(_iter_full(), headers={
            "Content-Length": str(file_size),
            "Accept-Ranges":  "bytes",
            "Content-Type":   mime,
        })

    # -- Entries CRUD --------------------------------------------------------
    @app.get("/entries")
    async def api_list(limit: int = 100):
        return list_entries(limit=limit)

    @app.get("/entries/{entry_id}")
    async def api_get(entry_id: str):
        row = get_entry(entry_id)
        if not row:
            return JSONResponse({"error": "not found"}, status_code=404)
        return row

    @app.put("/entries/{entry_id}")
    async def api_update(entry_id: str, req: UpdateReq):
        updates = {}
        if req.title is not None: updates["title"] = req.title
        if req.body  is not None: updates["body"]  = req.body
        if req.tags  is not None: updates["tags"]  = req.tags
        if updates:
            update_entry(entry_id, **updates)
        return {"ok": True}

    @app.delete("/entries/{entry_id}")
    async def api_delete(entry_id: str):
        row = get_entry(entry_id)
        if not row:
            return JSONResponse({"error": "not found"}, status_code=404)
        if row.get("audio_path"):
            try:
                Path(row["audio_path"]).unlink(missing_ok=True)
            except Exception:
                pass
        delete_entry(entry_id)
        return {"ok": True}

    # -- Search --------------------------------------------------------------
    @app.get("/search")
    async def api_search(q: str = ""):
        if not q.strip():
            return []
        return search_entries(q.strip())

    # -- Chat / Q&A ----------------------------------------------------------
    @app.post("/ask")
    async def api_ask(req: AskReq):
        try:
            result = await agent.invoke(req.question, thread_id="chat")
            return {"answer": result.answer}
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/watcher/status")
    async def api_watcher():
        return _watcher_status

    @app.get("/", response_class=HTMLResponse)
    async def ui():
        return HTMLResponse(_HTML)

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Embedded UI
# ---------------------------------------------------------------------------

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Voice Journal</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:#0d0d0f;color:#e2e8f0;height:100vh;display:flex;
  flex-direction:column;overflow:hidden}

/* Header */
header{background:#111113;border-bottom:1px solid #1e1e24;padding:12px 20px;
  display:flex;align-items:center;gap:10px;flex-shrink:0}
header h1{font-size:15px;font-weight:700;letter-spacing:-.2px}
header h1 span{color:#f59e0b}
.hdr-right{margin-left:auto;display:flex;align-items:center;gap:10px}
.search-wrap{position:relative}
.search-wrap input{background:#1a1a1f;border:1px solid #2a2a35;border-radius:18px;
  padding:5px 12px 5px 30px;font-size:12px;color:#e2e8f0;width:200px;outline:none}
.search-wrap input:focus{border-color:#f59e0b}
.search-icon{position:absolute;left:10px;top:50%;transform:translateY(-50%);
  font-size:12px;color:#4b5563;pointer-events:none}

/* Layout */
.layout{display:grid;grid-template-columns:272px 1fr;flex:1;overflow:hidden}

/* ── Left panel ─────────────────────────────────── */
.left{border-right:1px solid #1e1e24;display:flex;flex-direction:column;overflow:hidden}

/* Record section */
.record-section{padding:20px 14px 16px;border-bottom:1px solid #1e1e24;
  display:flex;flex-direction:column;align-items:center;gap:10px}
#record-btn{width:64px;height:64px;border-radius:50%;border:2px solid #2a2a35;
  background:#1c1c22;color:#e2e8f0;font-size:22px;cursor:pointer;transition:all .2s}
#record-btn:hover{background:#242430;transform:scale(1.05)}
#record-btn.recording{background:#ef4444;border-color:#dc2626}
#record-btn.recording:hover{background:#dc2626}
#record-timer{font-size:16px;font-weight:600;color:#ef4444;
  font-variant-numeric:tabular-nums;letter-spacing:.5px}
#record-label{font-size:11px;color:#6b7280;text-align:center}
#file-input{padding:4px 12px;border-radius:16px;border:1px solid #2a2a35;
  background:transparent;color:#9ca3af;font-size:11px;cursor:pointer}
#file-input:hover{border-color:#f59e0b;color:#f59e0b}

/* Timeline */
.timeline{flex:1;overflow-y:auto;padding:6px}
.timeline::-webkit-scrollbar{width:3px}
.timeline::-webkit-scrollbar-thumb{background:#2a2a35;border-radius:2px}
.date-label{font-size:10px;font-weight:600;color:#374151;text-transform:uppercase;
  letter-spacing:.8px;padding:8px 8px 4px}
.entry-card{padding:9px 10px;border-radius:7px;cursor:pointer;margin-bottom:1px;
  transition:background .12s;border:1px solid transparent}
.entry-card:hover{background:#141418}
.entry-card.active{background:#171720;border-color:#2a2a35}
.ec-title{font-size:12px;font-weight:500;color:#c5cae9;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:3px}
.entry-card.active .ec-title{color:#f5f5f5}
.ec-meta{display:flex;align-items:center;gap:5px}
.ec-time{font-size:10px;color:#374151}
.ec-words{font-size:10px;color:#374151}
.ec-tag{font-size:10px;padding:1px 6px;border-radius:6px;
  background:#1c1a0e;color:#d97706;border:1px solid #2e2208}
.ec-dot{width:5px;height:5px;border-radius:50%;background:#f59e0b;
  animation:dot-blink 1s ease-in-out infinite;flex-shrink:0}
@keyframes dot-blink{0%,100%{opacity:1}50%{opacity:.2}}
.no-entries{font-size:12px;color:#374151;text-align:center;padding:24px 8px}

/* ── Right panel ─────────────────────────────────── */
.right{display:flex;flex-direction:column;overflow:hidden;position:relative}

/* Empty / chat view */
#chat-view{flex:1;overflow-y:auto;display:flex;flex-direction:column;padding:24px 28px;gap:14px}
#chat-view::-webkit-scrollbar{width:3px}
#chat-view::-webkit-scrollbar-thumb{background:#2a2a35;border-radius:2px}
.chat-hero{display:flex;flex-direction:column;align-items:center;gap:8px;
  padding:32px 0 20px;color:#374151}
.chat-hero .icon{font-size:40px}
.chat-hero p{font-size:14px;color:#4b5563}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{padding:5px 12px;border-radius:14px;font-size:12px;
  background:#141418;border:1px solid #1e1e24;color:#9ca3af;
  cursor:pointer;transition:all .15s}
.chip:hover{border-color:#f59e0b;color:#f59e0b}
.chat-row{display:flex;gap:8px;margin-top:auto;padding-top:12px}
.chat-input{flex:1;padding:8px 12px;border-radius:8px;font-size:13px;
  background:#111115;border:1px solid #1e1e24;color:#e2e8f0;outline:none}
.chat-input:focus{border-color:#f59e0b}
.chat-send{padding:8px 16px;border-radius:8px;font-size:13px;
  cursor:pointer;border:none;background:#f59e0b;color:#000;font-weight:600}
.chat-send:hover{background:#d97706}
.chat-send:disabled{background:#1e1e24;color:#374151;cursor:default}
.chat-result{padding:12px 14px;border-radius:8px;background:#111115;
  border:1px solid #1e1e24;font-size:13px;line-height:1.7;color:#d1d5db;
  white-space:pre-wrap;display:none}
.chat-result.vis{display:block}

/* Entry detail view */
#detail-view{flex:1;overflow-y:auto;padding:24px 28px;display:none;flex-direction:column;gap:16px}
#detail-view::-webkit-scrollbar{width:3px}
#detail-view::-webkit-scrollbar-thumb{background:#2a2a35;border-radius:2px}
#detail-view.vis{display:flex}
.detail-header{display:flex;align-items:flex-start;gap:10px}
.detail-title-wrap{flex:1}
.detail-title{font-size:20px;font-weight:600;color:#f5f5f5;line-height:1.3;
  border:none;background:transparent;width:100%;outline:none;
  font-family:inherit;cursor:text}
.detail-title:focus{border-bottom:1px solid #2a2a35}
.detail-date{font-size:11px;color:#4b5563;margin-top:4px}
.icon-btn{width:30px;height:30px;border-radius:7px;border:1px solid #1e1e24;
  background:transparent;color:#4b5563;font-size:13px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;transition:all .15s}
.icon-btn:hover{border-color:#f59e0b;color:#f59e0b}
.icon-btn.danger:hover{border-color:#ef4444;color:#ef4444}

/* Audio player */
.audio-wrap{background:#111115;border:1px solid #1e1e24;
  border-radius:9px;padding:12px 16px}
audio{width:100%;height:34px}

/* Summary */
.summary-block{border-left:3px solid #f59e0b;border-radius:0 7px 7px 0;
  padding:10px 14px;background:#111115;font-size:13px;line-height:1.7;
  color:#b0b8c8;font-style:italic}

/* Tags */
.tags-row{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.tag-pill{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;
  border-radius:10px;font-size:11px;background:#1a1a22;
  color:#9ca3af;border:1px solid #2a2a35}
.tag-pill.mood{background:#1c1a0e;color:#f59e0b;border-color:#2e2208}
.tag-del{cursor:pointer;color:#4b5563;font-size:11px;line-height:1}
.tag-del:hover{color:#ef4444}
.add-tag{padding:3px 10px;border-radius:10px;font-size:11px;
  background:transparent;color:#374151;border:1px dashed #2a2a35;
  cursor:pointer;transition:all .15s}
.add-tag:hover{border-color:#f59e0b;color:#f59e0b}

/* Transcript */
.section-label{font-size:10px;font-weight:600;color:#374151;
  text-transform:uppercase;letter-spacing:.8px}
.transcript-area{width:100%;min-height:140px;padding:12px;border-radius:8px;
  font-size:14px;line-height:1.8;color:#d1d5db;background:transparent;
  border:1px solid transparent;outline:none;resize:vertical;
  font-family:inherit;transition:border-color .15s}
.transcript-area:focus{border-color:#1e1e24;background:#0d0d11}

/* Save bar */
.save-bar{padding:10px 28px;border-top:1px solid #1e1e24;flex-shrink:0;
  display:none;align-items:center;gap:10px;background:#0d0d0f}
.save-bar.vis{display:flex}
.save-btn{padding:6px 18px;border-radius:7px;border:none;
  background:#f59e0b;color:#000;font-size:12px;font-weight:600;
  cursor:pointer;transition:background .15s}
.save-btn:hover{background:#d97706}
.save-status{font-size:11px;color:#4b5563}
.save-status.ok{color:#4ade80}

/* Processing overlay */
#processing-state{flex:1;display:none;flex-direction:column;
  align-items:center;justify-content:center;gap:10px;color:#4b5563;font-size:13px}
#processing-state.vis{display:flex}
.spinner{width:24px;height:24px;border:2px solid #1e1e24;
  border-top-color:#f59e0b;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>

<header>
  <h1>🎙 Voice <span>Journal</span></h1>
  <div class="hdr-right">
    <div class="search-wrap">
      <span class="search-icon">⌕</span>
      <input type="text" id="search-input" placeholder="Search entries…"
             oninput="onSearch(this.value)" autocomplete="off">
    </div>
  </div>
</header>

<div class="layout">

  <!-- ── Left panel ─────────────────────── -->
  <div class="left">
    <div class="record-section">
      <button id="record-btn" type="button" onclick="toggleRecord()" title="Record">🎙</button>
      <div id="record-timer" style="display:none;font-size:16px" class="ec-time"></div>
      <div id="record-label">Tap to record</div>
      <input type="file" id="file-input"
             accept=".mp3,.wav,.m4a,.webm,.ogg,.flac,.mp4,.mov,.mkv"
             onchange="uploadFile(this.files[0])">
    </div>
    <div class="timeline" id="timeline">
      <div class="no-entries">No entries yet</div>
    </div>
  </div>

  <!-- ── Right panel ────────────────────── -->
  <div class="right">

    <!-- Chat / empty view -->
    <div id="chat-view">
      <div class="chat-hero">
        <div class="icon">🎙</div>
        <p>Record a thought or ask about your journal</p>
      </div>
      <div class="chips">
        <span class="chip" onclick="ask(this.textContent)">What did I write about this week?</span>
        <span class="chip" onclick="ask(this.textContent)">How have I been feeling lately?</span>
        <span class="chip" onclick="ask(this.textContent)">What goals did I mention?</span>
        <span class="chip" onclick="ask(this.textContent)">Summarize last month</span>
        <span class="chip" onclick="ask(this.textContent)">What themes keep coming up?</span>
        <span class="chip" onclick="ask(this.textContent)">Show entries tagged work</span>
      </div>
      <div class="chat-result" id="chat-result"></div>
      <div class="chat-row">
        <input class="chat-input" id="chat-input" type="text"
               placeholder="Ask about your journal or type an entry…"
               onkeydown="if(event.key==='Enter')ask()">
        <button class="chat-send" id="chat-send" onclick="ask()">Ask</button>
      </div>
    </div>

    <!-- Entry detail view -->
    <div id="detail-view">
      <div class="detail-header">
        <div class="detail-title-wrap">
          <input class="detail-title" id="detail-title" type="text" placeholder="Entry title…">
          <div class="detail-date" id="detail-date"></div>
        </div>
        <button class="icon-btn" onclick="showChat()" title="Back">←</button>
        <button class="icon-btn danger" onclick="deleteEntry()" title="Delete">🗑</button>
      </div>
      <div class="audio-wrap" id="audio-wrap" style="display:none">
        <audio id="audio-player" controls preload="none"></audio>
      </div>
      <div class="summary-block" id="detail-summary" style="display:none"></div>
      <div class="tags-row" id="tags-row"></div>
      <div class="section-label">Transcript</div>
      <textarea class="transcript-area" id="detail-body"
                placeholder="Transcript will appear after processing…"></textarea>
    </div>

    <!-- Processing state -->
    <div id="processing-state">
      <div class="spinner"></div>
      <span>Transcribing…</span>
    </div>

    <!-- Save bar -->
    <div class="save-bar" id="save-bar">
      <button class="save-btn" onclick="saveEntry()">Save changes</button>
      <span class="save-status" id="save-status"></span>
    </div>

  </div>
</div>

<script>
let _entries    = [];
let _selected   = null;
let _tags       = [];
let _recorder   = null;
let _chunks     = [];
let _recSecs    = 0;
let _recIval    = null;
let _pollTimer  = null;
let _searchMode = false;
let _searchTo   = null;

const MOOD_TAGS = new Set([
  'grateful','reflective','anxious','excited','tired','happy',
  'frustrated','calm','hopeful','energized','melancholy','neutral'
]);

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  await loadEntries();
  setInterval(loadEntries, 12000);
}

// ---------------------------------------------------------------------------
// Entries
// ---------------------------------------------------------------------------

async function loadEntries() {
  try {
    const data = await fetch('/entries').then(r => r.json());
    _entries = data;
    if (!_searchMode) renderTimeline(data);
    // Re-render active card highlight
    if (_selected) {
      document.querySelectorAll('.entry-card').forEach(el => {
        el.classList.toggle('active', el.dataset.id == _selected.id);
      });
    }
  } catch(e) {}
}

function renderTimeline(entries) {
  const el = document.getElementById('timeline');
  if (!entries.length) {
    el.innerHTML = '<div class="no-entries">No entries yet — tap to record!</div>';
    return;
  }
  const groups = {};
  for (const e of entries) {
    const d   = new Date(e.created_at);
    const key = d.toLocaleDateString('en-US', {weekday:'long', month:'short', day:'numeric'});
    (groups[key] = groups[key] || []).push(e);
  }
  let html = '';
  for (const [date, items] of Object.entries(groups)) {
    html += '<div class="date-label">' + esc(date) + '</div>';
    for (const e of items) {
      const tags   = (e.tags || '').split(',').map(t => t.trim()).filter(Boolean);
      const mood   = tags.find(t => MOOD_TAGS.has(t.toLowerCase()));
      const isAct  = _selected && _selected.id == e.id;
      const time   = new Date(e.created_at).toLocaleTimeString('en-US',
                       {hour:'numeric', minute:'2-digit'});
      html += '<div class="entry-card' + (isAct ? ' active' : '') +
              '" data-id="' + e.id + '" onclick="selectEntry(' + e.id + ')">' +
              '<div class="ec-title">' + esc(e.title || 'Processing…') + '</div>' +
              '<div class="ec-meta">' +
              '<span class="ec-time">' + time + '</span>' +
              (e.status === 'processing' ? '<span class="ec-dot"></span>' : '') +
              (e.word_count ? '<span class="ec-words">' + e.word_count + 'w</span>' : '') +
              (mood ? '<span class="ec-tag">' + esc(mood) + '</span>' : '') +
              '</div></div>';
    }
  }
  el.innerHTML = html;
}

async function selectEntry(id) {
  _selected = {id};
  renderTimeline(_entries);
  try {
    const entry = await fetch('/entries/' + id).then(r => r.json());
    _selected = entry;
    if (entry.status === 'processing') {
      showProcessing();
      schedulePoll(id);
    } else {
      showDetail(entry);
    }
  } catch(e) {}
}

function showDetail(entry) {
  document.getElementById('chat-view').style.display    = 'none';
  document.getElementById('processing-state').className = '';
  document.getElementById('detail-view').className      = 'vis';
  document.getElementById('save-bar').className         = 'save-bar vis';

  document.getElementById('detail-title').value = entry.title || '';
  document.getElementById('detail-date').textContent =
    new Date(entry.created_at).toLocaleString('en-US', {
      weekday:'long', year:'numeric', month:'long',
      day:'numeric', hour:'numeric', minute:'2-digit'
    });

  // Audio player
  const audioWrap   = document.getElementById('audio-wrap');
  const audioPlayer = document.getElementById('audio-player');
  if (entry.audio_path) {
    audioWrap.style.display = 'block';
    audioPlayer.src         = '/audio/' + entry.id;
  } else {
    audioWrap.style.display = 'none';
    audioPlayer.src         = '';
  }

  // Summary
  const summaryEl = document.getElementById('detail-summary');
  if (entry.summary) {
    summaryEl.textContent    = entry.summary;
    summaryEl.style.display  = 'block';
  } else {
    summaryEl.style.display  = 'none';
  }

  // Tags
  _tags = (entry.tags || '').split(',').map(t => t.trim()).filter(Boolean);
  renderTags();

  // Transcript
  document.getElementById('detail-body').value = entry.body || '';

  document.getElementById('save-status').textContent = '';
  document.getElementById('save-status').className   = 'save-status';
}

function showProcessing() {
  document.getElementById('chat-view').style.display    = 'none';
  document.getElementById('detail-view').className      = '';
  document.getElementById('processing-state').className = 'vis';
  document.getElementById('save-bar').className         = 'save-bar';
}

function showChat() {
  _selected = null;
  document.querySelectorAll('.entry-card').forEach(el => el.classList.remove('active'));
  document.getElementById('detail-view').className      = '';
  document.getElementById('processing-state').className = '';
  document.getElementById('save-bar').className         = 'save-bar';
  document.getElementById('chat-view').style.display    = 'flex';
}

function schedulePoll(id) {
  clearTimeout(_pollTimer);
  _pollTimer = setTimeout(() => pollEntry(id), 2000);
}

async function pollEntry(id) {
  try {
    const entry = await fetch('/entries/' + id).then(r => r.json());
    if (entry.status === 'processing') {
      _pollTimer = setTimeout(() => pollEntry(id), 2000);
    } else {
      _selected = entry;
      const idx  = _entries.findIndex(e => e.id == id);
      if (idx >= 0) Object.assign(_entries[idx], entry);
      renderTimeline(_entries);
      showDetail(entry);
    }
  } catch(e) {
    _pollTimer = setTimeout(() => pollEntry(id), 3000);
  }
}

// ---------------------------------------------------------------------------
// Tags
// ---------------------------------------------------------------------------

function renderTags() {
  const row  = document.getElementById('tags-row');
  let   html = _tags.map((t, i) =>
    '<span class="tag-pill' + (MOOD_TAGS.has(t.toLowerCase()) ? ' mood' : '') + '">' +
    esc(t) + '<span class="tag-del" onclick="removeTag(' + i + ')">x</span></span>'
  ).join('');
  html += '<button class="add-tag" onclick="addTag()">+ tag</button>';
  row.innerHTML = html;
}

function removeTag(i) { _tags.splice(i, 1); renderTags(); }

function addTag() {
  const v = prompt('Add tag (e.g. grateful, work, family):');
  if (v && v.trim()) { _tags.push(v.trim().toLowerCase()); renderTags(); }
}

// ---------------------------------------------------------------------------
// Save / Delete
// ---------------------------------------------------------------------------

async function saveEntry() {
  if (!_selected) return;
  const btn = document.querySelector('.save-btn');
  const sts = document.getElementById('save-status');
  btn.disabled = true;
  try {
    await fetch('/entries/' + _selected.id, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        title: document.getElementById('detail-title').value,
        body:  document.getElementById('detail-body').value,
        tags:  _tags.join(', '),
      }),
    });
    sts.textContent = 'Saved';
    sts.className   = 'save-status ok';
    setTimeout(() => { sts.textContent = ''; sts.className = 'save-status'; }, 2000);
    const idx = _entries.findIndex(e => e.id == _selected.id);
    if (idx >= 0) _entries[idx].title = document.getElementById('detail-title').value;
    renderTimeline(_entries);
  } catch(e) { sts.textContent = 'Error saving'; }
  btn.disabled = false;
}

async function deleteEntry() {
  if (!_selected || !confirm('Delete this entry? This cannot be undone.')) return;
  try {
    await fetch('/entries/' + _selected.id, {method: 'DELETE'});
    _entries = _entries.filter(e => e.id != _selected.id);
    showChat();
    renderTimeline(_entries);
  } catch(e) {}
}

// ---------------------------------------------------------------------------
// Recording
// ---------------------------------------------------------------------------

async function toggleRecord() {
  if (_recorder && _recorder.state === 'recording') {
    stopRecording();
  } else {
    await startRecording();
  }
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    _chunks  = [];
    _recorder = new MediaRecorder(stream);
    _recorder.ondataavailable = e => { if (e.data.size > 0) _chunks.push(e.data); };
    _recorder.onstop = submitRecording;
    _recorder.start(100);

    document.getElementById('record-btn').textContent = '⏹';
    document.getElementById('record-btn').classList.add('recording');
    // pulse-ring removed
    document.getElementById('record-label').textContent = 'Recording… tap to stop';
    document.getElementById('record-timer').style.display = 'block';

    _recSecs = 0; updateTimer();
    _recIval = setInterval(updateTimer, 1000);
  } catch(e) {
    alert('Microphone access denied. Please allow microphone in your browser.');
  }
}

function stopRecording() {
  if (_recorder) {
    _recorder.stop();
    _recorder.stream.getTracks().forEach(t => t.stop());
  }
  clearInterval(_recIval);
  document.getElementById('record-btn').textContent = '🎙';
  document.getElementById('record-btn').classList.remove('recording');
  // pulse-ring removed
  document.getElementById('record-label').textContent = 'Tap to record';
  document.getElementById('record-timer').style.display = 'none';
}

function updateTimer() {
  _recSecs++;
  const m = Math.floor(_recSecs / 60);
  const s = String(_recSecs % 60).padStart(2, '0');
  document.getElementById('record-timer').textContent = m + ':' + s;
}

async function submitRecording() {
  const blob = new Blob(_chunks, {type: 'audio/webm'});
  const fd   = new FormData();
  fd.append('file', blob, 'recording.webm');
  try {
    const entry = await fetch('/record', {method: 'POST', body: fd}).then(r => r.json());
    _entries.unshift({id: entry.id, title: 'Processing…', status: 'processing',
                      tags: '', word_count: 0, source: 'record', created_at: entry.created_at});
    renderTimeline(_entries);
    selectEntry(entry.id);
  } catch(e) { alert('Error saving recording: ' + e.message); }
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------

async function uploadFile(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file, file.name);
  try {
    const entry = await fetch('/upload', {method: 'POST', body: fd}).then(r => r.json());
    if (entry.error) { alert(entry.error); return; }
    _entries.unshift({id: entry.id, title: 'Processing…', status: 'processing',
                      tags: '', word_count: 0, source: 'upload', created_at: entry.created_at});
    renderTimeline(_entries);
    selectEntry(entry.id);
    document.getElementById('file-input').value = '';
  } catch(e) { alert('Upload error: ' + e.message); }
}

// ---------------------------------------------------------------------------
// Chat / Q&A
// ---------------------------------------------------------------------------

async function ask(question) {
  const inp = document.getElementById('chat-input');
  const res = document.getElementById('chat-result');
  const btn = document.getElementById('chat-send');
  const q   = question || inp.value.trim();
  if (!q) return;
  inp.value    = q;
  btn.disabled = true; btn.textContent = '…';
  res.className = 'chat-result vis'; res.textContent = 'Thinking…';
  try {
    const d = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: q}),
    }).then(r => r.json());
    res.textContent = d.answer || d.error || '(no response)';
    await loadEntries();
  } catch(e) { res.textContent = 'Error: ' + e.message; }
  btn.disabled = false; btn.textContent = 'Ask';
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

function onSearch(q) {
  clearTimeout(_searchTo);
  if (!q.trim()) { _searchMode = false; renderTimeline(_entries); return; }
  _searchMode = true;
  _searchTo = setTimeout(() => doSearch(q), 280);
}

async function doSearch(q) {
  try {
    const results = await fetch('/search?q=' + encodeURIComponent(q)).then(r => r.json());
    const el = document.getElementById('timeline');
    if (!results.length) {
      el.innerHTML = '<div class="no-entries">No results for "' + esc(q) + '"</div>';
      return;
    }
    const re = new RegExp(q.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&'), 'gi');
    let html = '<div class="date-label">' + results.length + ' result' +
               (results.length === 1 ? '' : 's') + '</div>';
    for (const e of results) {
      const snip = (e.body || e.summary || '').slice(0, 120);
      const hiTitle = esc(e.title || '').replace(re, m => '<mark>' + esc(m) + '</mark>');
      const hiSnip  = esc(snip).replace(re, m => '<mark>' + esc(m) + '</mark>');
      html += '<div class="entry-card" onclick="selectEntry(' + e.id + ')">' +
              '<div class="ec-title">' + hiTitle + '</div>' +
              '<div style="font-size:11px;color:#4b5563;margin-top:3px">' + hiSnip + '…</div>' +
              '</div>';
    }
    el.innerHTML = html + '<style>mark{background:#3d2e08;color:#fbbf24;border-radius:2px;padding:0 1px}</style>';
  } catch(e) {}
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function esc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

init();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice Journal")
    parser.add_argument("--port",     type=int, default=28799)
    parser.add_argument("--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model",    "-m", default=None)
    args = parser.parse_args()

    if args.provider: os.environ["LLM_PROVIDER"] = args.provider
    if args.model:    os.environ["LLM_MODEL"]    = args.model

    print(f"\n  Voice Journal  →  http://127.0.0.1:{args.port}\n")
    _web(args.port)
