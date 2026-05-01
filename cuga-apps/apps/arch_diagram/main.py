"""
Architecture Diagram Generator — web UI powered by CugaAgent
=============================================================

Describe a system in plain English, get a rendered architecture diagram.
The agent generates Mermaid.js code and the browser renders it as SVG.
Supports iterative refinement — ask the agent to add, remove, or change
components and it updates the diagram.

Run:
    python main.py
    python main.py --port 28804
    python main.py --provider anthropic

Then open: http://127.0.0.1:28804

Environment variables:
    LLM_PROVIDER      rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL         model override
    TAVILY_API_KEY    (optional) Tavily search key for researching unfamiliar systems
"""
from __future__ import annotations

import argparse
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
# Persistent store
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
# SQLite diagram log
# ---------------------------------------------------------------------------

_DB_PATH = _DIR / "diagrams.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS diagram_log (
    id         TEXT PRIMARY KEY,
    query      TEXT NOT NULL,
    response   TEXT NOT NULL,
    mermaid    TEXT NOT NULL DEFAULT '',
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


def _save_diagram(query: str, response: str, mermaid: str = "") -> dict:
    rid = uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).isoformat()
    with _db() as con:
        con.execute(
            "INSERT INTO diagram_log (id, query, response, mermaid, created_at) VALUES (?,?,?,?,?)",
            (rid, query, response, mermaid, now),
        )
    return {"id": rid, "query": query, "response": response, "mermaid": mermaid, "created_at": now}


def _list_diagrams(limit: int = 30) -> list[dict]:
    with _db() as con:
        rows = con.execute(
            "SELECT * FROM diagram_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Web search tool (optional — for researching unfamiliar systems)
# ---------------------------------------------------------------------------

def _make_tools():
    # Delegated to MCP server(s): web.
    from _mcp_bridge import load_tools
    return load_tools(["web"])


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = r"""
# Architecture Diagram Generator

You are an expert software architect who creates clear, accurate architecture
diagrams from natural-language descriptions.  You produce Mermaid.js diagram
code that renders in the browser.

## Your workflow

1. Read the user's description carefully.
2. Decide which Mermaid diagram type best fits (see reference below).
3. Generate valid Mermaid code inside a fenced code block:  ```mermaid ... ```
4. BELOW the diagram, provide a brief explanation of the architecture:
   what each component does and why it's there.
5. If the user asks to modify an existing diagram, update the Mermaid code —
   do not start from scratch unless asked.

## Choosing the right diagram type

| User is describing… | Use this type |
|---|---|
| System components and how they connect | `graph TD` or `graph LR` |
| A request/response flow over time | `sequenceDiagram` |
| Database tables and relationships | `erDiagram` |
| Object-oriented class structure | `classDiagram` |
| States and transitions (e.g. order lifecycle) | `stateDiagram-v2` |

Default to `graph TD` (top-down flowchart) when uncertain.

## Mermaid syntax reference with examples

### Flowchart (graph)

```mermaid
graph TD
    Client["Browser Client"]
    LB["Load Balancer"]
    S1["App Server 1"]
    S2["App Server 2"]
    DB[("PostgreSQL")]
    Cache[("Redis Cache")]

    Client -->|HTTPS| LB
    LB --> S1
    LB --> S2
    S1 --> DB
    S2 --> DB
    S1 -.->|cache read| Cache
    S2 -.->|cache read| Cache
```

Key syntax rules for flowcharts:
- Node IDs must be alphanumeric (no spaces, no hyphens). Use: `APIGateway`, `S1`, `UserSvc`
- Labels with special characters MUST be in double quotes: `APIGateway["API Gateway"]`
- Database/cylinder shape: `DB[("PostgreSQL")]`
- Dotted lines: `A -.-> B` or `A -.->|label| B`
- Solid lines: `A --> B` or `A -->|label| B`
- Subgraphs for grouping:
  ```
  subgraph VPC["AWS VPC"]
      S1["Server 1"]
      S2["Server 2"]
  end
  ```
- NEVER use parentheses `()` in labels without wrapping in quotes
- NEVER use hyphens in node IDs — use camelCase or underscores

### Sequence diagram

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant API as API Server
    participant Auth as Auth Service
    participant DB as Database

    User->>FE: Click login
    FE->>API: POST /auth/login
    API->>Auth: Validate credentials
    Auth->>DB: Query user record
    DB-->>Auth: User data
    Auth-->>API: JWT token
    API-->>FE: 200 OK + token
    FE-->>User: Redirect to dashboard

    Note over API,Auth: Token expires in 1 hour
```

Key syntax rules for sequence diagrams:
- `actor` for human participants, `participant` for systems
- Solid arrow: `->>` (request)
- Dashed arrow: `-->>` (response)
- Aliases: `participant API as "API Server"`
- Notes: `Note over A,B: text` or `Note right of A: text`
- Loops: `loop Every 30s` / `end`
- Alt paths: `alt Success` / `else Failure` / `end`

### ER diagram

```mermaid
erDiagram
    USER {
        int id PK
        string email
        string name
        datetime created_at
    }
    ORDER {
        int id PK
        int user_id FK
        decimal total
        string status
    }
    ORDER_ITEM {
        int id PK
        int order_id FK
        int product_id FK
        int quantity
    }
    PRODUCT {
        int id PK
        string name
        decimal price
    }

    USER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : "included in"
```

Key syntax rules for ER diagrams:
- Relationship symbols: `||--o{` (one-to-many), `||--|{` (one-to-many required),
  `}o--o{` (many-to-many), `||--||` (one-to-one)
- Every relationship needs a label after the colon
- Field types: `int`, `string`, `datetime`, `decimal`, `boolean`
- PK and FK markers go after the field name

### State diagram

```mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Review: Submit
    Review --> Approved: Approve
    Review --> Draft: Request changes
    Approved --> Published: Publish
    Published --> Archived: Archive
    Archived --> [*]

    state Review {
        [*] --> Pending
        Pending --> InReview: Assign reviewer
        InReview --> [*]
    }
```

Key syntax rules for state diagrams:
- Start/end: `[*]`
- Transitions: `State1 --> State2: Label`
- Nested states use `state Name { ... }`
- No quotes needed for simple state names
- Use camelCase for multi-word state names: `InReview`

## Critical rules

- ALWAYS wrap the diagram in a ```mermaid fenced code block
- ALWAYS define nodes before using them in connections when using labels
- ALWAYS use double quotes for labels that contain spaces, special characters,
  parentheses, slashes, or colons
- NEVER use hyphens (-) in node IDs — use underscores or camelCase
- NEVER put spaces in node IDs
- Keep diagrams readable: 6-15 nodes is ideal. If a system has more components,
  group them with subgraphs or split into multiple diagrams
- If the user asks for changes to a previous diagram, reproduce the full updated
  Mermaid code — do not use pseudocode or partial snippets
- Below every diagram, include a brief "Components" section explaining what
  each node does and why it's in the architecture
- If you are unsure about a specific technology's architecture, use `web_search`
  to look it up before generating the diagram

## Iterative refinement

When the user says things like "add a cache", "remove the queue", "show me
the auth flow as a sequence diagram", or "make it more detailed":
1. Start from the previous Mermaid code
2. Apply the requested changes
3. Output the complete updated diagram (never a partial diff)
4. Briefly note what changed
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
    import re as _re
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse

    _init_db()

    app = FastAPI(title="Architecture Diagram Generator", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    _agent = make_agent()

    # -- Conversation state --------------------------------------------------
    _thread_id = uuid.uuid4().hex[:8]
    _conversation: list[dict] = []   # [{role, text, mermaid?}]

    stored_key = _load_store().get("tavily_key", "")
    if stored_key and not os.getenv("TAVILY_API_KEY"):
        os.environ["TAVILY_API_KEY"] = stored_key

    @app.post("/ask")
    async def api_ask(req: AskReq):
        nonlocal _thread_id
        question = req.question.strip()
        if not question:
            return JSONResponse({"error": "Empty question"}, status_code=400)

        _conversation.append({"role": "user", "text": question})

        try:
            result = await _agent.invoke(question, thread_id=f"diagram-{_thread_id}")
            answer = result.answer

            mermaid_match = _re.search(r'```mermaid\s*\n(.*?)```', answer, _re.DOTALL)
            mermaid_code = mermaid_match.group(1).strip() if mermaid_match else ""

            _conversation.append({"role": "agent", "text": answer, "mermaid": mermaid_code})
            _save_diagram(question, answer, mermaid_code)

            return {"answer": answer, "mermaid": mermaid_code, "conversation": _conversation}
        except Exception as exc:
            log.error("Agent error: %s", exc)
            err_msg = str(exc)
            _conversation.append({"role": "agent", "text": f"Error: {err_msg}", "mermaid": ""})
            return JSONResponse({"error": err_msg}, status_code=500)

    @app.get("/conversation")
    async def api_conversation():
        return _conversation

    @app.post("/reset")
    async def api_reset():
        nonlocal _thread_id
        _thread_id = uuid.uuid4().hex[:8]
        _conversation.clear()
        return {"ok": True, "thread_id": _thread_id}

    @app.get("/diagrams")
    async def api_diagrams():
        return _list_diagrams()

    @app.get("/settings")
    async def api_settings():
        return {"tavily_configured": bool(os.getenv("TAVILY_API_KEY"))}

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

    print(f"\n  Architecture Diagram Generator  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_WEB_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Architecture Diagram Generator</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#0f0f13;color:#e2e2e8;min-height:100vh;display:flex;flex-direction:column}

header{background:#1a1a24;border-bottom:1px solid #2e2e40;padding:14px 28px;
  display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10;flex-shrink:0}
header h1{font-size:17px;font-weight:700;color:#fff}
.sub{font-size:12px;color:#6b6b7e}.sub span{color:#818cf8;font-weight:600}
.spacer{flex:1}

.layout{display:grid;grid-template-columns:260px 1fr;gap:0;flex:1;overflow:hidden;
  max-width:1400px;width:100%;margin:0 auto}
@media(max-width:720px){.layout{grid-template-columns:1fr}}

/* Left sidebar */
.sidebar{padding:16px;overflow-y:auto;border-right:1px solid #2e2e40}
.card{background:#1a1a24;border:1px solid #2e2e40;border-radius:12px;
  padding:16px;margin-bottom:14px}
.card:last-child{margin-bottom:0}
.section-label{font-size:11px;font-weight:600;color:#4a4a60;letter-spacing:.06em;
  text-transform:uppercase;margin:14px 0 8px}
.section-label:first-child{margin-top:0}
label{display:block;font-size:11px;color:#6b6b7e;margin-bottom:4px;font-weight:500;
  text-transform:uppercase;letter-spacing:.05em}
input[type=text],input[type=password]{width:100%;background:#0f0f13;
  border:1px solid #2e2e40;border-radius:7px;padding:7px 10px;font-size:12px;
  color:#e2e2e8;outline:none}
input:focus{border-color:#818cf8}
.field{margin-bottom:8px}
.btn{background:#6366f1;color:#fff;border:none;border-radius:7px;
  padding:6px 14px;font-size:12px;font-weight:600;cursor:pointer;width:100%;margin-top:8px}
.btn:hover{background:#4f46e5}
.btn:disabled{opacity:.45}
.btn-sm{padding:5px 10px;font-size:11px;width:auto;margin-top:0}
.btn-ghost{background:#1f2937;border:1px solid #374151;color:#9ca3af}
.btn-ghost:hover{background:#374151}
.btn-danger{background:#7f1d1d;color:#fca5a5}
.btn-danger:hover{background:#991b1b}
.status-row{display:flex;align-items:center;gap:7px;margin-top:8px;
  padding:6px 10px;background:#0f0f13;border:1px solid #1e1e2e;border-radius:7px;font-size:11px}
.dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.dot.on{background:#10b981;box-shadow:0 0 4px #10b981}
.dot.off{background:#374151}
.status-text{color:#6b6b7e;flex:1}

/* Right panel — diagram + chat */
.main{display:flex;flex-direction:column;overflow:hidden}

/* Pinned diagram */
#pinnedDiagram{background:#1a1a24;border-bottom:1px solid #2e2e40;display:none;flex-shrink:0}
#pinnedDiagram.visible{display:block}
.pinned-header{display:flex;align-items:center;gap:8px;padding:10px 20px 0}
.pinned-title{font-size:11px;font-weight:700;color:#6b6b7e;letter-spacing:.08em;text-transform:uppercase;flex:1}
#pinnedRender{background:#fff;border-radius:8px;margin:10px 20px;padding:16px;
  text-align:center;overflow-x:auto;max-height:360px;overflow-y:auto}
#pinnedRender svg{max-width:100%;height:auto}
#pinnedError{display:none;margin:0 20px 10px;padding:8px 12px;background:#451a03;
  border:1px solid #78350f;border-radius:7px;font-size:11px;color:#fbbf24}
.pinned-actions{display:flex;gap:6px;padding:0 20px 12px;justify-content:flex-end}

/* Chat thread */
#chatThread{flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:12px}
.msg{max-width:85%;animation:fadein .2s ease}
.msg-user{align-self:flex-end;background:#6366f1;color:#fff;border-radius:12px 12px 2px 12px;
  padding:10px 14px;font-size:13px;line-height:1.5}
.msg-agent{align-self:flex-start;background:#1a1a24;border:1px solid #2e2e40;
  border-radius:12px 12px 12px 2px;padding:12px 16px;font-size:13px;line-height:1.7;color:#d1d5db}
.msg-agent strong{color:#fff}
.msg-agent code{background:#0f0f13;padding:1px 5px;border-radius:3px;font-size:12px}
.msg-diagram{background:#fff;border-radius:8px;padding:12px;margin:8px 0;
  text-align:center;overflow-x:auto}
.msg-diagram svg{max-width:100%;height:auto}
.msg-thinking{color:#6b6b7e;font-style:italic;font-size:13px;padding:10px 14px}
.welcome{text-align:center;color:#4a4a60;padding:40px 20px;flex:1;display:flex;
  flex-direction:column;align-items:center;justify-content:center;gap:16px}
.welcome h2{font-size:18px;color:#6b6b7e;font-weight:600}

/* Chips */
.chips{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;max-width:600px}
.chip{background:#111827;border:1px solid #1e293b;border-radius:6px;
  padding:5px 10px;font-size:12px;color:#94a3b8;cursor:pointer;transition:all .15s}
.chip:hover{background:#6366f1;border-color:#6366f1;color:#fff}

/* Input bar */
.input-bar{padding:12px 20px;border-top:1px solid #2e2e40;background:#1a1a24;flex-shrink:0}
.input-row{display:flex;gap:8px;align-items:flex-end}
#chatInput{flex:1;background:#0f0f13;border:1px solid #2e2e40;border-radius:8px;
  padding:10px 14px;font-size:14px;color:#e2e2e8;outline:none;font-family:inherit;
  resize:none;min-height:44px;max-height:120px;line-height:1.4}
#chatInput:focus{border-color:#818cf8}
#chatInput::placeholder{color:#4a4a60}
#chatSend{background:#6366f1;color:#fff;border:none;border-radius:8px;
  padding:10px 20px;font-size:14px;font-weight:600;cursor:pointer;height:44px;white-space:nowrap}
#chatSend:hover{background:#4f46e5}
#chatSend:disabled{opacity:.45;cursor:default}
.refine-chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
.refine-chips .chip{font-size:11px;padding:3px 8px}

@keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
@keyframes spin{to{transform:rotate(360deg)}}
.spinner{display:inline-block;animation:spin .7s linear infinite}
</style>
</head>
<body>

<header>
  <h1>Architecture Diagram Generator</h1>
  <p class="sub">Powered by <span>CugaAgent</span> + Mermaid.js</p>
  <div class="spacer"></div>
</header>

<div class="layout">

  <!-- ══ Left sidebar ══ -->
  <div class="sidebar">

    <div class="card">
      <div class="section-label">Settings</div>
      <div class="field">
        <label>Tavily key <span style="font-weight:400;text-transform:none;letter-spacing:0;color:#4a4a60">— optional</span></label>
        <input id="tavilyKey" type="password" placeholder="tvly-…" />
      </div>
      <button class="btn" id="saveBtn" onclick="saveCreds()">Save</button>
      <div class="status-row">
        <span class="dot off" id="apiDot"></span>
        <span class="status-text" id="apiLabel">Web search off</span>
      </div>
    </div>

    <div class="card">
      <div class="section-label">Diagram types</div>
      <p style="font-size:11px;color:#6b6b7e;line-height:1.6">
        <strong style="color:#e2e2e8">Flowchart</strong> — components &amp; connections<br>
        <strong style="color:#e2e2e8">Sequence</strong> — request flows<br>
        <strong style="color:#e2e2e8">ER diagram</strong> — database schema<br>
        <strong style="color:#e2e2e8">State</strong> — lifecycles<br><br>
        <span style="color:#4a4a60">The agent picks automatically, or ask for a specific type.</span>
      </p>
    </div>

    <div class="card">
      <div class="section-label">Session</div>
      <button class="btn btn-danger" onclick="resetConversation()" style="width:100%">New diagram</button>
      <p style="font-size:10px;color:#4a4a60;margin-top:6px;line-height:1.4">
        Clears the conversation and starts fresh. The agent forgets previous context.
      </p>
    </div>

  </div>

  <!-- ══ Right panel ══ -->
  <div class="main">

    <!-- Pinned diagram -->
    <div id="pinnedDiagram">
      <div class="pinned-header">
        <span class="pinned-title">Current diagram</span>
      </div>
      <div id="pinnedRender"></div>
      <div id="pinnedError"></div>
      <div class="pinned-actions">
        <button class="btn-sm btn-ghost" onclick="downloadSVG()">Download SVG</button>
        <button class="btn-sm btn-ghost" onclick="copyMermaid()">Copy Mermaid</button>
      </div>
    </div>

    <!-- Chat thread -->
    <div id="chatThread">
      <div class="welcome" id="welcomeScreen">
        <h2>Describe a system to get started</h2>
        <p style="color:#4a4a60;font-size:13px;max-width:500px">
          The agent will create an architecture diagram and you can refine it
          conversationally — add components, change diagram types, drill into subsystems.
        </p>
        <div class="chips" id="starterChips">
          <span class="chip" onclick="ask(this.textContent)">Microservices e-commerce platform</span>
          <span class="chip" onclick="ask(this.textContent)">CI/CD pipeline from git push to production</span>
          <span class="chip" onclick="ask(this.textContent)">Real-time chat with WebSockets</span>
          <span class="chip" onclick="ask(this.textContent)">RAG pipeline for document Q&A</span>
          <span class="chip" onclick="ask(this.textContent)">OAuth2 login as a sequence diagram</span>
          <span class="chip" onclick="ask(this.textContent)">Kafka event streaming architecture</span>
          <span class="chip" onclick="ask(this.textContent)">Order lifecycle as state diagram</span>
          <span class="chip" onclick="ask(this.textContent)">E-commerce DB as ER diagram</span>
        </div>
      </div>
    </div>

    <!-- Input bar -->
    <div class="input-bar">
      <div class="input-row">
        <textarea id="chatInput" rows="1"
          placeholder="Describe a system, or refine the current diagram…"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();ask()}"
          oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,120)+'px'"></textarea>
        <button id="chatSend" onclick="ask()">Send</button>
      </div>
      <div class="refine-chips" id="refineChips" style="display:none">
        <span class="chip" onclick="ask(this.textContent)">Add a cache layer</span>
        <span class="chip" onclick="ask(this.textContent)">Add a message queue</span>
        <span class="chip" onclick="ask(this.textContent)">Add monitoring / logging</span>
        <span class="chip" onclick="ask(this.textContent)">Show as sequence diagram</span>
        <span class="chip" onclick="ask(this.textContent)">Make it more detailed</span>
        <span class="chip" onclick="ask(this.textContent)">Simplify it</span>
        <span class="chip" onclick="ask(this.textContent)">Add authentication flow</span>
        <span class="chip" onclick="ask(this.textContent)">Show the database schema as ER</span>
      </div>
    </div>

  </div>
</div>

<script>
mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  flowchart: { htmlLabels: true, curve: 'basis' }
})

let _lastMermaid = ''
let _hasMessages = false

async function ask(question) {
  const inp = document.getElementById('chatInput')
  const btn = document.getElementById('chatSend')
  const thread = document.getElementById('chatThread')
  const q = question || inp.value.trim()
  if (!q) return
  inp.value = ''
  inp.style.height = 'auto'

  // Hide welcome, show refine chips
  const welcome = document.getElementById('welcomeScreen')
  if (welcome) welcome.remove()
  document.getElementById('refineChips').style.display = 'flex'
  _hasMessages = true

  // Add user message
  const userEl = document.createElement('div')
  userEl.className = 'msg msg-user'
  userEl.textContent = q
  thread.appendChild(userEl)

  // Add thinking indicator
  const thinkEl = document.createElement('div')
  thinkEl.className = 'msg msg-thinking'
  thinkEl.innerHTML = '<span class="spinner">&#10227;</span> Generating diagram…'
  thread.appendChild(thinkEl)
  thread.scrollTop = thread.scrollHeight

  btn.disabled = true

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

    // Remove thinking indicator
    thinkEl.remove()

    // Build agent message
    const agentEl = document.createElement('div')
    agentEl.className = 'msg msg-agent'

    // Inline diagram in chat bubble
    if (data.mermaid) {
      _lastMermaid = data.mermaid
      const diagDiv = document.createElement('div')
      diagDiv.className = 'msg-diagram'
      try {
        const { svg } = await mermaid.render('chat-' + Date.now(), data.mermaid)
        diagDiv.innerHTML = svg
      } catch(e) {
        diagDiv.innerHTML = '<pre style="text-align:left;font-size:11px;color:#666;margin:0;white-space:pre-wrap">' + esc(data.mermaid) + '</pre>'
      }
      agentEl.appendChild(diagDiv)

      // Update pinned diagram
      await updatePinned(data.mermaid)
    }

    // Explanation text (strip mermaid block)
    const explText = data.answer.replace(/```mermaid[\s\S]*?```/g, '').trim()
    if (explText) {
      const textDiv = document.createElement('div')
      textDiv.innerHTML = renderMd(explText)
      agentEl.appendChild(textDiv)
    }

    thread.appendChild(agentEl)
    thread.scrollTop = thread.scrollHeight

  } catch (err) {
    thinkEl.remove()
    const errEl = document.createElement('div')
    errEl.className = 'msg msg-agent'
    errEl.innerHTML = '<span style="color:#f87171">Error: ' + esc(err.message) + '</span>'
    thread.appendChild(errEl)
  } finally {
    btn.disabled = false
  }
}

async function updatePinned(mermaidCode) {
  const panel = document.getElementById('pinnedDiagram')
  const render = document.getElementById('pinnedRender')
  const errEl = document.getElementById('pinnedError')
  panel.className = 'visible'
  errEl.style.display = 'none'
  try {
    const { svg } = await mermaid.render('pin-' + Date.now(), mermaidCode)
    render.innerHTML = svg
  } catch(e) {
    render.innerHTML = '<pre style="text-align:left;font-size:11px;color:#666;margin:0;white-space:pre-wrap">' + esc(mermaidCode) + '</pre>'
    errEl.textContent = 'Rendering failed — ask the agent to fix the syntax.'
    errEl.style.display = 'block'
  }
}

async function resetConversation() {
  await fetch('/reset', { method: 'POST' })
  _lastMermaid = ''
  _hasMessages = false
  document.getElementById('pinnedDiagram').className = ''
  document.getElementById('refineChips').style.display = 'none'
  document.getElementById('chatThread').innerHTML = `
    <div class="welcome" id="welcomeScreen">
      <h2>Describe a system to get started</h2>
      <p style="color:#4a4a60;font-size:13px;max-width:500px">
        The agent will create an architecture diagram and you can refine it
        conversationally — add components, change diagram types, drill into subsystems.
      </p>
      <div class="chips" id="starterChips">
        <span class="chip" onclick="ask(this.textContent)">Microservices e-commerce platform</span>
        <span class="chip" onclick="ask(this.textContent)">CI/CD pipeline from git push to production</span>
        <span class="chip" onclick="ask(this.textContent)">Real-time chat with WebSockets</span>
        <span class="chip" onclick="ask(this.textContent)">RAG pipeline for document Q&A</span>
        <span class="chip" onclick="ask(this.textContent)">OAuth2 login as a sequence diagram</span>
        <span class="chip" onclick="ask(this.textContent)">Kafka event streaming architecture</span>
        <span class="chip" onclick="ask(this.textContent)">Order lifecycle as state diagram</span>
        <span class="chip" onclick="ask(this.textContent)">E-commerce DB as ER diagram</span>
      </div>
    </div>`
}

function downloadSVG() {
  const svg = document.querySelector('#pinnedRender svg')
  if (!svg) return
  const blob = new Blob([svg.outerHTML], {type: 'image/svg+xml'})
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'architecture.svg'
  a.click()
}

function copyMermaid() {
  if (!_lastMermaid) return
  navigator.clipboard.writeText(_lastMermaid).then(() => {
    const btns = document.querySelectorAll('.pinned-actions .btn-ghost')
    const btn = btns[1]
    if (!btn) return
    const orig = btn.textContent
    btn.textContent = 'Copied!'
    setTimeout(() => btn.textContent = orig, 1500)
  })
}

function renderMd(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^### (.+)$/gm, '<div style="font-size:13px;font-weight:700;color:#fff;margin:12px 0 4px">$1</div>')
    .replace(/^## (.+)$/gm, '<div style="font-size:14px;font-weight:700;color:#fff;margin:16px 0 6px">$1</div>')
    .replace(/^- (.+)$/gm, '<div style="padding-left:14px;margin:2px 0">&#8226; $1</div>')
    .replace(/\n/g, '<br>')
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
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
  } catch(e) {}
  finally { btn.disabled = false; btn.textContent = 'Save' }
}

function setApiUI(ok) {
  document.getElementById('apiDot').className = 'dot ' + (ok ? 'on' : 'off')
  document.getElementById('apiLabel').textContent = ok ? 'Web search on' : 'Web search off'
}

/* --- Init: restore conversation if server has one --- */
async function init() {
  fetch('/settings').then(r => r.json()).then(s => {
    setApiUI(s.tavily_configured)
    if (s.tavily_configured)
      document.getElementById('tavilyKey').value = '••••••••••'
  })

  try {
    const convo = await fetch('/conversation').then(r => r.json())
    if (convo && convo.length > 0) {
      document.getElementById('welcomeScreen')?.remove()
      document.getElementById('refineChips').style.display = 'flex'
      _hasMessages = true
      const thread = document.getElementById('chatThread')
      for (const msg of convo) {
        if (msg.role === 'user') {
          const el = document.createElement('div')
          el.className = 'msg msg-user'
          el.textContent = msg.text
          thread.appendChild(el)
        } else {
          const el = document.createElement('div')
          el.className = 'msg msg-agent'
          if (msg.mermaid) {
            _lastMermaid = msg.mermaid
            const diagDiv = document.createElement('div')
            diagDiv.className = 'msg-diagram'
            try {
              const { svg } = await mermaid.render('restore-' + Date.now() + '-' + Math.random().toString(36).slice(2,6), msg.mermaid)
              diagDiv.innerHTML = svg
            } catch(e) {
              diagDiv.innerHTML = '<pre style="text-align:left;font-size:11px;color:#666;margin:0;white-space:pre-wrap">' + esc(msg.mermaid) + '</pre>'
            }
            el.appendChild(diagDiv)
          }
          const explText = msg.text.replace(/```mermaid[\s\S]*?```/g, '').trim()
          if (explText) {
            const textDiv = document.createElement('div')
            textDiv.innerHTML = renderMd(explText)
            el.appendChild(textDiv)
          }
          thread.appendChild(el)
        }
      }
      thread.scrollTop = thread.scrollHeight
      if (_lastMermaid) await updatePinned(_lastMermaid)
    }
  } catch(e) {}
}

init()
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Architecture Diagram Generator — web UI")
    parser.add_argument("--port",     type=int, default=28804)
    parser.add_argument("--provider", "-p", default=None,
                        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model",    "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    _web(args.port)


if __name__ == "__main__":
    main()
