"""
Wiki Dive UI — self-contained HTML page served by FastAPI.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation. Layout: left input/history/help column, right results panel.
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { background: var(--cds-background); }

  .layout {
    display: grid; grid-template-columns: 1fr 1fr; gap: var(--cds-sp-06);
    max-width: 80rem; margin: 0 auto;
    padding: var(--cds-sp-06) var(--cds-sp-06);
    height: calc(100vh - 3rem);
  }
  @media (max-width: 820px) { .layout { grid-template-columns: 1fr; height: auto; } }

  .panel { display: flex; flex-direction: column; gap: var(--cds-sp-05); overflow: hidden; }

  .card-title {
    font-size: 0.75rem; font-weight: 600; color: var(--cds-text-secondary);
    letter-spacing: 0.32px; text-transform: uppercase; margin-bottom: var(--cds-sp-04);
  }

  .chips { display: flex; flex-wrap: wrap; gap: var(--cds-sp-03); margin-bottom: var(--cds-sp-04); }
  .chip {
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    border-radius: 0.9375rem; padding: var(--cds-sp-02) var(--cds-sp-04);
    font-size: 0.75rem; color: var(--cds-text-secondary); cursor: pointer;
    transition: all var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .chip:hover { background: var(--cds-interactive); border-color: var(--cds-interactive); color: #fff; }

  .chat-row { display: flex; gap: 0; }
  .chat-input { flex: 1; border-bottom: 1px solid var(--cds-border-strong); }
  .chat-row .cds-btn { flex: none; justify-content: center; }

  .result-panel {
    flex: 1; overflow-y: auto;
    background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-06);
  }
  .result-empty {
    color: var(--cds-text-placeholder); font-size: 0.875rem;
    text-align: center; padding: var(--cds-sp-09) 0;
  }
  .result-content { font-size: 0.875rem; line-height: 1.7; color: var(--cds-text-primary); }
  .result-content a { color: var(--cds-link-primary); }
  .result-content a:hover { color: var(--cds-link-hover); text-decoration: underline; }
  .result-content strong { color: var(--cds-text-primary); font-weight: 600; }
  .result-content hr { border: none; border-top: 1px solid var(--cds-border-subtle); margin: var(--cds-sp-05) 0; }

  @keyframes fadein { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
  .fadein { animation: fadein 0.25s ease; }

  .thinking {
    color: var(--cds-text-secondary); font-size: 0.875rem; text-align: center;
    padding: var(--cds-sp-07) 0; display: flex; flex-direction: column;
    align-items: center; gap: var(--cds-sp-05);
  }

  .history-list { max-height: 14rem; overflow-y: auto; }
  .history-item {
    padding: var(--cds-sp-03) var(--cds-sp-04); cursor: pointer;
    font-size: 0.75rem; color: var(--cds-text-secondary);
    border-left: 2px solid transparent; margin-bottom: var(--cds-sp-02);
    transition: all var(--cds-dur-fast) var(--cds-ease-productive);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .history-item:hover { background: var(--cds-layer-hover); border-left-color: var(--cds-interactive); color: var(--cds-text-primary); }
  .history-empty { font-size: 0.75rem; color: var(--cds-text-placeholder); }

  .help { font-size: 0.8125rem; color: var(--cds-text-secondary); line-height: 1.6; }
  .help strong { color: var(--cds-text-primary); }

  .md-h3 { font-size: 0.875rem; font-weight: 600; color: var(--cds-link-primary); margin: var(--cds-sp-05) 0 var(--cds-sp-03); }
  .md-h2 { font-size: 1rem; font-weight: 600; color: var(--cds-text-primary); margin: var(--cds-sp-06) 0 var(--cds-sp-03); padding-bottom: var(--cds-sp-03); border-bottom: 1px solid var(--cds-border-subtle); }
  .md-h1 { font-size: 1.125rem; font-weight: 600; color: var(--cds-text-primary); margin: 0 0 var(--cds-sp-04); }
  .md-li { padding-left: var(--cds-sp-05); margin: var(--cds-sp-02) 0; }
  .md-code { background: var(--cds-layer-accent); color: var(--cds-link-primary); padding: 1px 5px; font-family: var(--cds-font-mono); font-size: 0.75rem; }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Wiki&nbsp;Dive</div>
  <div class="cds-header__actions">
    <span class="cds-helper-01">Deep Wikipedia Research · Powered by CugaAgent</span>
    <span class="cds-tag cds-tag--green">No API keys required</span>
  </div>
</header>

<div class="layout">

  <!-- Left panel: input -->
  <div class="panel">
    <div class="cds-tile">
      <div class="card-title">Research any topic in depth</div>
      <div class="chips" id="chips"></div>
      <div class="chat-row">
        <input class="cds-input chat-input" id="chatInput" type="text"
          placeholder="Topic, concept, historical event, person…"
          onkeydown="if(event.key==='Enter')send()">
        <button class="cds-btn" id="sendBtn" onclick="send()" style="min-width:8rem">Dive in</button>
      </div>
    </div>

    <div class="cds-tile" style="flex:1;overflow:hidden;display:flex;flex-direction:column">
      <div class="card-title">Search History</div>
      <div class="history-list" id="historyList">
        <div class="history-empty">No searches yet.</div>
      </div>
    </div>

    <div class="cds-tile help">
      <div class="card-title">How it works</div>
      The agent goes beyond a Wikipedia search — it reads articles
      <strong>section by section</strong>, follows
      <strong>See Also</strong> links to pull related
      concepts, and synthesises a structured report with
      <strong>citations</strong> and cross-article
      connections.<br><br>
      Great for: understanding complex topics from first principles, building
      mental models, or preparing to read primary sources.
    </div>
  </div>

  <!-- Right panel: results -->
  <div class="result-panel" id="resultPanel">
    <div class="result-empty">Results will appear here after you search.</div>
  </div>

</div>

<script>
const CHIPS = [
  "How does transformer attention work?",
  "The French Revolution",
  "Quantum entanglement explained",
  "CRISPR gene editing",
  "The Byzantine Empire",
  "How does the immune system work?",
  "Game theory and Nash equilibrium",
  "The history of the internet",
  "Plate tectonics",
  "The philosophy of consciousness",
]

const history = []

function initChips() {
  const el = document.getElementById('chips')
  el.innerHTML = CHIPS.slice(0, 6).map(c =>
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

  btn.disabled = true; btn.textContent = 'Reading…'
  panel.innerHTML = '<div class="thinking"><div class="cds-spinner"></div> Reading Wikipedia articles section by section… this may take 20–40 seconds.</div>'

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
    panel.innerHTML = '<div class="cds-notification cds-notification--error">Error: ' + esc(err.message) + '</div>'
  } finally {
    btn.disabled = false; btn.textContent = 'Dive in'
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
    .replace(/^### (.+)$/gm, '<div class="md-h3">$1</div>')
    .replace(/^## (.+)$/gm, '<div class="md-h2">$1</div>')
    .replace(/^# (.+)$/gm, '<div class="md-h1">$1</div>')
    .replace(/^- (.+)$/gm, '<div class="md-li">• $1</div>')
    .replace(/^\d+\. (.+)$/gm, '<div class="md-li">$1</div>')
    .replace(/`([^`]+)`/g, '<code class="md-code">$1</code>')
    .replace(/---/g, '<hr>')
    .replace(/\\n/g, '<br>').replace(/\n/g, '<br>')
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

initChips()
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("Wiki Dive")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
