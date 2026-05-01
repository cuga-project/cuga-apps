"""
HTML UI for the Webpage Summarizer demo app.
Exported as _HTML — a single self-contained string served by the FastAPI root endpoint.
"""

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Webpage Summarizer</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #0f1117;
    --card:      #1a1a2e;
    --border:    #2d2d4a;
    --accent:    #6c63ff;
    --accent2:   #00d4aa;
    --text:      #e2e8f0;
    --muted:     #8892a4;
    --danger:    #ff4d6d;
    --success:   #00c896;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
    font-size: 14px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  /* ── Header ── */
  header {
    position: sticky;
    top: 0;
    z-index: 100;
    background: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 12px 24px;
    display: flex;
    align-items: center;
    gap: 16px;
  }
  header h1 { font-size: 18px; font-weight: 700; letter-spacing: 0.5px; }
  header h1 span { color: var(--accent); }

  .status-badge {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--muted);
    margin-left: auto;
  }
  .status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--success);
    animation: pulse 2s infinite;
  }
  .status-dot.busy { background: var(--accent); animation: none; }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.4; }
  }

  /* ── Main layout ── */
  main {
    display: grid;
    grid-template-columns: 420px 1fr;
    gap: 0;
    flex: 1;
    overflow: hidden;
    height: calc(100vh - 57px);
  }

  /* ── Left panel: chat ── */
  .chat-panel {
    background: var(--card);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .panel-title {
    padding: 14px 18px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
  }

  /* Prompt chips */
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
  }
  .chip {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 12px;
    color: var(--muted);
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .chip:hover {
    border-color: var(--accent);
    color: var(--text);
  }

  /* Messages */
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    scroll-behavior: smooth;
  }
  .messages::-webkit-scrollbar { width: 4px; }
  .messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  .msg {
    max-width: 100%;
    padding: 10px 14px;
    border-radius: 10px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .msg.user {
    background: var(--accent);
    color: #fff;
    align-self: flex-end;
    border-bottom-right-radius: 3px;
  }
  .msg.agent {
    background: var(--bg);
    border: 1px solid var(--border);
    align-self: flex-start;
    border-bottom-left-radius: 3px;
    font-size: 13px;
  }
  .msg.error {
    background: rgba(255,77,109,0.15);
    border: 1px solid var(--danger);
    color: var(--danger);
    align-self: flex-start;
  }
  .msg.thinking {
    color: var(--muted);
    font-style: italic;
    border: 1px dashed var(--border);
    align-self: flex-start;
  }

  /* Input row */
  .input-row {
    display: flex;
    gap: 8px;
    padding: 14px 16px;
    border-top: 1px solid var(--border);
  }
  .input-row input {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 14px;
    color: var(--text);
    font-size: 14px;
    outline: none;
    transition: border-color 0.15s;
  }
  .input-row input:focus { border-color: var(--accent); }
  .input-row input::placeholder { color: var(--muted); }
  .btn {
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .btn:hover  { opacity: 0.85; }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }

  /* ── Right panel: summary view ── */
  .summary-panel {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .summary-header {
    padding: 14px 20px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .summary-header .url-badge {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 3px 10px;
    font-size: 11px;
    color: var(--accent2);
    font-family: monospace;
    max-width: 400px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .summary-content {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
  }
  .summary-content::-webkit-scrollbar { width: 4px; }
  .summary-content::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--muted);
    gap: 12px;
    text-align: center;
  }
  .empty-state .icon { font-size: 48px; opacity: 0.3; }
  .empty-state p { font-size: 13px; max-width: 280px; line-height: 1.6; }

  /* Summary card */
  .summary-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
  }
  .summary-card .card-url {
    font-size: 11px;
    color: var(--accent2);
    font-family: monospace;
    margin-bottom: 6px;
    word-break: break-all;
  }
  .summary-card .card-title {
    font-size: 16px;
    font-weight: 700;
    margin-bottom: 12px;
    color: var(--text);
  }
  .summary-card .card-body {
    font-size: 13px;
    line-height: 1.75;
    color: #c8d0dc;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .summary-card .card-time {
    font-size: 11px;
    color: var(--muted);
    margin-top: 12px;
    text-align: right;
  }

  /* History sidebar */
  .history-list {
    border-top: 1px solid var(--border);
    padding: 14px 20px;
    max-height: 180px;
    overflow-y: auto;
  }
  .history-list::-webkit-scrollbar { width: 4px; }
  .history-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
  .history-title {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--muted);
    font-weight: 600;
    margin-bottom: 8px;
  }
  .history-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 0;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
  }
  .history-item:last-child { border-bottom: none; }
  .history-item:hover .history-url { color: var(--accent); }
  .history-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent2); flex-shrink: 0; }
  .history-url {
    font-size: 12px;
    color: var(--muted);
    font-family: monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    transition: color 0.15s;
  }
  .history-time { font-size: 11px; color: var(--muted); flex-shrink: 0; }
</style>
</head>
<body>

<header>
  <h1>Webpage <span>Summarizer</span></h1>
  <div class="status-badge">
    <div class="status-dot" id="statusDot"></div>
    <span id="statusText">Ready</span>
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
      <button class="btn" id="sendBtn" onclick="sendMessage()">Send</button>
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
    const m = text.match(/https?:\\/\\/[^\\s"'<>)]+/);
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
</body>
</html>
"""
