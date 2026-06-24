"""
Smart Todo — personal task manager with AI + reminder watcher
=============================================================

Chat with the agent to add todos, set reminders, and track notes.
The background watcher fires email alerts when reminders come due.

Run:
    python main.py
    python main.py --port 28800
    python main.py --provider anthropic

Then open: http://127.0.0.1:28800

Environment variables:
    LLM_PROVIDER        rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL           model override
    SMTP_HOST           SMTP server (default: smtp.gmail.com)
    SMTP_USERNAME       sender email
    SMTP_PASSWORD       app password
    DIGEST_TO           default recipient for reminders
"""

import argparse
import asyncio
import json
import logging
import os
import sys
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

from _carbon import carbon_head, carbon_css  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent settings store
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
# Agent tools — imported from existing store.py
# ---------------------------------------------------------------------------

def _make_tools():
    import json as _json
    from langchain_core.tools import tool
    from store import (
        save      as _save,
        list_all  as _list_all,
        mark_done as _mark_done,
    )

    @tool
    def save_todo(
        content: str,
        todo_type: str = "todo",
        priority: str = "medium",
        tags: list[str] | None = None,
        due_date: str | None = None,
        delivery_email: str | None = None,
    ) -> str:
        """
        Save a classified todo, reminder, or note.

        Args:
            content:        Clean task description.
            todo_type:      "todo" | "reminder" | "note"
            priority:       "high" | "medium" | "low"
            tags:           List of tag strings.
            due_date:       ISO-8601 datetime for reminders (e.g. "2026-04-08T09:00:00"). Null for todos.
            delivery_email: Email to notify when this reminder fires. Null = use default.
        """
        item = _save(
            content=content, todo_type=todo_type, priority=priority,
            tags=tags, due_date=due_date, delivery_email=delivery_email,
        )
        return _json.dumps(item)

    @tool
    def list_todos(status: str = "active") -> str:
        """
        Return all todos/reminders/notes as JSON.

        Args:
            status: "active" (default) or "done"
        """
        return _json.dumps(_list_all(status=status))

    @tool
    def mark_done(todo_id: int) -> str:
        """
        Mark a todo item as completed.

        Args:
            todo_id: Integer id of the item to complete.
        """
        _mark_done(todo_id)
        return _json.dumps({"ok": True, "id": todo_id})

    return [save_todo, list_todos, mark_done]


_SYSTEM = """\
# Todo Reasoning

You are a smart personal assistant. When the user says something, reason about what they want and act with the right tool.

## Classify

| Type | When | Examples |
|---|---|---|
| **reminder** | Has an explicit time or "remind me" phrasing | "remind me to send the report at noon", "ping me in 2 hours" |
| **todo** | A task, no specific time | "set up a meeting", "review the slides" |
| **note** | Pure information, no action | "interesting idea about search" |

## Extract

- `content`: clean task text — strip filler ("remind me to", "add a todo:")
- `priority`: high / medium / low — infer from urgency words (urgent, ASAP → high)
- `tags`: 1–3 relevant tags
- `delivery_email`: if the user mentions an email address, extract it
- `due_date` (reminders only): ISO-8601. Resolve natural language relative to today:
  - "at noon" → today 12:00
  - "in 2 hours" → now + 2h
  - "tomorrow morning" → tomorrow 09:00
  - "next Monday" → next Monday 09:00

## Act

- **reminder** → call `save_todo` with `todo_type="reminder"`, `due_date` set. Confirm: "⏰ Reminder set for {time}: {content}"
- **todo** → call `save_todo` with `todo_type="todo"`. Confirm: "✅ Added: {content}"
- **note** → call `save_todo` with `todo_type="note"`. Confirm: "💡 Saved note: {content}"
- **complete / done / finished** → call `list_todos` to find the item, then `mark_done(id)`. Confirm: "✅ Marked done: {content}"

## Configuration requests

If the user asks to reconfigure the digest pipeline (schedule, email, stop), call the appropriate config tool:
- "send my digest at 9am" → `configure_digest(schedule="0 9 * * *")`
- "email my digest to x@example.com" → `configure_digest(email="x@example.com")`
- "stop the digest" → `stop_digest()`
- "what's the digest status?" → `get_digest_status()`

## Daily Digest

When triggered to send the daily digest:
1. Call `list_todos(status="active")` to get open items
2. Call `list_todos(status="done")` to get completed items
3. Organize by priority: high → medium → low, then upcoming reminders
4. Return a single styled HTML email — do not call any send or email tools

Reply in one sentence only. Never say "I cannot".
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
        # CUGA's policy DB is a global sqlite store shared by every app. Don't
        # auto-load it, or an output-formatter persisted by another app (e.g.
        # find_a_doctor's doctor board) bleeds in and the model emits that board
        # instead of this app's answer.
        auto_load_policies=False,
    )


# ---------------------------------------------------------------------------
# Background reminder watcher
# ---------------------------------------------------------------------------

_fired_log: list[dict] = []  # in-memory, capped at 100


async def _reminder_watcher(agent) -> None:
    """Poll SQLite every 60s for due reminders; append to the in-memory
    `_fired_log` ring (UI surfaces it on the Fired Reminders panel via
    GET /reminders/fired). No email — alerts are in-UI only."""
    from store import list_due, mark_done

    while True:
        try:
            due = list_due()
            for item in due:
                mark_done(item["id"])
                log.info("Reminder firing: #%d %r", item["id"], item["content"])

                result = await agent.invoke(
                    f'Compose a brief styled HTML reminder for: "{item["content"]}".\n'
                    f'Return only the HTML body content (no DOCTYPE needed).',
                    thread_id=f"reminder-{item['id']}",
                )
                body_html = result.answer

                entry = {
                    "id":        item["id"],
                    "content":   item["content"],
                    "due_date":  item.get("due_date"),
                    "body_html": body_html,
                    "fired_at":  datetime.now(timezone.utc).isoformat(),
                }
                _fired_log.insert(0, entry)
                if len(_fired_log) > 100:
                    _fired_log.pop()

        except Exception as exc:
            log.warning("Reminder watcher error: %s", exc)

        await asyncio.sleep(60)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class AskReq(BaseModel):
    question: str


# ---------------------------------------------------------------------------
# Web app
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn
    from store import init_db, list_all, mark_done

    init_db()
    agent = make_agent()

    app = FastAPI(title="Smart Todo")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    @app.on_event("startup")
    async def _startup():
        asyncio.create_task(_reminder_watcher(agent))
        log.info("Reminder watcher started.")

    @app.post("/ask")
    async def api_ask(req: AskReq):
        from _usage import track_utterance; track_utterance(req.question)
        try:
            result = await agent.invoke(req.question, thread_id="chat")
            return {"answer": result.answer}
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/todos")
    async def api_todos():
        return list_all("active")

    @app.get("/todos/done")
    async def api_todos_done():
        return list_all("done")

    @app.post("/todos/{todo_id}/done")
    async def api_mark_done(todo_id: int):
        mark_done(todo_id)
        return {"ok": True}

    @app.get("/reminders/fired")
    async def api_fired():
        return _fired_log

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

  .layout{display:grid;grid-template-columns:360px 1fr;gap:var(--cds-sp-06);
    max-width:1280px;margin:0 auto;padding:var(--cds-sp-06) var(--cds-sp-06)}
  @media (max-width:820px){ .layout{grid-template-columns:1fr} }

  .card{background:var(--cds-layer-01);border:1px solid var(--cds-border-subtle);
    overflow:hidden;margin-bottom:var(--cds-sp-05)}
  .card-header{padding:var(--cds-sp-04) var(--cds-sp-05);
    border-bottom:1px solid var(--cds-border-subtle);
    display:flex;align-items:center;gap:var(--cds-sp-03)}
  .card-header h2{font-size:0.875rem;font-weight:600;color:var(--cds-text-primary)}
  .card-body{padding:var(--cds-sp-05)}

  /* Chat */
  .chips{display:flex;flex-wrap:wrap;gap:var(--cds-sp-02);margin-bottom:var(--cds-sp-04)}
  .chip{padding:var(--cds-sp-02) var(--cds-sp-04);border-radius:0.9375rem;
    font-size:0.75rem;background:var(--cds-layer-02);
    border:1px solid var(--cds-border-subtle);color:var(--cds-text-secondary);
    cursor:pointer;transition:all var(--cds-dur-mod) var(--cds-ease-productive)}
  .chip:hover{background:var(--cds-interactive);border-color:var(--cds-interactive);color:#fff}
  .chat-row{display:flex;gap:0}
  .chat-input{flex:1}
  .chat-row .cds-btn{flex:none}
  .chat-result{margin-top:var(--cds-sp-04);padding:var(--cds-sp-04) var(--cds-sp-05);
    background:var(--cds-field-01);border:1px solid var(--cds-border-subtle);
    border-left:3px solid var(--cds-support-info);
    font-size:0.875rem;line-height:1.6;color:var(--cds-text-primary);
    white-space:pre-wrap;display:none}
  .chat-result.vis{display:block}

  /* Tabs */
  .tabs{display:flex;gap:var(--cds-sp-02);margin-bottom:var(--cds-sp-05)}
  .tab{padding:var(--cds-sp-03) var(--cds-sp-05);font-size:0.8125rem;cursor:pointer;
    background:var(--cds-layer-02);border:1px solid var(--cds-border-subtle);
    color:var(--cds-text-secondary);
    transition:all var(--cds-dur-fast) var(--cds-ease-productive)}
  .tab:hover{background:var(--cds-layer-hover)}
  .tab.active{background:var(--cds-interactive);border-color:var(--cds-interactive);color:#fff}

  /* Todo items */
  .todo-item{padding:var(--cds-sp-04);border:1px solid var(--cds-border-subtle);
    margin-bottom:var(--cds-sp-03);display:flex;align-items:flex-start;gap:var(--cds-sp-04);
    background:var(--cds-layer-02);
    transition:background var(--cds-dur-fast) var(--cds-ease-productive)}
  .todo-item:hover{background:var(--cds-layer-hover)}
  .todo-check{width:18px;height:18px;border:1px solid var(--cds-border-strong);
    cursor:pointer;flex-shrink:0;margin-top:2px;
    transition:all var(--cds-dur-fast) var(--cds-ease-productive)}
  .todo-check:hover{border-color:var(--cds-interactive);background:var(--cds-support-info-bg)}
  .todo-body{flex:1;min-width:0}
  .todo-content{font-size:0.875rem;color:var(--cds-text-primary);line-height:1.4}
  .todo-meta{display:flex;gap:var(--cds-sp-03);margin-top:var(--cds-sp-02);flex-wrap:wrap}
  .meta-pill{font-size:0.6875rem;padding:1px var(--cds-sp-03);border-radius:0.9375rem;
    line-height:1.4;white-space:nowrap}
  .pill-todo{background:var(--cds-support-info-bg);color:var(--cds-link-primary)}
  .pill-reminder{background:var(--cds-support-warning-bg);color:var(--cds-text-primary)}
  .pill-note{background:var(--cds-support-success-bg);color:var(--cds-support-success)}
  .pill-high{background:var(--cds-support-error-bg);color:var(--cds-support-error)}
  .pill-medium{background:var(--cds-support-info-bg);color:var(--cds-link-primary)}
  .pill-low{background:var(--cds-support-success-bg);color:var(--cds-support-success)}
  .pill-tag{background:var(--cds-layer-accent);color:var(--cds-text-secondary)}
  .todo-due{font-size:0.6875rem;color:var(--cds-support-warning);align-self:center}
  .todo-done{opacity:.45}

  .empty-state{font-size:0.875rem;color:var(--cds-text-placeholder);
    text-align:center;padding:var(--cds-sp-08)}

  /* Reminder log */
  .fired-item{padding:var(--cds-sp-03) var(--cds-sp-04);
    border:1px solid var(--cds-border-subtle);
    border-left:3px solid var(--cds-support-warning);
    background:var(--cds-layer-02);
    margin-bottom:var(--cds-sp-03);font-size:0.8125rem}
  .fired-content{color:var(--cds-text-primary);font-weight:500}
  .fired-meta{font-size:0.6875rem;color:var(--cds-text-helper);margin-top:var(--cds-sp-02)}
</style>"""

_BODY = """
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Smart&nbsp;Todo</div>
  <span class="cds-tag cds-tag--blue" id="count-badge">0 active</span>
  <div class="cds-header__actions">
    <span class="cds-helper-01">Reminder watcher running · checks every 60s</span>
  </div>
</header>

<div class="layout">

  <!-- ── Left: Chat + Email ───────────────────────────────── -->
  <div>

    <div class="card">
      <div class="card-header"><h2>💬 Chat — Add &amp; Manage Tasks</h2></div>
      <div class="card-body">
        <div class="chips">
          <span class="chip" onclick="ask(this.textContent)">Add: review quarterly report</span>
          <span class="chip" onclick="ask(this.textContent)">Remind me to call John tomorrow at 9am</span>
          <span class="chip" onclick="ask(this.textContent)">High priority: fix login bug ASAP</span>
          <span class="chip" onclick="ask(this.textContent)">Note: interesting idea about caching</span>
          <span class="chip" onclick="ask(this.textContent)">What are my high priority todos?</span>
          <span class="chip" onclick="ask(this.textContent)">Remind me in 2 hours to check deploys</span>
          <span class="chip" onclick="ask(this.textContent)">What's on my list today?</span>
          <span class="chip" onclick="ask(this.textContent)">Mark the first item done</span>
          <span class="chip" onclick="ask(this.textContent)">Add: send invoice to client by Friday</span>
          <span class="chip" onclick="ask(this.textContent)">Remind me tomorrow morning to review PR</span>
        </div>
        <div class="chat-row">
          <input class="cds-input chat-input" id="chat-input" type="text"
            placeholder="Add a task, set a reminder, ask a question…"
            onkeydown="if(event.key==='Enter')ask()">
          <button class="cds-btn" id="chat-send" onclick="ask()" style="min-width:6rem">Send</button>
        </div>
        <div class="chat-result" id="chat-result"></div>
      </div>
    </div>

    <!-- Fired reminders / Recent Alerts -->
    <div class="card">
      <div class="card-header">
        <h2>🔔 Recent Alerts</h2>
        <button class="cds-btn cds-btn--ghost cds-btn--sm cds-btn--icon" style="margin-left:auto" onclick="loadFired()" title="Refresh">↺</button>
      </div>
      <div class="card-body" id="fired-body">
        <div class="empty-state">No reminders fired yet — alerts appear here when a reminder comes due.</div>
      </div>
    </div>

  </div><!-- /left -->

  <!-- ── Right: Todo board ────────────────────────────────── -->
  <div>
    <div class="card">
      <div class="card-header">
        <h2>📋 Task Board</h2>
        <button class="cds-btn cds-btn--ghost cds-btn--sm" style="margin-left:auto" onclick="loadTodos()">↺ Refresh</button>
      </div>
      <div class="card-body">
        <div class="tabs">
          <div class="tab active" onclick="switchTab('todos',this)">Todos</div>
          <div class="tab" onclick="switchTab('reminders',this)">Reminders</div>
          <div class="tab" onclick="switchTab('notes',this)">Notes</div>
          <div class="tab" onclick="switchTab('done',this)">Done</div>
        </div>
        <div id="board-body">
          <div class="empty-state">Loading…</div>
        </div>
      </div>
    </div>
  </div><!-- /right -->

</div>

<script>
let _allTodos = [];
let _doneTodos = [];
let _currentTab = 'todos';
let _lastFiredCount = 0;

// ── Init ────────────────────────────────────────────────────────────
async function init() {
  await loadTodos();
  await loadFired();
  setInterval(loadTodos, 15000);
  setInterval(loadFired, 10000);
}

async function loadTodos() {
  try {
    _allTodos  = await fetch('/todos').then(r => r.json());
    _doneTodos = await fetch('/todos/done').then(r => r.json());
    const active = _allTodos.length;
    document.getElementById('count-badge').textContent = active + ' active';
    renderBoard();
  } catch(e) {}
}

async function loadFired() {
  try {
    const fired = await fetch('/reminders/fired').then(r => r.json());
    _lastFiredCount = fired.length;
    renderFired(fired);
  } catch(e) {}
}

// ── Tabs ────────────────────────────────────────────────────────────
function switchTab(tab, el) {
  _currentTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  renderBoard();
}

function renderBoard() {
  const body = document.getElementById('board-body');
  let items = [];
  if (_currentTab === 'done') {
    items = _doneTodos;
  } else if (_currentTab === 'todos') {
    items = _allTodos.filter(t => t.todo_type === 'todo');
  } else if (_currentTab === 'reminders') {
    items = _allTodos.filter(t => t.todo_type === 'reminder');
  } else if (_currentTab === 'notes') {
    items = _allTodos.filter(t => t.todo_type === 'note');
  }
  if (!items.length) {
    body.innerHTML = '<div class="empty-state">Nothing here yet — add one via chat above.</div>';
    return;
  }
  body.innerHTML = items.map(item => renderItem(item)).join('');
}

function renderItem(item) {
  const done = item.status === 'done';
  const tags  = (item.tags || []).map(t => `<span class="meta-pill pill-tag">#${esc(t)}</span>`).join('');
  const due   = item.due_date
    ? `<span class="todo-due">⏰ ${new Date(item.due_date).toLocaleString()}</span>` : '';
  return `
    <div class="todo-item ${done ? 'todo-done' : ''}">
      ${!done ? `<div class="todo-check" onclick="markDone(${item.id})" title="Mark done"></div>` : '<div style="width:16px"></div>'}
      <div class="todo-body">
        <div class="todo-content">${esc(item.content)}</div>
        <div class="todo-meta">
          <span class="meta-pill pill-${item.todo_type}">${item.todo_type}</span>
          <span class="meta-pill pill-${item.priority}">${item.priority}</span>
          ${tags}${due}
        </div>
      </div>
    </div>`;
}

async function markDone(id) {
  await fetch('/todos/' + id + '/done', { method: 'POST' });
  await loadTodos();
}

function renderFired(fired) {
  const body = document.getElementById('fired-body');
  if (!fired.length) {
    body.innerHTML = '<div class="empty-state">No reminders fired yet.</div>';
    return;
  }
  body.innerHTML = fired.map(f => `
    <div class="fired-item">
      <span class="fired-content">${esc(f.content)}</span>
      <div class="fired-meta">Due: ${f.due_date || '—'} · Fired: ${new Date(f.fired_at).toLocaleString()}</div>
    </div>`).join('');
}

// ── Chat ─────────────────────────────────────────────────────────────
async function ask(question) {
  const inp = document.getElementById('chat-input');
  const res = document.getElementById('chat-result');
  const btn = document.getElementById('chat-send');
  const q   = question || inp.value.trim();
  if (!q) return;
  inp.value = q;
  btn.disabled = true; btn.textContent = 'Thinking…';
  res.className = 'chat-result vis';
  res.textContent = 'Thinking…';
  try {
    const r = await fetch('/ask', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ question: q }) });
    const d = await r.json();
    res.textContent = d.answer || d.error || '(no response)';
    await loadTodos();
  } catch(e) { res.textContent = 'Error: ' + e.message; }
  btn.disabled = false; btn.textContent = 'Send';
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

init();
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("Smart Todo")
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
    parser = argparse.ArgumentParser(description="Smart Todo — web UI")
    parser.add_argument("--port",     type=int, default=28800)
    parser.add_argument("--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model",    "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    print(f"\n  Smart Todo  →  http://127.0.0.1:{args.port}\n")
    _web(args.port)
