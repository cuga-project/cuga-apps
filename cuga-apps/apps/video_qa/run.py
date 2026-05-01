#!/usr/bin/env python3
"""
Video Q&A — CugaAgent demo
===========================

Transcribe a video recording and ask questions with timestamp answers.

Modes
-----
1. Interactive CLI Q&A:
     python docs/examples/demo_apps/video_qa/run.py meeting.mp4

2. Single question (stdout):
     python docs/examples/demo_apps/video_qa/run.py meeting.mp4 --ask "where was M3 discussed?"

3. Web UI (simple browser interface):
     python docs/examples/demo_apps/video_qa/run.py --web
     python docs/examples/demo_apps/video_qa/run.py meeting.mp4 --web

Dependencies (install once)
---------------------------
    pip install faster-whisper chromadb sentence-transformers fastapi uvicorn
    brew install ffmpeg

Env vars
--------
    LLM_PROVIDER    rits | watsonx | openai | anthropic | litellm | ollama
    LLM_MODEL       model name override
    RITS_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY / etc.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import textwrap
from pathlib import Path

_EXAMPLE_DIR = Path(__file__).parent
_DEMOS_DIR   = _EXAMPLE_DIR.parent

for _p in [str(_EXAMPLE_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
)
log = logging.getLogger("video_qa")


# ---------------------------------------------------------------------------
# CLI mode
# ---------------------------------------------------------------------------

async def _cli(
    video_path: str | None,
    question: str | None,
    whisper_model: str,
    provider: str | None,
    model: str | None,
):
    from agent import VideoQAAgent

    agent = VideoQAAgent(provider=provider, model=model, whisper_model=whisper_model)

    if video_path:
        path = Path(video_path).expanduser().resolve()
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        print(f"\nAudio: {path.name}")
    else:
        print("\nNo audio file specified. You can still load one during the session.")

    if video_path:
        # Pre-warm the Whisper cache before the agent runs — Whisper takes
        # minutes, which exceeds the agent's 30s code-executor timeout.
        # The agent's transcribe_audio tool then just loads from disk cache
        # and indexes into ChromaDB, completing in seconds.
        import transcriber as tr
        print("Transcribing… (cached on disk after first run)")
        tr.transcribe(str(path), model_size=whisper_model)
        print("Ready. Handing off to agent.\n")

    if question:
        full_q = f"Transcribe {path} then answer: {question}" if video_path else question
        print(await agent.ask(full_q))
        return

    print("Ask anything about the video. Type 'exit' to quit.\n")
    print("Examples:")
    print("  Where was M3 discussed?")
    print("  Summarise the key decisions made")
    print("  What was said around the 10-minute mark?")
    print()

    while True:
        try:
            q = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not q:
            continue
        if q.lower() in {"exit", "quit", "q"}:
            print("Bye.")
            break

        if q.lower().startswith("load "):
            new_path = q[5:].strip().strip('"').strip("'")
            import transcriber as tr
            segs = tr.transcribe(new_path, model_size=whisper_model)
            print(f"Loaded — {len(segs)} segments, {tr.fmt_time(segs[-1]['end']) if segs else '0:00'}\n")
            continue

        print()
        answer = await agent.ask(q)
        for line in answer.split("\n"):
            print(textwrap.fill(line, width=80) if line else "")
        print()


# ---------------------------------------------------------------------------
# Web UI mode
# ---------------------------------------------------------------------------

try:
    from pydantic import BaseModel as _BaseModel

    class LoadReq(_BaseModel):
        audio_path: str
        whisper_model: str = "base"

    class AskReq(_BaseModel):
        question: str
except ImportError:
    LoadReq = None  # type: ignore
    AskReq = None   # type: ignore


def _web(port: int, provider: str | None = None, llm_model: str | None = None):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse

    app = FastAPI(title="Video Q&A · CugaAgent", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    from agent import VideoQAAgent
    import index as idx
    _agent = VideoQAAgent(provider=provider, model=llm_model)
    _executor = ThreadPoolExecutor(max_workers=1)

    # Job state for async transcription polling
    _job: dict = {"status": "idle", "error": None, "result": None}

    def _load_sync(audio_path: str, whisper_model: str):
        import transcriber as tr
        segments = tr.transcribe(audio_path, model_size=whisper_model)
        idx.index_segments(audio_path, segments)
        _agent._video_path_ref["path"]     = audio_path
        _agent._video_path_ref["segments"] = segments
        return segments

    @app.post("/load")
    async def load(req: LoadReq):
        if _job["status"] == "running":
            raise HTTPException(status_code=409, detail="Transcription already in progress.")
        _job.update(status="running", error=None, result=None)

        def _run():
            try:
                segments = _load_sync(req.audio_path, req.whisper_model)
                import transcriber as tr
                duration = segments[-1]["end"] if segments else 0
                _job.update(status="done", result={
                    "segments_count": len(segments),
                    "duration_fmt": tr.fmt_time(duration),
                    "audio_path": req.audio_path,
                })
            except Exception as exc:
                _job.update(status="error", error=str(exc))

        loop = asyncio.get_running_loop()
        loop.run_in_executor(_executor, _run)
        return {"status": "running"}

    @app.get("/load/status")
    def load_status():
        return _job

    @app.post("/ask")
    async def ask(req: AskReq):
        if not _agent.video_path:
            raise HTTPException(status_code=400, detail="No video loaded. Use /load first.")
        answer = await _agent.ask(req.question)
        return {"answer": answer}

    @app.get("/status")
    def status():
        import transcriber as tr
        segs     = _agent.segments
        duration = segs[-1]["end"] if segs else 0
        return {
            "loaded":          bool(_agent.video_path),
            "audio_path":      _agent.video_path,
            "segments_count":  len(segs),
            "duration_fmt":    tr.fmt_time(duration) if segs else None,
        }

    @app.get("/segments")
    def segments():
        import transcriber as tr
        return [
            {
                "index":      i,
                "start":      s["start"],
                "end":        s["end"],
                "start_fmt":  tr.fmt_time(s["start"]),
                "end_fmt":    tr.fmt_time(s["end"]),
                "text":       s["text"],
            }
            for i, s in enumerate(_agent.segments)
        ]

    @app.get("/", response_class=HTMLResponse)
    def ui():
        return _WEB_HTML

    print(f"\n  Video Q&A · CugaAgent  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


_WEB_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Video Q&A · CugaAgent</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0f0f13;color:#e2e2e8;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:40px 16px 80px;}
h1{font-size:22px;font-weight:700;color:#fff;margin-bottom:4px}
.sub{font-size:13px;color:#6b6b7e;margin-bottom:32px}.sub span{color:#7c7cf8;font-weight:500}
.card{width:100%;max-width:640px;background:#1a1a24;border:1px solid #2e2e40;border-radius:12px;padding:20px;margin-bottom:16px;}
label{display:block;font-size:12px;color:#6b6b7e;margin-bottom:6px;font-weight:500;text-transform:uppercase;letter-spacing:.05em}
input[type=text],select{width:100%;background:#0f0f13;border:1px solid #2e2e40;border-radius:8px;padding:10px 14px;font-size:14px;color:#e2e2e8;outline:none;transition:border-color .15s;}
input[type=text]:focus,select:focus{border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.15)}
input[type=text]::placeholder{color:#4a4a60}
.row{display:flex;gap:8px;margin-top:10px}.row input{flex:1}
button{background:#6366f1;color:#fff;border:none;border-radius:8px;padding:10px 18px;font-size:14px;font-weight:600;cursor:pointer;transition:background .15s,opacity .15s;white-space:nowrap;}
button:hover{background:#4f52d9}button:disabled{opacity:.45;cursor:default}
.status-pill{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:500;margin-bottom:12px;}
.status-none{background:#1f1f2e;color:#6b6b7e;border:1px solid #2e2e40}
.status-ok{background:rgba(16,185,129,.12);color:#10b981;border:1px solid rgba(16,185,129,.25)}
.status-loading{background:rgba(99,102,241,.12);color:#818cf8;border:1px solid rgba(99,102,241,.25)}
.messages{display:flex;flex-direction:column;gap:12px;margin-top:16px}
.msg{padding:12px 14px;border-radius:10px;font-size:14px;line-height:1.6}
.msg.user{background:#1e1e2e;border:1px solid #2e2e40;color:#d4d4e4;align-self:flex-end;max-width:85%}
.msg.agent{background:#111827;border:1px solid #1e293b;color:#e2e8f0}
.thinking{color:#6b6b7e;font-style:italic;font-size:13px}
/* transcript panel */
.transcript-header{display:flex;align-items:center;justify-content:space-between;cursor:pointer;user-select:none;}
.transcript-header h2{font-size:12px;font-weight:600;color:#6b6b7e;letter-spacing:.05em;text-transform:uppercase;}
.transcript-header .chevron{font-size:11px;color:#4a4a60;transition:transform .2s;}
.transcript-header.open .chevron{transform:rotate(180deg);}
.transcript-body{margin-top:14px;max-height:400px;overflow-y:auto;display:flex;flex-direction:column;gap:4px;}
.transcript-body::-webkit-scrollbar{width:4px}.transcript-body::-webkit-scrollbar-track{background:transparent}.transcript-body::-webkit-scrollbar-thumb{background:#2e2e40;border-radius:2px}
.seg{display:flex;gap:10px;padding:7px 10px;border-radius:7px;border:1px solid transparent;transition:background .1s,border-color .1s;}
.seg:hover{background:#111827;border-color:#1e293b;}
.seg-ts{flex-shrink:0;font-size:11px;font-weight:600;color:#6366f1;font-variant-numeric:tabular-nums;padding-top:1px;min-width:80px;}
.seg-text{font-size:13px;color:#c4c4d4;line-height:1.5;}
.seg-filter{width:100%;background:#0f0f13;border:1px solid #2e2e40;border-radius:7px;padding:7px 12px;font-size:13px;color:#e2e2e8;outline:none;margin-bottom:10px;}
.seg-filter:focus{border-color:#6366f1;}
.seg-filter::placeholder{color:#4a4a60}
.empty-state{text-align:center;color:#4a4a60;font-size:13px;padding:24px 0;}
@keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.fadein{animation:fadein .2s ease}
.spinner{display:inline-block;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<h1>Audio Q&A</h1>
<p class="sub">Powered by <span>CugaAgent</span> · Whisper + ChromaDB + LLM</p>

<div class="card">
  <label>Audio file</label>
  <p style="font-size:12px;color:#6b6b7e;margin-bottom:8px">
    Copy your file to <code style="background:#111827;padding:1px 5px;border-radius:4px;color:#818cf8">apps/video_qa/videos/</code> on the host, then enter <code style="background:#111827;padding:1px 5px;border-radius:4px;color:#818cf8">/audio/filename.mp3</code> below.
    Supported: <code style="background:#111827;padding:1px 5px;border-radius:4px;color:#818cf8">.wav &nbsp;.mp3 &nbsp;.m4a &nbsp;.flac &nbsp;.ogg &nbsp;.aac</code>
  </p>
  <div class="row">
    <input id="audioPath" type="text" placeholder="/audio/recording.mp3" />
  </div>
  <div class="row" style="margin-top:8px;align-items:center">
    <label style="margin:0;white-space:nowrap">Whisper model</label>
    <select id="modelSize" style="width:auto;flex:0 0 auto">
      <option value="tiny" selected>tiny (fastest)</option>
      <option value="base">base</option>
      <option value="small">small</option>
      <option value="medium">medium</option>
      <option value="large-v3">large-v3 (most accurate)</option>
    </select>
    <button id="loadBtn" onclick="loadAudio()">Transcribe</button>
  </div>
  <div style="margin-top:12px">
    <span class="status-pill status-none" id="statusPill">No audio loaded</span>
  </div>
</div>

<div class="card" id="transcriptCard" style="display:none">
  <div class="transcript-header" id="transcriptToggle" onclick="toggleTranscript()">
    <h2>Transcript <span id="segCount" style="color:#4a4a60;font-weight:400"></span></h2>
    <span class="chevron">▼</span>
  </div>
  <div class="transcript-body" id="transcriptBody" style="display:none">
    <input class="seg-filter" id="segFilter" placeholder="Filter segments…" oninput="filterSegments()" />
    <div id="segList"></div>
  </div>
</div>

<div class="card">
  <label>Ask a question</label>
  <div class="row">
    <input id="question" type="text"
      placeholder="What was discussed at 10 minutes?  ·  Summarise key decisions  ·  Where was X mentioned?"
      onkeydown="if(event.key==='Enter')ask()"
    />
    <button id="askBtn" onclick="ask()" disabled>Ask</button>
  </div>
  <div class="messages" id="messages"></div>
</div>

<script>
let loaded = false
let allSegments = []

async function loadAudio() {
  const path  = document.getElementById('audioPath').value.trim()
  const model = document.getElementById('modelSize').value
  if (!path) return
  const btn  = document.getElementById('loadBtn')
  const pill = document.getElementById('statusPill')
  btn.disabled = true; btn.textContent = '…'
  pill.className = 'status-pill status-loading'
  pill.textContent = '⏳ Transcribing…'
  try {
    const res = await fetch('/load', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({audio_path:path,whisper_model:model})})
    if (!res.ok) throw new Error(await res.text())
    // Poll for completion — /load returns immediately, transcription runs in background
    while (true) {
      await new Promise(r => setTimeout(r, 3000))
      let poll
      try { poll = await fetch('/load/status').then(r => r.json()) }
      catch(e) { throw new Error('Server became unreachable. It may have run out of memory — try the "tiny" model.') }
      if (poll.status === 'done') {
        const data = poll.result
        pill.className = 'status-pill status-ok'
        pill.textContent = `✓ ${data.segments_count} segments · ${data.duration_fmt}`
        document.getElementById('askBtn').disabled = false
        loaded = true
        await loadSegments()
        break
      } else if (poll.status === 'error') {
        throw new Error(poll.error)
      }
      // still running — update elapsed hint
      const elapsed = Math.round((Date.now() - loadStart) / 1000)
      pill.textContent = `⏳ Transcribing… ${elapsed}s`
    }
  } catch(err) {
    pill.className = 'status-pill status-none'
    pill.textContent = 'Error: ' + err.message
  } finally { btn.disabled = false; btn.textContent = 'Transcribe' }
}
let loadStart = 0
const _origLoad = loadAudio
loadAudio = async function() { loadStart = Date.now(); return _origLoad() }

async function loadSegments() {
  const res = await fetch('/segments')
  if (!res.ok) return
  allSegments = await res.json()
  document.getElementById('segCount').textContent = `· ${allSegments.length} segments`
  document.getElementById('transcriptCard').style.display = ''
  renderSegments(allSegments)
}

function renderSegments(segs) {
  const list = document.getElementById('segList')
  if (!segs.length) {
    list.innerHTML = '<div class="empty-state">No segments match.</div>'
    return
  }
  list.innerHTML = segs.map(s => `
    <div class="seg" onclick="fillQuestion('What was said at ${s.start_fmt}?')">
      <span class="seg-ts">${s.start_fmt} – ${s.end_fmt}</span>
      <span class="seg-text">${escHtml(s.text.trim())}</span>
    </div>`).join('')
}

function filterSegments() {
  const q = document.getElementById('segFilter').value.toLowerCase()
  renderSegments(q ? allSegments.filter(s => s.text.toLowerCase().includes(q)) : allSegments)
}

function toggleTranscript() {
  const body   = document.getElementById('transcriptBody')
  const toggle = document.getElementById('transcriptToggle')
  const open   = body.style.display === 'none'
  body.style.display = open ? '' : 'none'
  toggle.classList.toggle('open', open)
}

function fillQuestion(text) {
  const input = document.getElementById('question')
  input.value = text
  input.focus()
}

async function ask() {
  if (!loaded) return
  const input = document.getElementById('question')
  const q = input.value.trim()
  if (!q) return
  const btn = document.getElementById('askBtn')
  btn.disabled = true; input.value = ''
  const msgs = document.getElementById('messages')
  const userEl = document.createElement('div')
  userEl.className = 'msg user fadein'; userEl.textContent = q
  msgs.appendChild(userEl)
  const thinkEl = document.createElement('div')
  thinkEl.className = 'msg agent fadein thinking'
  thinkEl.innerHTML = '<span class="spinner">⟳</span> Thinking…'
  msgs.appendChild(thinkEl); msgs.scrollTop = msgs.scrollHeight
  try {
    const res = await fetch('/ask', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})})
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    thinkEl.className = 'msg agent fadein'
    thinkEl.innerHTML = renderAnswer(data.answer)
  } catch(err) {
    thinkEl.className = 'msg agent fadein'
    thinkEl.style.color = '#f87171'
    thinkEl.textContent = 'Error: ' + err.message
  } finally { btn.disabled = false; msgs.scrollTop = msgs.scrollHeight }
}

function renderAnswer(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\\*\\*(.*?)\\*\\*/g,'<strong>$1</strong>')
    .replace(/\\b(\\d{1,2}:\\d{2}(?::\\d{2})?)\\b/g,(ts)=>{
      return `<span style="background:rgba(99,102,241,.15);color:#818cf8;border-radius:4px;padding:1px 5px;font-size:12px;font-weight:600;margin:0 2px;border:1px solid rgba(99,102,241,.25);">${ts}</span>`
    })
    .replace(/\\n/g,'<br>')
}

function escHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function toSeconds(ts){const p=ts.split(':').map(Number);return p.length===2?p[0]*60+p[1]:p[0]*3600+p[1]*60+p[2]}

fetch('/status').then(r=>r.json()).then(s=>{
  if(s.loaded){
    const pill=document.getElementById('statusPill')
    pill.className='status-pill status-ok'
    pill.textContent=`✓ ${s.segments_count} segments · ${s.duration_fmt}`
    document.getElementById('audioPath').value=s.audio_path||''
    document.getElementById('askBtn').disabled=false
    loaded=true
    loadSegments()
  }
})
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(
        description="Video Q&A — CugaAgent demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python run.py meeting.mp4
              python run.py meeting.mp4 --ask "where was M3 discussed?"
              python run.py meeting.mp4 --model large-v3
              python run.py --web --port 28766
              python run.py meeting.mp4 --web
        """),
    )
    parser.add_argument("video", nargs="?", help="Path to video or audio file")
    parser.add_argument("--ask", "-q", help="Ask a single question and exit")
    parser.add_argument("--model", "-m", default="base",
        choices=["tiny", "base", "small", "medium", "large-v3"])
    parser.add_argument("--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--web", action="store_true")
    parser.add_argument("--port", type=int, default=28766)
    args = parser.parse_args()

    provider  = args.provider  or os.getenv("LLM_PROVIDER") or None
    llm_model = args.llm_model or os.getenv("LLM_MODEL")    or None

    if args.web:
        _web(args.port, provider=provider, llm_model=llm_model)
    else:
        asyncio.run(_cli(
            video_path=args.video,
            question=args.ask,
            whisper_model=args.model,
            provider=provider,
            model=llm_model,
        ))


if __name__ == "__main__":
    main()
