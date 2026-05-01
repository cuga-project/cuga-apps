"""
Code Reviewer — AI-powered code review with suggestions and insights
====================================================================

Paste code into the text area or upload a file. The agent reviews it for
bugs, security issues, performance, style, and best practices, then returns
structured findings with severity ratings and actionable suggestions.

Run:
    python main.py
    python main.py --port 28807
    python main.py --provider anthropic
    python main.py --provider openai --model gpt-4.1

Then open: http://127.0.0.1:28807

Environment variables:
    LLM_PROVIDER   rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL      model name override
"""

import argparse
import json
import logging
import os
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory review history (capped at 50)
# ---------------------------------------------------------------------------

_review_history: list[dict] = []


def _add_to_history(language: str, snippet: str, review: str) -> dict:
    entry = {
        "id":         uuid.uuid4().hex[:8],
        "language":   language,
        "snippet":    snippet[:300],
        "review":     review,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _review_history.insert(0, entry)
    if len(_review_history) > 50:
        _review_history.pop()
    return entry


# ---------------------------------------------------------------------------
# Agent tools
# ---------------------------------------------------------------------------

def _make_tools():
    # Delegated to the mcp-code MCP server (see mcp_servers/code/server.py).
    from _mcp_bridge import load_tools
    return load_tools(["code"])


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
# Code Reviewer

You are an expert code reviewer. Your job is to analyse code snippets and provide
structured, actionable feedback. You have three tools:
- `detect_language`      — identify the language if not specified
- `check_python_syntax`  — validate Python syntax before reviewing
- `extract_code_metrics` — get LOC, complexity, and top-level definitions

## Workflow

1. If language is unknown, call `detect_language(code)`.
2. If language is Python, call `check_python_syntax(code)`.
3. Call `extract_code_metrics(code)` to understand size and complexity.
4. Produce your review.

## Review format

Always reply in this exact structure (use markdown):

### Summary
One paragraph: what the code does, overall quality assessment (Good / Needs Work / Poor).

### Issues Found
List every bug, security flaw, or correctness problem. For each:
- **[SEVERITY]** Description — file:line if identifiable
  Severities: CRITICAL · HIGH · MEDIUM · LOW

If no issues: "No issues found."

### Suggestions
Concrete, copy-paste-ready improvements ranked by impact:
1. **Title** — explanation + example fix (code block if helpful)

### Insights
2–4 observations about architecture, patterns, or style. Not bugs — observations
that help the author understand the deeper implications of their design choices.

### Metrics
- Language: …
- Lines: … (non-blank: …)
- Complexity estimate: …

## Rules
- Be specific: mention variable names, line numbers, patterns.
- For security issues always explain the attack vector.
- Keep each section focused. No filler phrases.
- If code is too short to review meaningfully, say so and ask for more.
"""


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

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
# Request models
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class AskReq(BaseModel):
    question: str


class ReviewReq(BaseModel):
    code:     str
    language: str = ""
    focus:    str = ""   # e.g. "security", "performance", "style"


# ---------------------------------------------------------------------------
# Web app
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn

    agent = make_agent()

    app = FastAPI(title="Code Reviewer")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    @app.post("/ask")
    async def api_ask(req: AskReq):
        try:
            result = await agent.invoke(req.question, thread_id="chat")
            return {"answer": result.answer}
        except Exception as exc:
            log.exception("ask error")
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.post("/review")
    async def api_review(req: ReviewReq):
        """Submit code for a structured review."""
        lang_hint = f"Language: {req.language}\n\n" if req.language else ""
        focus_hint = f"Focus especially on: {req.focus}\n\n" if req.focus else ""
        prompt = (
            f"{lang_hint}{focus_hint}"
            f"Please review the following code:\n\n```\n{req.code}\n```"
        )
        try:
            result = await agent.invoke(prompt, thread_id=f"review-{uuid.uuid4().hex[:6]}")
            review = result.answer
            _add_to_history(req.language or "auto-detected", req.code, review)
            return {"review": review}
        except Exception as exc:
            log.exception("review error")
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.post("/upload")
    async def api_upload(file: UploadFile = File(...)):
        """Accept a source file and return its text content."""
        try:
            raw = await file.read()
            text = raw.decode("utf-8", errors="replace")
            ext  = Path(file.filename or "").suffix.lstrip(".")
            return {"content": text, "filename": file.filename, "ext": ext}
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/history")
    async def api_history():
        return _review_history

    @app.get("/", response_class=HTMLResponse)
    async def ui():
        return HTMLResponse(_HTML)

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Code Reviewer</title>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    background:#0f1117;color:#e2e8f0;min-height:100vh}

  header{background:#1a1a2e;border-bottom:1px solid #2d2d4a;padding:14px 28px;
    display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}
  header h1{font-size:16px;font-weight:700;color:#fff}
  .badge{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
  .badge-green{background:#052e16;color:#4ade80}
  .badge-amber{background:#451a03;color:#fb923c}
  .spacer{flex:1}
  .hdr-stat{font-size:11px;color:#4b5563}

  .layout{display:grid;grid-template-columns:1fr 1fr;gap:20px;
    max-width:1400px;margin:0 auto;padding:20px 24px}

  .card{background:#1a1a2e;border:1px solid #2d2d4a;border-radius:10px;
    overflow:hidden;margin-bottom:16px}
  .card-header{padding:12px 16px 10px;border-bottom:1px solid #2d2d4a;
    display:flex;align-items:center;gap:8px}
  .card-header h2{font-size:13px;font-weight:600;color:#c5cae9}
  .card-body{padding:16px}

  /* Code input */
  .code-area{width:100%;min-height:320px;padding:12px;border-radius:7px;
    font-family:'JetBrains Mono','Fira Code','Courier New',monospace;
    font-size:12px;line-height:1.6;background:#0a0a14;
    border:1px solid #374151;color:#e2e8f0;outline:none;resize:vertical;
    tab-size:4}
  .code-area:focus{border-color:#7c3aed}

  .controls{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;align-items:center}
  select{padding:6px 10px;border-radius:6px;font-size:12px;
    background:#0f1117;border:1px solid #374151;color:#e2e8f0;outline:none}
  select:focus{border-color:#7c3aed}

  .btn{padding:7px 18px;border-radius:7px;font-size:13px;font-weight:500;
    cursor:pointer;border:none;transition:all .15s}
  .btn-primary{background:#7c3aed;color:#fff}
  .btn-primary:hover{background:#6d28d9}
  .btn-primary:disabled{background:#374151;color:#6b7280;cursor:default}
  .btn-ghost{background:#1f2937;border:1px solid #374151;color:#9ca3af}
  .btn-ghost:hover{background:#374151;color:#e2e8f0}
  .btn-sm{padding:4px 12px;font-size:11px}
  .btn-upload{background:#1e3a5f;color:#60a5fa;border:1px dashed #2d5a8f}
  .btn-upload:hover{background:#1d4ed8;color:#fff;border-style:solid}

  /* Focus chips */
  .chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:12px}
  .chip{padding:4px 12px;border-radius:12px;font-size:11px;background:#1f2937;
    border:1px solid #374151;color:#9ca3af;cursor:pointer;transition:all .15s}
  .chip:hover{background:#7c3aed;border-color:#7c3aed;color:#fff}
  .chip.active{background:#7c3aed;border-color:#7c3aed;color:#fff}

  /* File info */
  .file-info{font-size:11px;color:#6b7280;margin-top:6px;display:none}
  .file-info.vis{display:block}
  .file-name{color:#a78bfa;font-weight:500}

  /* Review output */
  .review-output{min-height:200px;font-size:13px;line-height:1.7;color:#d1d5db;
    white-space:pre-wrap;display:none}
  .review-output.vis{display:block}
  .review-placeholder{color:#4b5563;font-size:13px;padding:40px 0;text-align:center}

  /* Markdown-ish rendering */
  .review-output h3{color:#a78bfa;font-size:14px;font-weight:700;
    margin:16px 0 8px;padding-bottom:4px;border-bottom:1px solid #2d2d4a}
  .review-output h3:first-child{margin-top:0}
  .review-output p{margin-bottom:10px}
  .review-output ul,.review-output ol{margin:6px 0 10px 20px}
  .review-output li{margin-bottom:4px}
  .review-output code{background:#0a0a14;border:1px solid #374151;
    padding:1px 5px;border-radius:3px;font-family:'JetBrains Mono','Courier New',monospace;
    font-size:11px;color:#86efac}
  .review-output pre{background:#0a0a14;border:1px solid #374151;
    padding:10px 12px;border-radius:6px;overflow-x:auto;margin:8px 0}
  .review-output pre code{background:none;border:none;padding:0;font-size:12px}
  .review-output strong{color:#e2e8f0}

  /* Severity badges */
  .sev-critical{color:#f87171;font-weight:700}
  .sev-high{color:#fb923c;font-weight:700}
  .sev-medium{color:#fbbf24;font-weight:600}
  .sev-low{color:#86efac;font-weight:600}

  /* Spinner */
  .spinner{display:none;align-items:center;gap:10px;
    font-size:13px;color:#6b7280;padding:30px 0}
  .spinner.vis{display:flex}
  .spin{width:20px;height:20px;border:2px solid #2d2d4a;
    border-top-color:#7c3aed;border-radius:50%;
    animation:spin .8s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}

  /* History */
  .history-item{border:1px solid #2d2d4a;border-radius:7px;margin-bottom:8px}
  .history-header{padding:9px 12px;display:flex;align-items:center;gap:8px;
    cursor:pointer;transition:background .1s}
  .history-header:hover{background:#1f2937;border-radius:7px}
  .history-snippet{font-size:11px;color:#9ca3af;flex:1;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
    font-family:'JetBrains Mono','Courier New',monospace}
  .history-lang{font-size:10px;padding:1px 7px;border-radius:8px;
    background:#2e1065;color:#c4b5fd;flex-shrink:0}
  .history-time{font-size:10px;color:#4b5563;flex-shrink:0}
  .history-body{display:none;padding:10px 12px;font-size:12px;line-height:1.6;
    color:#d1d5db;white-space:pre-wrap;border-top:1px solid #2d2d4a;
    background:#0a0a14;max-height:400px;overflow-y:auto}
  .history-body.open{display:block}
  .empty-state{font-size:13px;color:#4b5563;text-align:center;padding:32px}

  /* Status bar */
  .status-bar{display:flex;gap:16px;font-size:11px;color:#4b5563;
    padding:6px 0 2px}
  .status-dot{width:6px;height:6px;border-radius:50%;background:#4ade80;
    display:inline-block;margin-right:4px}
</style>
</head>
<body>

<header>
  <h1>&#x1f50d; Code Reviewer</h1>
  <span class="badge badge-green" id="status-badge">Ready</span>
  <div class="spacer"></div>
  <span class="hdr-stat" id="review-count">0 reviews this session</span>
</header>

<div class="layout">

  <!-- ── Left: Input ──────────────────────────────────────────── -->
  <div>

    <div class="card">
      <div class="card-header"><h2>&#x1f4c4; Code Input</h2></div>
      <div class="card-body">

        <div class="chips" id="focus-chips">
          <span class="chip active" data-focus="" onclick="setFocus(this)">Full Review</span>
          <span class="chip" data-focus="security" onclick="setFocus(this)">Security</span>
          <span class="chip" data-focus="performance" onclick="setFocus(this)">Performance</span>
          <span class="chip" data-focus="style &amp; readability" onclick="setFocus(this)">Style</span>
          <span class="chip" data-focus="bugs and correctness" onclick="setFocus(this)">Bugs</span>
          <span class="chip" data-focus="architecture and design patterns" onclick="setFocus(this)">Architecture</span>
          <span class="chip" data-focus="test coverage and testability" onclick="setFocus(this)">Testability</span>
        </div>

        <textarea class="code-area" id="code-input"
          placeholder="Paste your code here…&#10;&#10;Or upload a file using the button below."
          spellcheck="false"
          onkeydown="handleTab(event)"></textarea>

        <div class="file-info" id="file-info">
          Loaded: <span class="file-name" id="file-name"></span>
        </div>

        <div class="controls">
          <select id="lang-select">
            <option value="">Auto-detect language</option>
            <option value="python">Python</option>
            <option value="javascript">JavaScript</option>
            <option value="typescript">TypeScript</option>
            <option value="java">Java</option>
            <option value="go">Go</option>
            <option value="rust">Rust</option>
            <option value="c++">C++</option>
            <option value="c">C</option>
            <option value="ruby">Ruby</option>
            <option value="php">PHP</option>
            <option value="sql">SQL</option>
            <option value="bash">Bash/Shell</option>
            <option value="html">HTML</option>
            <option value="css">CSS</option>
          </select>

          <button class="btn btn-primary" id="review-btn" onclick="submitReview()">
            Review Code
          </button>

          <label class="btn btn-ghost btn-sm btn-upload" style="cursor:pointer">
            Upload File
            <input type="file" id="file-upload" style="display:none"
              accept=".py,.js,.ts,.jsx,.tsx,.java,.go,.rs,.cpp,.c,.rb,.php,.sql,.sh,.html,.css,.txt"
              onchange="handleFileUpload(event)">
          </label>

          <button class="btn btn-ghost btn-sm" onclick="clearAll()">Clear</button>
        </div>

        <div class="status-bar">
          <span id="line-count">0 lines</span>
          <span id="char-count">0 chars</span>
        </div>

      </div>
    </div>

    <!-- Quick prompts card -->
    <div class="card">
      <div class="card-header"><h2>&#x1f4ac; Ask the Reviewer</h2></div>
      <div class="card-body">
        <div class="chips">
          <span class="chip" onclick="quickAsk('What design patterns are used in the current code?')">Design patterns</span>
          <span class="chip" onclick="quickAsk('Is there any SQL injection or XSS risk in the current code?')">Security risks</span>
          <span class="chip" onclick="quickAsk('How could I improve the test coverage of the current code?')">Test coverage</span>
          <span class="chip" onclick="quickAsk('What are the top 3 refactoring opportunities?')">Refactoring</span>
          <span class="chip" onclick="quickAsk('Are there any memory leaks or resource management issues?')">Memory &amp; resources</span>
          <span class="chip" onclick="quickAsk('How does the complexity compare to best practices for this language?')">Complexity</span>
        </div>
        <div style="display:flex;gap:8px">
          <input type="text" id="ask-input" placeholder="Ask a follow-up question about the code…"
            style="flex:1;padding:8px 12px;border-radius:7px;font-size:13px;
              background:#0f1117;border:1px solid #374151;color:#e2e8f0;outline:none"
            onkeydown="if(event.key==='Enter')quickAsk()">
          <button class="btn btn-ghost" onclick="quickAsk()">Ask</button>
        </div>
        <div id="ask-result" style="display:none;margin-top:10px;padding:12px;
          border-radius:7px;background:#0f1117;border:1px solid #2d2d4a;
          font-size:13px;line-height:1.6;color:#d1d5db;white-space:pre-wrap"></div>
      </div>
    </div>

  </div><!-- /left -->

  <!-- ── Right: Output ─────────────────────────────────────────── -->
  <div>

    <div class="card">
      <div class="card-header">
        <h2>&#x1f4cb; Review Results</h2>
        <button class="btn btn-ghost btn-sm" style="margin-left:auto" id="copy-btn"
          onclick="copyReview()" style="display:none">Copy</button>
      </div>
      <div class="card-body">
        <div class="spinner" id="spinner">
          <div class="spin"></div>
          <span>Reviewing your code… this may take a moment</span>
        </div>
        <div class="review-placeholder" id="review-placeholder">
          Paste or upload code on the left, then click <strong>Review Code</strong>.
        </div>
        <div class="review-output" id="review-output"></div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2>&#x1f4da; Review History</h2>
        <button class="btn btn-ghost btn-sm" style="margin-left:auto"
          onclick="loadHistory()">&#x21ba; Refresh</button>
      </div>
      <div class="card-body" id="history-body">
        <div class="empty-state">No reviews yet this session.</div>
      </div>
    </div>

  </div><!-- /right -->

</div>

<script>
let _focus = '';
let _reviewCount = 0;

// ── Focus chip selection ────────────────────────────────────────────
function setFocus(el) {
  document.querySelectorAll('#focus-chips .chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  _focus = el.dataset.focus;
}

// ── Tab support in textarea ─────────────────────────────────────────
function handleTab(e) {
  if (e.key !== 'Tab') return;
  e.preventDefault();
  const ta = e.target;
  const s = ta.selectionStart, end = ta.selectionEnd;
  ta.value = ta.value.substring(0,s) + '    ' + ta.value.substring(end);
  ta.selectionStart = ta.selectionEnd = s + 4;
  updateStats();
}

function updateStats() {
  const code = document.getElementById('code-input').value;
  document.getElementById('line-count').textContent = code.split('\n').length + ' lines';
  document.getElementById('char-count').textContent = code.length + ' chars';
}
document.getElementById('code-input').addEventListener('input', updateStats);

// ── File upload ─────────────────────────────────────────────────────
async function handleFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await fetch('/upload', { method:'POST', body: fd });
    const d = await r.json();
    if (d.error) { alert('Upload error: ' + d.error); return; }
    document.getElementById('code-input').value = d.content;
    document.getElementById('file-name').textContent = d.filename;
    document.getElementById('file-info').classList.add('vis');
    // Auto-select language from extension
    const extMap = {
      py:'python', js:'javascript', ts:'typescript', jsx:'javascript',
      tsx:'typescript', java:'java', go:'go', rs:'rust',
      cpp:'c++', cc:'c++', c:'c', rb:'ruby', php:'php',
      sql:'sql', sh:'bash', html:'html', css:'css',
    };
    if (extMap[d.ext]) {
      document.getElementById('lang-select').value = extMap[d.ext];
    }
    updateStats();
  } catch(e) { alert('Upload failed: ' + e.message); }
  // Reset input so same file can be re-uploaded
  event.target.value = '';
}

// ── Main review ─────────────────────────────────────────────────────
async function submitReview() {
  const code = document.getElementById('code-input').value.trim();
  if (!code) { alert('Please paste or upload some code first.'); return; }

  const btn = document.getElementById('review-btn');
  const out  = document.getElementById('review-output');
  const ph   = document.getElementById('review-placeholder');
  const spin = document.getElementById('spinner');
  const cpBtn = document.getElementById('copy-btn');

  btn.disabled = true; btn.textContent = 'Reviewing…';
  ph.style.display = 'none';
  out.className = 'review-output';
  out.innerHTML  = '';
  spin.className = 'spinner vis';

  try {
    const r = await fetch('/review', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        code,
        language: document.getElementById('lang-select').value,
        focus:    _focus,
      }),
    });
    const d = await r.json();
    spin.className = 'spinner';
    if (d.error) {
      out.innerHTML = '<span style="color:#f87171">Error: ' + esc(d.error) + '</span>';
    } else {
      out.innerHTML = renderMarkdown(d.review);
      cpBtn.style.display = 'inline-block';
    }
    out.className = 'review-output vis';
    _reviewCount++;
    document.getElementById('review-count').textContent = _reviewCount + ' review' + (_reviewCount===1?'':'s') + ' this session';
    await loadHistory();
  } catch(e) {
    spin.className = 'spinner';
    out.innerHTML = '<span style="color:#f87171">Network error: ' + esc(e.message) + '</span>';
    out.className = 'review-output vis';
  }
  btn.disabled = false; btn.textContent = 'Review Code';
}

// ── Quick ask ────────────────────────────────────────────────────────
async function quickAsk(preset) {
  const inp = document.getElementById('ask-input');
  const res = document.getElementById('ask-result');
  const q   = preset || inp.value.trim();
  if (!q) return;

  const code = document.getElementById('code-input').value.trim();
  const fullQ = code
    ? q + '\n\nContext — the code being reviewed:\n```\n' + code.slice(0, 3000) + '\n```'
    : q;

  res.style.display = 'block';
  res.textContent   = 'Thinking…';
  try {
    const r = await fetch('/ask', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ question: fullQ }),
    });
    const d = await r.json();
    res.innerHTML = renderMarkdown(d.answer || d.error || '(no response)');
  } catch(e) { res.textContent = 'Error: ' + e.message; }
}

// ── History ───────────────────────────────────────────────────────────
async function loadHistory() {
  try {
    const h = await fetch('/history').then(r => r.json());
    renderHistory(h);
  } catch(e) {}
}

function renderHistory(items) {
  const el = document.getElementById('history-body');
  if (!items.length) {
    el.innerHTML = '<div class="empty-state">No reviews yet this session.</div>';
    return;
  }
  el.innerHTML = items.map((item, i) => `
    <div class="history-item">
      <div class="history-header" onclick="toggleHistory('hb-${i}','hi-${i}')">
        <span class="history-snippet">${esc(item.snippet)}</span>
        <span class="history-lang">${esc(item.language || 'auto')}</span>
        <span class="history-time">${new Date(item.created_at).toLocaleTimeString()}</span>
        <span id="hi-${i}" style="font-size:11px;color:#4b5563;margin-left:4px">&#x25b8;</span>
      </div>
      <div class="history-body" id="hb-${i}">${renderMarkdown(item.review)}</div>
    </div>`).join('');
}

function toggleHistory(bodyId, iconId) {
  document.getElementById(bodyId).classList.toggle('open');
  const icon = document.getElementById(iconId);
  icon.innerHTML = document.getElementById(bodyId).classList.contains('open') ? '&#x25be;' : '&#x25b8;';
}

// ── Copy review ────────────────────────────────────────────────────────
function copyReview() {
  const out = document.getElementById('review-output');
  navigator.clipboard.writeText(out.innerText).then(() => {
    const btn = document.getElementById('copy-btn');
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 1500);
  });
}

// ── Clear ───────────────────────────────────────────────────────────────
function clearAll() {
  document.getElementById('code-input').value = '';
  document.getElementById('file-info').classList.remove('vis');
  document.getElementById('review-output').className = 'review-output';
  document.getElementById('review-placeholder').style.display = '';
  document.getElementById('copy-btn').style.display = 'none';
  document.getElementById('ask-result').style.display = 'none';
  document.getElementById('lang-select').value = '';
  updateStats();
}

// ── Simple markdown renderer ────────────────────────────────────────────
function renderMarkdown(text) {
  if (!text) return '';
  let html = esc(text);

  // Code blocks
  html = html.replace(/```[\w]*\n([\s\S]*?)```/g, (_, code) =>
    '<pre><code>' + code + '</code></pre>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // ### headings
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  // **bold**
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // Severity colorising
  html = html.replace(/\[CRITICAL\]/g, '<span class="sev-critical">[CRITICAL]</span>');
  html = html.replace(/\[HIGH\]/g,     '<span class="sev-high">[HIGH]</span>');
  html = html.replace(/\[MEDIUM\]/g,   '<span class="sev-medium">[MEDIUM]</span>');
  html = html.replace(/\[LOW\]/g,      '<span class="sev-low">[LOW]</span>');
  // Numbered / bullet lists → preserve as-is (pre-wrap handles it)
  // Paragraphs
  html = html.replace(/\n\n/g, '</p><p>');
  html = '<p>' + html + '</p>';
  html = html.replace(/<p>(<h3>)/g, '$1');
  html = html.replace(/(<\/h3>)<\/p>/g, '$1');
  html = html.replace(/<p>(<pre>)/g, '$1');
  html = html.replace(/(<\/pre>)<\/p>/g, '$1');
  return html;
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Init ───────────────────────────────────────────────────────────────
loadHistory();
setInterval(loadHistory, 30000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Code Reviewer — web UI")
    parser.add_argument("--port",     type=int, default=28807)
    parser.add_argument("--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model",    "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    print(f"\n  Code Reviewer  →  http://127.0.0.1:{args.port}\n")
    _web(args.port)
