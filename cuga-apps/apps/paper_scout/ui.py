"""
Paper Scout UI — self-contained HTML page served by FastAPI.
"""

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Paper Scout</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#0f1117;color:#e2e2e8;min-height:100vh}

header{background:#1a1a2e;border-bottom:1px solid #2d2d4a;padding:14px 28px;
  display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}
header h1{font-size:17px;font-weight:700;color:#fff}
.sub{font-size:12px;color:#6b6b7e}.sub span{color:#7c3aed;font-weight:600}
.spacer{flex:1}
.badge{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;
  background:#1e1b4b;color:#a5b4fc}

.layout{display:grid;grid-template-columns:1fr 1fr;gap:20px;
  max-width:1200px;margin:0 auto;padding:20px 24px;height:calc(100vh - 57px)}
@media(max-width:800px){.layout{grid-template-columns:1fr;height:auto}}

.panel{display:flex;flex-direction:column;gap:16px;overflow:hidden}
.card{background:#1a1a2e;border:1px solid #2d2d4a;border-radius:12px;padding:18px}
.card-title{font-size:11px;font-weight:700;color:#6b6b7e;letter-spacing:.08em;
  text-transform:uppercase;margin-bottom:14px}

.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.chip{background:#111827;border:1px solid #1e293b;border-radius:6px;
  padding:5px 10px;font-size:12px;color:#94a3b8;cursor:pointer;transition:all .15s}
.chip:hover{background:#7c3aed;border-color:#7c3aed;color:#fff}

.chat-row{display:flex;gap:8px}
.chat-input{flex:1;padding:9px 14px;border-radius:8px;font-size:14px;
  background:#0f1117;border:1px solid #2d2d4a;color:#e2e2e8;outline:none;
  transition:border-color .15s}
.chat-input:focus{border-color:#7c3aed;box-shadow:0 0 0 3px rgba(124,58,237,.15)}
.chat-input::placeholder{color:#4a4a60}
button.send{background:#7c3aed;color:#fff;border:none;border-radius:8px;
  padding:9px 20px;font-size:13px;font-weight:600;cursor:pointer;
  transition:background .15s;white-space:nowrap}
button.send:hover{background:#6d28d9}
button.send:disabled{opacity:.45;cursor:default}

.result-panel{flex:1;overflow-y:auto;background:#1a1a2e;border:1px solid #2d2d4a;
  border-radius:12px;padding:18px}
.result-empty{color:#4a4a60;font-size:13px;text-align:center;padding:40px 0;
  font-style:italic}
.result-content{font-size:14px;line-height:1.8;color:#e2e8f0}
.result-content a{color:#a5b4fc;text-decoration:none}
.result-content a:hover{text-decoration:underline}
.result-content strong{color:#fff}
.result-content hr{border:none;border-top:1px solid #2d2d4a;margin:14px 0}
.thinking{color:#6b6b7e;font-style:italic;font-size:13px;text-align:center;
  padding:20px 0}
.spinner{display:inline-block;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.fadein{animation:fadein .25s ease}

.citation-count{display:inline-block;background:#1e1b4b;color:#a5b4fc;
  border-radius:10px;padding:1px 7px;font-size:11px;margin-left:5px}
.source-tag{display:inline-block;border-radius:4px;padding:1px 6px;
  font-size:10px;font-weight:700;margin-left:4px;text-transform:uppercase}
.source-arxiv{background:#7f1d1d;color:#fca5a5}
.source-s2{background:#14532d;color:#86efac}

.history-list{max-height:220px;overflow-y:auto}
.history-item{padding:8px 12px;border-radius:7px;cursor:pointer;
  font-size:12px;color:#94a3b8;border:1px solid transparent;margin-bottom:4px;
  transition:all .15s;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.history-item:hover{background:#111827;border-color:#2d2d4a;color:#e2e2e8}
.history-empty{font-size:12px;color:#4a4a60;font-style:italic}
</style>
</head>
<body>

<header>
  <h1>Paper Scout</h1>
  <p class="sub">arXiv + Semantic Scholar · Powered by <span>CugaAgent</span></p>
  <div class="spacer"></div>
  <span class="badge">No API keys required</span>
</header>

<div class="layout">

  <!-- Left panel: input -->
  <div class="panel">
    <div class="card">
      <div class="card-title">Research a Topic or Paste an arXiv ID</div>
      <div class="chips" id="chips"></div>
      <div class="chat-row">
        <input class="chat-input" id="chatInput" type="text"
          placeholder="Topic, question, or arXiv ID / URL…"
          onkeydown="if(event.key==='Enter')send()">
        <button class="send" id="sendBtn" onclick="send()">Search</button>
      </div>
    </div>

    <div class="card" style="flex:1;overflow:hidden;display:flex;flex-direction:column">
      <div class="card-title">Search History</div>
      <div class="history-list" id="historyList">
        <div class="history-empty">No searches yet.</div>
      </div>
    </div>

    <div class="card" style="font-size:12px;color:#6b6b7e;line-height:1.7">
      <div class="card-title">Tips</div>
      <strong style="color:#e2e2e8">Topic mode</strong> — type a research area
      and the agent searches arXiv + Semantic Scholar, then synthesises findings
      across papers with citations.<br><br>
      <strong style="color:#e2e2e8">arXiv mode</strong> — paste an arXiv URL or
      ID (e.g. <span style="color:#a5b4fc">2305.11206</span>) to get an instant
      structured summary with key contributions and limitations.<br><br>
      <strong style="color:#e2e2e8">Follow-up</strong> — ask "what does this build
      on?" to fetch reference lists.
    </div>
  </div>

  <!-- Right panel: results -->
  <div class="result-panel" id="resultPanel">
    <div class="result-empty">Results will appear here after you search.</div>
  </div>

</div>

<script>
const CHIPS = [
  "LoRA and parameter-efficient fine-tuning",
  "Mixture of Experts in LLMs",
  "Retrieval-Augmented Generation (RAG)",
  "Diffusion models for image generation",
  "Reinforcement learning from human feedback",
  "Vision-language models (VLMs)",
  "Graph neural networks",
  "Mechanistic interpretability of transformers",
  "Protein structure prediction",
  "Quantum computing algorithms",
]

const history = []

function initChips() {
  const el = document.getElementById('chips')
  const shown = CHIPS.slice(0, 6)
  el.innerHTML = shown.map(c =>
    `<span class="chip" onclick="fillAndSend(this.textContent)">${c}</span>`
  ).join('')
}

function fillAndSend(text) {
  document.getElementById('chatInput').value = text
  send()
}

async function send() {
  const inp = document.getElementById('chatInput')
  const btn = document.getElementById('sendBtn')
  const panel = document.getElementById('resultPanel')
  const q = inp.value.trim()
  if (!q) return

  btn.disabled = true; btn.textContent = 'Searching…'
  panel.innerHTML = '<div class="thinking"><span class="spinner">⟳</span> Searching arXiv and Semantic Scholar… this may take 15–30 seconds.</div>'

  try {
    const r = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ question: q, thread_id: 'main' })
    })
    if (!r.ok) {
      const e = await r.json()
      throw new Error(e.error || r.statusText)
    }
    const data = await r.json()
    panel.innerHTML = '<div class="result-content fadein">' + renderMd(data.answer) + '</div>'
    addHistory(q)
  } catch(err) {
    panel.innerHTML = '<div style="color:#f87171;padding:16px">Error: ' + esc(err.message) + '</div>'
  } finally {
    btn.disabled = false; btn.textContent = 'Search'
  }
}

function addHistory(q) {
  history.unshift(q)
  const el = document.getElementById('historyList')
  el.innerHTML = history.slice(0, 20).map(h =>
    `<div class="history-item" onclick="fillAndSend(${JSON.stringify(h)})">${esc(h)}</div>`
  ).join('')
}

function renderMd(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/^### (.+)$/gm, '<div style="font-size:13px;font-weight:700;color:#c4b5fd;margin:16px 0 6px">$1</div>')
    .replace(/^## (.+)$/gm, '<div style="font-size:15px;font-weight:700;color:#fff;margin:20px 0 8px;padding-bottom:6px;border-bottom:1px solid #2d2d4a">$1</div>')
    .replace(/^# (.+)$/gm, '<div style="font-size:16px;font-weight:700;color:#fff;margin:0 0 12px">$1</div>')
    .replace(/^- (.+)$/gm, '<div style="padding-left:16px;margin:4px 0">• $1</div>')
    .replace(/^\d+\. (.+)$/gm, '<div style="padding-left:16px;margin:4px 0">$1</div>')
    .replace(/`([^`]+)`/g, '<code style="background:#1e1b4b;color:#a5b4fc;padding:1px 5px;border-radius:4px;font-size:12px">$1</code>')
    .replace(/---/g, '<hr>')
    .replace(/\\n/g, '<br>').replace(/\n/g, '<br>')
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

initChips()
</script>
</body>
</html>
"""
