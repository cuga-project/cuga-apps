_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Box Document Q&A</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#0f1117;color:#e2e2e8;min-height:100vh}

header{background:#1a1a2e;border-bottom:1px solid #2d2d4a;padding:14px 28px;
  display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}
header h1{font-size:17px;font-weight:700;color:#fff}
.sub{font-size:12px;color:#6b6b7e}.sub span{color:#0061d5;font-weight:600}
.spacer{flex:1}
.badge{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
.badge-on{background:#0a2e1a;color:#4ade80}
.badge-off{background:#2e0a0a;color:#f87171}

.layout{display:grid;grid-template-columns:260px 1fr 1fr;gap:16px;
  max-width:1300px;margin:0 auto;padding:20px 24px;height:calc(100vh - 57px)}
@media(max-width:900px){.layout{grid-template-columns:1fr;height:auto}}

.panel{display:flex;flex-direction:column;gap:16px;overflow:hidden}

.card{background:#1a1a2e;border:1px solid #2d2d4a;border-radius:12px;padding:18px}
.card-title{font-size:11px;font-weight:700;color:#5b5b7e;letter-spacing:.08em;
  text-transform:uppercase;margin-bottom:14px}

label{display:block;font-size:11px;color:#6b6b7e;margin-bottom:4px;font-weight:500;
  text-transform:uppercase;letter-spacing:.05em}
input[type=text]{width:100%;background:#0f1117;border:1px solid #2d2d4a;border-radius:7px;
  padding:8px 12px;font-size:13px;color:#e2e2e8;outline:none;transition:border-color .15s}
input[type=text]:focus{border-color:#0061d5;box-shadow:0 0 0 3px rgba(0,97,213,.15)}
input::placeholder{color:#4a4a60}
.field{margin-bottom:10px}
button.save{background:#0061d5;color:#fff;border:none;border-radius:7px;
  padding:8px 16px;font-size:13px;font-weight:600;cursor:pointer;width:100%;
  margin-top:8px;transition:background .15s}
button.save:hover{background:#0050b3}
button.save:disabled{opacity:.45;cursor:default}

.status-row{display:flex;align-items:center;gap:8px;padding:8px 12px;
  background:#0f1117;border:1px solid #1e1e2e;border-radius:8px;font-size:12px;
  margin-top:10px}
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.dot.on{background:#10b981;box-shadow:0 0 5px #10b981}
.dot.off{background:#374151}
.status-text{color:#6b6b7e}
.status-text strong{color:#e2e2e8}

.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.chip{background:#111827;border:1px solid #1e293b;border-radius:6px;
  padding:5px 10px;font-size:12px;color:#94a3b8;cursor:pointer;transition:all .15s}
.chip:hover{background:#0061d5;border-color:#0061d5;color:#fff}

.chat-row{display:flex;gap:8px}
.chat-input{flex:1;padding:9px 14px;border-radius:8px;font-size:14px;
  background:#0f1117;border:1px solid #2d2d4a;color:#e2e2e8;outline:none}
.chat-input:focus{border-color:#0061d5;box-shadow:0 0 0 3px rgba(0,97,213,.15)}
.chat-input::placeholder{color:#4a4a60}
button.send{background:#0061d5;color:#fff;border:none;border-radius:8px;
  padding:9px 20px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap;
  transition:background .15s}
button.send:hover{background:#0050b3}
button.send:disabled{opacity:.45;cursor:default}

.chat-history{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:12px;
  padding-right:4px;min-height:0}
.msg{padding:12px 14px;border-radius:9px;font-size:13px;line-height:1.7}
.msg.user{background:#0f1f3d;border:1px solid #1a3a6e;color:#93c5fd;
  align-self:flex-end;max-width:85%}
.msg.agent{background:#111827;border:1px solid #1e293b;color:#e2e8f0;
  align-self:flex-start;width:100%}
.msg.thinking{color:#5b5b7e;font-style:italic;font-size:12px}
.spinner{display:inline-block;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

.result-panel{flex:1;overflow-y:auto;min-height:0}
.result-card{background:#111827;border:1px solid #1e293b;border-radius:9px;
  padding:16px;font-size:13px;line-height:1.75;color:#e2e8f0}
.result-card a{color:#60a5fa;text-decoration:none}
.result-card a:hover{text-decoration:underline}
.result-card strong{color:#fff}
.placeholder{color:#4a4a60;font-size:13px;text-align:center;
  padding:48px 20px;border:1px dashed #2d2d4a;border-radius:9px}

.var-row{margin-bottom:10px}
.var-label{display:block;font-size:10px;font-weight:700;color:#4a4a60;
  letter-spacing:.07em;text-transform:uppercase;margin-bottom:3px}
.var-value{display:block;font-size:12px;color:#e2e2e8;background:#0f1117;
  border:1px solid #1e1e2e;border-radius:6px;padding:6px 10px;
  word-break:break-all;font-family:monospace}

@keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.fadein{animation:fadein .2s ease}
</style>
</head>
<body>

<header>
  <h1>Box Document Q&A</h1>
  <p class="sub">Powered by <span>CugaAgent</span></p>
  <div class="spacer"></div>
  <span class="badge badge-off" id="boxBadge">Checking…</span>
</header>

<div class="layout">

  <!-- Left: settings -->
  <div class="panel">
    <div class="card">
      <div class="card-title" style="display:flex;align-items:center;justify-content:space-between">
        Box Connection
        <button id="editBtn" onclick="toggleEdit()" style="background:none;border:1px solid #2d2d4a;border-radius:5px;color:#6b6b7e;font-size:11px;padding:2px 8px;cursor:pointer;width:auto;margin:0">Edit</button>
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
          <label>BOX_CONFIG_PATH</label>
          <input type="text" id="configPath" placeholder="/path/to/box-app-config.json" />
        </div>
        <div class="field">
          <label>BOX_FOLDER_ID</label>
          <input type="text" id="folderId" placeholder="0  (root)" />
        </div>
        <button class="save" id="saveBtn" onclick="saveCreds()">Connect</button>
      </div>

      <div class="status-row">
        <span class="dot off" id="boxDot"></span>
        <span class="status-text" id="boxStatus">Not configured</span>
      </div>
    </div>

    <div class="card">
      <div class="card-title">About</div>
      <p style="font-size:12px;color:#6b6b7e;line-height:1.7">
        Connects to your Box storage via a JWT app config JSON.<br><br>
        Reads <strong style="color:#e2e2e8">PDF, DOCX, PPTX, XLSX, TXT, MD, CSV</strong>.<br><br>
        Video and audio files are listed but not read in this version.
      </p>
    </div>
  </div>

  <!-- Middle: chat -->
  <div class="panel">
    <div class="card" style="flex:0 0 auto">
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
        <input class="chat-input" id="chatInput" type="text"
          placeholder="Ask a question about your Box documents…"
          onkeydown="if(event.key==='Enter')ask()">
        <button class="send" id="sendBtn" onclick="ask()">Send</button>
      </div>
    </div>

    <div class="card" style="flex:1;overflow:hidden;display:flex;flex-direction:column;min-height:0">
      <div class="card-title">Conversation</div>
      <div class="chat-history" id="chatHistory">
        <div class="msg thinking">Connect Box above, then ask what files are in your folder.</div>
      </div>
    </div>
  </div>

  <!-- Right: result display -->
  <div class="panel">
    <div class="card" style="flex:1;overflow:hidden;display:flex;flex-direction:column;min-height:0">
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
  const thinkEl = appendMsg(history, '<span class="spinner">⟳</span> Fetching from Box…', 'thinking')
  panel.innerHTML = '<div class="result-card"><span style="color:#5b5b7e;font-style:italic"><span class="spinner">⟳</span> Working…</span></div>'

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
    panel.innerHTML = '<div class="result-card" style="color:#f87171">Error: ' + esc(err.message) + '</div>'
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
      '<span style="color:#60a5fa;font-weight:600">[$1]</span>')
    .replace(/^### (.+)$/gm,
      '<div style="font-size:13px;font-weight:700;color:#fff;margin:14px 0 6px">$1</div>')
    .replace(/^## (.+)$/gm,
      '<div style="font-size:15px;font-weight:700;color:#fff;margin:18px 0 8px">$1</div>')
    .replace(/^- (.+)$/gm,
      '<div style="padding-left:16px;margin:3px 0">• $1</div>')
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
</body>
</html>
"""
