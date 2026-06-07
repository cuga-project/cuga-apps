"""
Box Document Q&A UI — self-contained HTML page served by FastAPI.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation. Three-column layout: Box connection / settings on the
left, the chat thread in the middle, and the full latest response on the right.
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { background: var(--cds-background); }

  .layout {
    display: grid; grid-template-columns: 260px 1fr 1fr; gap: var(--cds-sp-05);
    max-width: 1300px; margin: 0 auto;
    padding: var(--cds-sp-06) var(--cds-sp-06);
    height: calc(100vh - 3rem);
  }
  @media (max-width: 900px) { .layout { grid-template-columns: 1fr; height: auto; } }

  .panel { display: flex; flex-direction: column; gap: var(--cds-sp-05); overflow: hidden; }

  .card-title {
    font-size: 0.75rem; font-weight: 600; color: var(--cds-text-secondary);
    letter-spacing: 0.32px; text-transform: uppercase; margin-bottom: var(--cds-sp-04);
  }

  .card-title-row { display: flex; align-items: center; justify-content: space-between; }
  .edit-btn {
    background: transparent; border: 1px solid var(--cds-border-subtle);
    color: var(--cds-text-secondary); font-family: var(--cds-font-sans);
    font-size: 0.75rem; padding: 2px 8px; cursor: pointer;
    transition: background var(--cds-dur-mod) var(--cds-ease-productive),
                color var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .edit-btn:hover { background: var(--cds-layer-hover); color: var(--cds-text-primary); }

  .field { margin-bottom: var(--cds-sp-04); }
  .field .cds-input { min-height: 2.5rem; }

  .save { margin-top: var(--cds-sp-03); }

  .status-row {
    display: flex; align-items: center; gap: var(--cds-sp-03);
    padding: var(--cds-sp-03) var(--cds-sp-04);
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    font-size: 0.75rem; margin-top: var(--cds-sp-04);
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; background: var(--cds-border-strong); }
  .dot.on { background: var(--cds-support-success); }
  .dot.off { background: var(--cds-border-strong); }
  .status-text { color: var(--cds-text-secondary); }
  .status-text strong { color: var(--cds-text-primary); }

  .badge { padding: 0 var(--cds-sp-03); height: 1.5rem; display: inline-flex; align-items: center;
    border-radius: 0.9375rem; font-size: 0.75rem; font-weight: 400; letter-spacing: 0.16px; }
  .badge-on  { background: var(--cds-support-success-bg); color: var(--cds-support-success); }
  .badge-off { background: var(--cds-support-error-bg); color: var(--cds-support-error); }

  .about-text { font-size: 0.8125rem; color: var(--cds-text-secondary); line-height: 1.6; }
  .about-text strong { color: var(--cds-text-primary); }

  .chips { display: flex; flex-wrap: wrap; gap: var(--cds-sp-03); margin-bottom: var(--cds-sp-04); }
  .chip {
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    border-radius: 0.9375rem; padding: var(--cds-sp-02) var(--cds-sp-04);
    font-size: 0.75rem; color: var(--cds-text-secondary); cursor: pointer;
    transition: all var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .chip:hover { background: var(--cds-interactive); border-color: var(--cds-interactive); color: #fff; }

  .chat-row { display: flex; gap: 0; }
  .chat-input { border-bottom: 1px solid var(--cds-border-strong); }
  .chat-row .cds-btn { flex: none; min-width: 6rem; }

  .chat-history {
    flex: 1; overflow-y: auto; display: flex; flex-direction: column;
    gap: var(--cds-sp-04); padding-right: var(--cds-sp-02); min-height: 0;
  }
  .msg { padding: var(--cds-sp-04); font-size: 0.875rem; line-height: 1.6; }
  .msg.user {
    background: var(--cds-support-info-bg); border: 1px solid var(--cds-border-subtle);
    border-left: 3px solid var(--cds-interactive);
    color: var(--cds-text-primary); align-self: flex-end; max-width: 85%;
  }
  .msg.agent {
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    color: var(--cds-text-primary); align-self: flex-start; width: 100%;
  }
  .msg.thinking { color: var(--cds-text-helper); font-style: italic; font-size: 0.8125rem; }
  .msg a { color: var(--cds-link-primary); }
  .msg a:hover { color: var(--cds-link-hover); text-decoration: underline; }
  .msg strong { color: var(--cds-text-primary); font-weight: 600; }

  .spinner {
    display: inline-block; width: 0.875rem; height: 0.875rem; vertical-align: -2px;
    border: 1.5px solid var(--cds-layer-accent); border-top-color: var(--cds-interactive);
    border-radius: 50%; animation: cds-spin 690ms linear infinite;
  }

  .result-panel { flex: 1; overflow-y: auto; min-height: 0; }
  .result-card {
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-05); font-size: 0.875rem; line-height: 1.7;
    color: var(--cds-text-primary);
  }
  .result-card a { color: var(--cds-link-primary); }
  .result-card a:hover { color: var(--cds-link-hover); text-decoration: underline; }
  .result-card strong { color: var(--cds-text-primary); font-weight: 600; }
  .placeholder {
    color: var(--cds-text-placeholder); font-size: 0.875rem; text-align: center;
    padding: var(--cds-sp-09) var(--cds-sp-06);
    border: 1px dashed var(--cds-border-subtle);
  }

  .var-row { margin-bottom: var(--cds-sp-04); }
  .var-label {
    display: block; font-size: 0.6875rem; font-weight: 600; color: var(--cds-text-helper);
    letter-spacing: 0.32px; text-transform: uppercase; margin-bottom: var(--cds-sp-02);
  }
  .var-value {
    display: block; font-size: 0.75rem; color: var(--cds-text-primary);
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-03) var(--cds-sp-04);
    word-break: break-all; font-family: var(--cds-font-mono);
  }

  .md-h3 { font-size: 0.875rem; font-weight: 600; color: var(--cds-link-primary); margin: var(--cds-sp-05) 0 var(--cds-sp-03); }
  .md-h2 { font-size: 1rem; font-weight: 600; color: var(--cds-text-primary); margin: var(--cds-sp-06) 0 var(--cds-sp-03); }
  .md-li { padding-left: var(--cds-sp-05); margin: var(--cds-sp-02) 0; }
  .md-file { color: var(--cds-link-primary); font-weight: 600; }

  @keyframes fadein { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
  .fadein { animation: fadein 0.2s ease; }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Box&nbsp;Document&nbsp;Q&amp;A</div>
  <div class="cds-header__actions">
    <span class="cds-helper-01">Powered by CugaAgent</span>
    <span class="badge badge-off" id="boxBadge">Checking…</span>
  </div>
</header>

<div class="layout">

  <!-- Left: settings -->
  <div class="panel">
    <div class="cds-tile">
      <div class="card-title card-title-row">
        Box Connection
        <button id="editBtn" class="edit-btn" onclick="toggleEdit()">Edit</button>
      </div>

      <!-- Display state (shown when configured) -->
      <div id="displayState" style="display:none">
        <div class="var-row">
          <span class="var-label">BOX_CONFIG_PATH</span>
          <span class="var-value" id="displayPath">—</span>
        </div>
        <div class="var-row">
          <span class="var-label">BOX_FOLDER_ID</span>
          <span class="var-value" id="displayFolder">—</span>
        </div>
      </div>

      <!-- Edit state (shown when not configured or editing) -->
      <div id="editState">
        <div class="field">
          <label class="cds-label">BOX_CONFIG_PATH</label>
          <input class="cds-input" type="text" id="configPath" placeholder="/path/to/box-app-config.json" />
        </div>
        <div class="field">
          <label class="cds-label">BOX_FOLDER_ID</label>
          <input class="cds-input" type="text" id="folderId" placeholder="0  (root)" />
        </div>
        <button class="cds-btn cds-btn--md cds-btn--full save" id="saveBtn" onclick="saveCreds()">Connect</button>
      </div>

      <div class="status-row">
        <span class="dot off" id="boxDot"></span>
        <span class="status-text" id="boxStatus">Not configured</span>
      </div>
    </div>

    <div class="cds-tile">
      <div class="card-title">About</div>
      <p class="about-text">
        Connects to your Box storage via a JWT app config JSON.<br><br>
        Reads <strong>PDF, DOCX, PPTX, XLSX, TXT, MD, CSV</strong>.<br><br>
        Video and audio files are listed but not read in this version.
      </p>
    </div>
  </div>

  <!-- Middle: chat -->
  <div class="panel">
    <div class="cds-tile" style="flex:0 0 auto">
      <div class="card-title">Ask about your Box files</div>
      <div class="chips">
        <span class="chip" onclick="ask(this.textContent)">What files are in my Box folder?</span>
        <span class="chip" onclick="ask(this.textContent)">Summarize the most recent document</span>
        <span class="chip" onclick="ask(this.textContent)">Find any files about contracts</span>
        <span class="chip" onclick="ask(this.textContent)">What does the README say?</span>
        <span class="chip" onclick="ask(this.textContent)">Compare the two most recent reports</span>
        <span class="chip" onclick="ask(this.textContent)">List all PDF files</span>
      </div>
      <div class="chat-row">
        <input class="cds-input chat-input" id="chatInput" type="text"
          placeholder="Ask a question about your Box documents…"
          onkeydown="if(event.key==='Enter')ask()">
        <button class="cds-btn" id="sendBtn" onclick="ask()">Send</button>
      </div>
    </div>

    <div class="cds-tile" style="flex:1;overflow:hidden;display:flex;flex-direction:column;min-height:0">
      <div class="card-title">Conversation</div>
      <div class="chat-history" id="chatHistory">
        <div class="msg thinking">Connect Box above, then ask what files are in your folder.</div>
      </div>
    </div>
  </div>

  <!-- Right: result display -->
  <div class="panel">
    <div class="cds-tile" style="flex:1;overflow:hidden;display:flex;flex-direction:column;min-height:0">
      <div class="card-title">Latest Response</div>
      <div class="result-panel" id="resultPanel">
        <div class="placeholder">Agent responses will appear here in full.</div>
      </div>
    </div>
  </div>

</div>

<script>
const threadId = 'session-' + Math.random().toString(36).slice(2, 9)

async function saveCreds() {
  const path = document.getElementById('configPath').value.trim()
  const fid  = document.getElementById('folderId').value.trim()
  if (!path) return
  const btn = document.getElementById('saveBtn')
  btn.disabled = true; btn.textContent = '…'
  try {
    const r = await fetch('/settings/credentials', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ box_config_path: path, box_folder_id: fid || '0' })
    })
    const d = await r.json()
    setBoxUI(d.box_configured, path, fid || '0')
    if (d.box_configured) document.getElementById('editBtn').textContent = 'Edit'
  } catch(e) { alert('Failed: ' + e.message) }
  finally { btn.disabled = false; btn.textContent = 'Connect' }
}

function setBoxUI(configured, configPath, folderId) {
  const dot    = document.getElementById('boxDot')
  const status = document.getElementById('boxStatus')
  const badge  = document.getElementById('boxBadge')
  const editBtn = document.getElementById('editBtn')

  if (configured) {
    dot.className = 'dot on'
    status.innerHTML = 'Connected — folder: <strong>' + esc(folderId || '0') + '</strong>'
    badge.className = 'badge badge-on'
    badge.textContent = 'Box connected'
    editBtn.style.display = 'inline-block'
    // show display state
    document.getElementById('displayPath').textContent = configPath || '—'
    document.getElementById('displayFolder').textContent = folderId || '0'
    document.getElementById('displayState').style.display = 'block'
    document.getElementById('editState').style.display = 'none'
    // keep inputs populated for when user clicks Edit
    if (configPath) document.getElementById('configPath').value = configPath
    if (folderId)   document.getElementById('folderId').value   = folderId
  } else {
    dot.className = 'dot off'
    status.innerHTML = configPath
      ? 'Config file not found at that path'
      : 'Enter the variables above to connect'
    badge.className = 'badge badge-off'
    badge.textContent = 'Box not configured'
    editBtn.style.display = 'none'
    document.getElementById('displayState').style.display = 'none'
    document.getElementById('editState').style.display = 'block'
  }
}

function toggleEdit() {
  const editing = document.getElementById('editState').style.display !== 'none'
  document.getElementById('editState').style.display  = editing ? 'none'  : 'block'
  document.getElementById('displayState').style.display = editing ? 'block' : 'none'
  document.getElementById('editBtn').textContent = editing ? 'Edit' : 'Cancel'
}

async function ask(question) {
  const inp = document.getElementById('chatInput')
  const btn = document.getElementById('sendBtn')
  const history = document.getElementById('chatHistory')
  const panel = document.getElementById('resultPanel')

  const q = question || inp.value.trim()
  if (!q) return
  inp.value = ''
  btn.disabled = true; btn.textContent = '…'

  appendMsg(history, q, 'user')
  const thinkEl = appendMsg(history, '<span class="spinner"></span> Fetching from Box…', 'thinking')
  panel.innerHTML = '<div class="result-card"><span style="color:var(--cds-text-helper);font-style:italic"><span class="spinner"></span> Working…</span></div>'

  try {
    const r = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ question: q, thread_id: threadId })
    })
    if (!r.ok) { const e = await r.json(); throw new Error(e.error || r.statusText) }
    const data = await r.json()
    thinkEl.remove()
    appendMsg(history, data.answer, 'agent fadein')
    panel.innerHTML = '<div class="result-card fadein">' + renderMd(data.answer) + '</div>'
    history.scrollTop = history.scrollHeight
  } catch (err) {
    thinkEl.remove()
    appendMsg(history, 'Error: ' + err.message, 'agent')
    panel.innerHTML = '<div class="cds-notification cds-notification--error">Error: ' + esc(err.message) + '</div>'
  } finally {
    btn.disabled = false; btn.textContent = 'Send'
  }
}

function appendMsg(container, html, cls) {
  const el = document.createElement('div')
  el.className = 'msg ' + cls
  if (cls === 'agent fadein' || cls === 'agent') el.innerHTML = renderMd(html)
  else el.innerHTML = html.includes('<') ? html : esc(html)
  container.appendChild(el)
  container.scrollTop = container.scrollHeight
  return el
}

function renderMd(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\[([^\]]+\.(?:pdf|docx|pptx|xlsx|txt|md|csv))\]/gi,
      '<span class="md-file">[$1]</span>')
    .replace(/^### (.+)$/gm, '<div class="md-h3">$1</div>')
    .replace(/^## (.+)$/gm, '<div class="md-h2">$1</div>')
    .replace(/^- (.+)$/gm, '<div class="md-li">• $1</div>')
    .replace(/\\n/g,'<br>').replace(/\n/g,'<br>')
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

fetch('/settings').then(r => r.json()).then(s => {
  setBoxUI(s.box_configured, s.box_config_path, s.folder_id)
  if (s.box_config_path) document.getElementById('configPath').value = s.box_config_path
  if (s.folder_id && s.folder_id !== '0') document.getElementById('folderId').value = s.folder_id
})
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("Box Document Q&A")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
