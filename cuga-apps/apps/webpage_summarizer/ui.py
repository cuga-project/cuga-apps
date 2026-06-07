"""
HTML UI for the Webpage Summarizer demo app.
Exported as _HTML — a single self-contained string served by the FastAPI root endpoint.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation. Layout: left chat panel, right latest-summary + history panel.
All ids, fetch routes, POST body shapes, and JS function names are preserved.
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { background: var(--cds-background); display: flex; flex-direction: column; }

  /* ── Main layout ── */
  main {
    display: grid;
    grid-template-columns: 420px 1fr;
    gap: 0;
    flex: 1;
    overflow: hidden;
    height: calc(100vh - 3rem);
  }
  @media (max-width: 820px) { main { grid-template-columns: 1fr; height: auto; } }

  /* ── Left panel: chat ── */
  .chat-panel {
    background: var(--cds-layer-01);
    border-right: 1px solid var(--cds-border-subtle);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .panel-title {
    padding: var(--cds-sp-04) var(--cds-sp-05);
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.32px;
    color: var(--cds-text-secondary);
    border-bottom: 1px solid var(--cds-border-subtle);
  }

  /* Prompt chips */
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--cds-sp-03);
    padding: var(--cds-sp-04) var(--cds-sp-05);
    border-bottom: 1px solid var(--cds-border-subtle);
  }
  .chip {
    background: var(--cds-layer-02);
    border: 1px solid var(--cds-border-subtle);
    border-radius: 0.9375rem;
    padding: var(--cds-sp-02) var(--cds-sp-04);
    font-size: 0.75rem;
    color: var(--cds-text-secondary);
    cursor: pointer;
    transition: all var(--cds-dur-mod) var(--cds-ease-productive);
    white-space: nowrap;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .chip:hover {
    border-color: var(--cds-interactive);
    background: var(--cds-interactive);
    color: #fff;
  }

  /* Messages */
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: var(--cds-sp-05);
    display: flex;
    flex-direction: column;
    gap: var(--cds-sp-04);
    scroll-behavior: smooth;
  }

  .msg {
    max-width: 100%;
    padding: var(--cds-sp-04) var(--cds-sp-05);
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
    font-size: 0.875rem;
  }
  .msg.user {
    background: var(--cds-interactive);
    color: #fff;
    align-self: flex-end;
  }
  .msg.agent {
    background: var(--cds-layer-02);
    border: 1px solid var(--cds-border-subtle);
    align-self: flex-start;
    font-size: 0.8125rem;
    color: var(--cds-text-primary);
  }
  .msg.error {
    background: var(--cds-support-error-bg);
    border-left: 3px solid var(--cds-support-error);
    color: var(--cds-text-primary);
    align-self: stretch;
  }
  .msg.thinking {
    color: var(--cds-text-secondary);
    border: 1px dashed var(--cds-border-strong);
    align-self: flex-start;
    display: inline-flex;
    align-items: center;
    gap: var(--cds-sp-04);
  }

  /* Input row */
  .input-row {
    display: flex;
    gap: 0;
    padding: var(--cds-sp-05);
    border-top: 1px solid var(--cds-border-subtle);
    background: var(--cds-layer-01);
  }
  .input-row input {
    flex: 1;
    background: var(--cds-field-01);
    color: var(--cds-text-primary);
    border: none;
    border-bottom: 1px solid var(--cds-border-strong);
    min-height: 3rem;
    padding: 0 var(--cds-sp-05);
    font-family: var(--cds-font-sans);
    font-size: 0.875rem;
    letter-spacing: 0.16px;
    transition: outline var(--cds-dur-fast) var(--cds-ease-productive);
  }
  .input-row input:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; }
  .input-row input::placeholder { color: var(--cds-text-placeholder); }
  .input-row .btn { flex: none; min-width: 6rem; }

  /* ── Right panel: summary view ── */
  .summary-panel {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--cds-background);
  }

  .summary-header {
    padding: var(--cds-sp-04) var(--cds-sp-06);
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.32px;
    color: var(--cds-text-secondary);
    border-bottom: 1px solid var(--cds-border-subtle);
    display: flex;
    align-items: center;
    gap: var(--cds-sp-04);
  }
  .summary-header .url-badge {
    background: var(--cds-layer-01);
    border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-02) var(--cds-sp-04);
    font-size: 0.6875rem;
    color: var(--cds-link-primary);
    font-family: var(--cds-font-mono);
    text-transform: none;
    letter-spacing: 0;
    max-width: 400px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .summary-content {
    flex: 1;
    overflow-y: auto;
    padding: var(--cds-sp-06);
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--cds-text-placeholder);
    gap: var(--cds-sp-04);
    text-align: center;
  }
  .empty-state .icon { font-size: 48px; opacity: 0.35; }
  .empty-state p { font-size: 0.8125rem; max-width: 280px; line-height: 1.6; }

  /* Summary card */
  .summary-card {
    background: var(--cds-layer-01);
    border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-06);
    margin-bottom: var(--cds-sp-06);
  }
  .summary-card .card-url {
    font-size: 0.6875rem;
    color: var(--cds-link-primary);
    font-family: var(--cds-font-mono);
    margin-bottom: var(--cds-sp-03);
    word-break: break-all;
  }
  .summary-card .card-title {
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: var(--cds-sp-04);
    color: var(--cds-text-primary);
  }
  .summary-card .card-body {
    font-size: 0.8125rem;
    line-height: 1.75;
    color: var(--cds-text-primary);
    white-space: pre-wrap;
    word-break: break-word;
  }
  .summary-card .card-time {
    font-size: 0.6875rem;
    color: var(--cds-text-helper);
    margin-top: var(--cds-sp-04);
    text-align: right;
    font-family: var(--cds-font-mono);
  }

  /* History sidebar */
  .history-list {
    border-top: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-05) var(--cds-sp-06);
    max-height: 180px;
    overflow-y: auto;
    background: var(--cds-layer-01);
  }
  .history-title {
    font-size: 0.6875rem;
    text-transform: uppercase;
    letter-spacing: 0.32px;
    color: var(--cds-text-secondary);
    font-weight: 600;
    margin-bottom: var(--cds-sp-03);
  }
  .history-item {
    display: flex;
    align-items: center;
    gap: var(--cds-sp-03);
    padding: var(--cds-sp-03) 0;
    border-bottom: 1px solid var(--cds-border-subtle);
    cursor: pointer;
  }
  .history-item:last-child { border-bottom: none; }
  .history-item:hover .history-url { color: var(--cds-link-primary); }
  .history-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--cds-interactive); flex-shrink: 0; }
  .history-url {
    font-size: 0.75rem;
    color: var(--cds-text-secondary);
    font-family: var(--cds-font-mono);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    transition: color var(--cds-dur-fast) var(--cds-ease-productive);
  }
  .history-time { font-size: 0.6875rem; color: var(--cds-text-helper); flex-shrink: 0; font-family: var(--cds-font-mono); }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Webpage&nbsp;Summarizer</div>
  <div class="cds-header__actions status-badge">
    <div class="status-dot" id="statusDot"></div>
    <span id="statusText" class="cds-helper-01">Ready</span>
  </div>
</header>

<main>
  <!-- Left: Chat -->
  <div class="chat-panel">
    <div class="panel-title">Chat with the agent</div>

    <div class="chips">
      <div class="chip" onclick="sendChip(this)">https://en.wikipedia.org/wiki/Artificial_intelligence</div>
      <div class="chip" onclick="sendChip(this)">Summarize https://www.bbc.com/news</div>
      <div class="chip" onclick="sendChip(this)">What is this page about? https://python.org</div>
      <div class="chip" onclick="sendChip(this)">Key takeaways from https://openai.com/blog</div>
      <div class="chip" onclick="sendChip(this)">Summarize https://github.com/langchain-ai/langchain</div>
      <div class="chip" onclick="sendChip(this)">List links on https://news.ycombinator.com</div>
      <div class="chip" onclick="sendChip(this)">What does https://anthropic.com talk about?</div>
    </div>

    <div class="messages" id="messages"></div>

    <div class="input-row">
      <input
        type="text"
        id="userInput"
        placeholder="Paste a URL or ask a question…"
        onkeydown="if(event.key==='Enter') sendMessage()"
      />
      <button class="cds-btn btn" id="sendBtn" onclick="sendMessage()">Send</button>
    </div>
  </div>

  <!-- Right: Summary display -->
  <div class="summary-panel">
    <div class="summary-header">
      <span>Latest Summary</span>
      <div class="url-badge" id="lastUrl">—</div>
    </div>

    <div class="summary-content" id="summaryContent">
      <div class="empty-state" id="emptyState">
        <div class="icon">🌐</div>
        <p>Paste any URL into the chat and the agent will fetch and summarise the page for you.</p>
      </div>
    </div>

    <div class="history-list" id="historySection" style="display:none">
      <div class="history-title">Previously summarized</div>
      <div id="historyItems"></div>
    </div>
  </div>
</main>

<style>
  .status-badge { display: flex; align-items: center; gap: var(--cds-sp-03); }
  .status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--cds-support-success);
    animation: pulse 2s infinite;
  }
  .status-dot.busy { background: var(--cds-interactive); animation: none; }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.4; }
  }
</style>

<script>
  const messagesEl  = document.getElementById('messages');
  const inputEl     = document.getElementById('userInput');
  const sendBtn     = document.getElementById('sendBtn');
  const statusDot   = document.getElementById('statusDot');
  const statusText  = document.getElementById('statusText');
  const summaryContent = document.getElementById('summaryContent');
  const emptyState  = document.getElementById('emptyState');
  const lastUrlEl   = document.getElementById('lastUrl');
  const historySection = document.getElementById('historySection');
  const historyItems = document.getElementById('historyItems');

  // History of summaries: [{url, text, time}]
  const history = [];

  function setStatus(busy, label) {
    statusDot.className = 'status-dot' + (busy ? ' busy' : '');
    statusText.textContent = label;
  }

  function addMessage(text, cls) {
    const div = document.createElement('div');
    div.className = 'msg ' + cls;
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function extractUrl(text) {
    const m = text.match(/https?:\/\/[^\s"'<>)]+/);
    return m ? m[0] : null;
  }

  function timeStr() {
    return new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  }

  function showSummary(url, answer) {
    // Remove empty state
    emptyState.style.display = 'none';

    // Update URL badge
    lastUrlEl.textContent = url || 'agent response';
    lastUrlEl.title = url || '';

    // Remove previous summary card
    const old = summaryContent.querySelector('.summary-card');
    if (old) old.remove();

    // Build new card
    const card = document.createElement('div');
    card.className = 'summary-card';
    card.innerHTML =
      '<div class="card-url">' + escHtml(url || '') + '</div>' +
      '<div class="card-body">' + escHtml(answer) + '</div>' +
      '<div class="card-time">' + timeStr() + '</div>';
    summaryContent.prepend(card);

    // Add to history
    if (url) {
      history.unshift({ url, text: answer, time: timeStr() });
      renderHistory();
    }
  }

  function renderHistory() {
    if (history.length < 2) return;
    historySection.style.display = 'block';
    historyItems.innerHTML = '';
    history.slice(1, 8).forEach(function(h) {
      const item = document.createElement('div');
      item.className = 'history-item';
      item.title = h.url;
      item.onclick = function() { showSummary(h.url, h.text); };
      item.innerHTML =
        '<div class="history-dot"></div>' +
        '<div class="history-url">' + escHtml(h.url) + '</div>' +
        '<div class="history-time">' + h.time + '</div>';
      historyItems.appendChild(item);
    });
  }

  function escHtml(s) {
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function sendMessage() {
    const question = inputEl.value.trim();
    if (!question) return;

    inputEl.value = '';
    sendBtn.disabled = true;
    setStatus(true, 'Thinking…');

    addMessage(question, 'user');
    const thinking = addMessage('Fetching and summarising…', 'thinking');

    try {
      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      const data = await res.json();
      thinking.remove();

      if (!res.ok) {
        addMessage('Error: ' + (data.answer || res.statusText), 'error');
      } else {
        addMessage(data.answer, 'agent');
        const url = extractUrl(question);
        showSummary(url, data.answer);
      }
    } catch (err) {
      thinking.remove();
      addMessage('Network error: ' + err.message, 'error');
    } finally {
      sendBtn.disabled = false;
      setStatus(false, 'Ready');
    }
  }

  function sendChip(el) {
    inputEl.value = el.textContent.trim();
    sendMessage();
  }
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("Webpage Summarizer")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
