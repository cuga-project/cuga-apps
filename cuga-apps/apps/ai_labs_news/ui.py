"""
HTML UI for the AI Labs News demo app.
Exported as _HTML — a single self-contained string served by FastAPI's "/" route.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation.

Layout:
  Left  — Chat panel: prompt chips, message log, input field
  Right — Live data panel: headline + cross-lab themes + news item cards
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { background: var(--cds-background); display: flex; flex-direction: column; }

  main {
    display: grid;
    grid-template-columns: 26rem 1fr;
    gap: 0; flex: 1; min-height: 0; overflow: hidden;
  }
  @media (max-width: 820px) {
    main { grid-template-columns: 1fr; height: auto; }
  }

  /* App intro band: one-line blurb + the tools this app uses */
  .app-intro {
    display: flex; align-items: center; gap: var(--cds-sp-05);
    flex-wrap: wrap;
    padding: var(--cds-sp-04) var(--cds-sp-06);
    background: var(--cds-layer-01);
    border-bottom: 1px solid var(--cds-border-subtle);
  }
  .app-intro__blurb {
    font-size: 0.8125rem; color: var(--cds-text-secondary);
    line-height: 1.5; max-width: 48rem;
  }
  .app-intro__blurb strong { color: var(--cds-text-primary); font-weight: 600; }
  .app-intro__tools {
    margin-left: auto; display: flex; flex-wrap: wrap; gap: var(--cds-sp-03);
    align-items: center;
  }
  .app-intro__tools .tools-label {
    font-size: 0.625rem; text-transform: uppercase; letter-spacing: 0.32px;
    color: var(--cds-text-helper); margin-right: var(--cds-sp-02);
  }
  .tool-pill {
    font-size: 0.6875rem; color: var(--cds-text-secondary);
    background: var(--cds-layer-accent); border: 1px solid var(--cds-border-subtle);
    border-radius: 0.9375rem; padding: var(--cds-sp-01) var(--cds-sp-04);
    white-space: nowrap;
  }

  /* ── Chat panel ──────────────────────────────────────────────────────── */
  .chat-panel {
    background: var(--cds-layer-01);
    border-right: 1px solid var(--cds-border-subtle);
    display: flex; flex-direction: column; overflow: hidden;
  }
  .panel-title {
    padding: var(--cds-sp-04) var(--cds-sp-05);
    font-size: 0.75rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.32px;
    color: var(--cds-text-secondary);
    border-bottom: 1px solid var(--cds-border-subtle);
  }

  .chips {
    display: flex; flex-wrap: wrap; gap: var(--cds-sp-03);
    padding: var(--cds-sp-04) var(--cds-sp-05);
    border-bottom: 1px solid var(--cds-border-subtle);
  }
  .chip {
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    border-radius: 0.9375rem; padding: var(--cds-sp-02) var(--cds-sp-04);
    font-size: 0.75rem; color: var(--cds-text-secondary); cursor: pointer;
    transition: all var(--cds-dur-mod) var(--cds-ease-productive); white-space: nowrap;
  }
  .chip:hover { background: var(--cds-interactive); border-color: var(--cds-interactive); color: #fff; }

  .messages {
    flex: 1; overflow-y: auto; padding: var(--cds-sp-05);
    display: flex; flex-direction: column; gap: var(--cds-sp-04);
    scroll-behavior: smooth;
  }

  .msg {
    max-width: 100%; padding: var(--cds-sp-04) var(--cds-sp-05);
    line-height: 1.6; white-space: pre-wrap;
    word-break: break-word; font-size: 0.8125rem;
  }
  .msg.user {
    background: var(--cds-interactive); color: #fff;
    align-self: flex-end; font-size: 0.875rem;
  }
  .msg.agent {
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    align-self: flex-start; color: var(--cds-text-primary);
  }
  .msg.error {
    background: var(--cds-support-error-bg);
    border-left: 3px solid var(--cds-support-error);
    color: var(--cds-text-primary); align-self: flex-start;
  }
  .msg.thinking {
    color: var(--cds-text-secondary); font-style: italic;
    border: 1px dashed var(--cds-border-subtle); align-self: flex-start;
  }

  .input-row {
    display: flex; gap: 0;
    padding: var(--cds-sp-05);
    border-top: 1px solid var(--cds-border-subtle);
  }
  .input-row input {
    flex: 1; min-height: 3rem;
    background: var(--cds-field-01); color: var(--cds-text-primary);
    border: none; border-bottom: 1px solid var(--cds-border-strong);
    padding: 0 var(--cds-sp-05);
    font-family: var(--cds-font-sans);
    font-size: 0.875rem; letter-spacing: 0.16px; outline: none;
    transition: outline var(--cds-dur-fast) var(--cds-ease-productive);
  }
  .input-row input:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; }
  .input-row input::placeholder { color: var(--cds-text-placeholder); }
  .input-row .btn { flex: none; min-width: 6rem; }

  /* ── Right data panel ────────────────────────────────────────────────── */
  .data-panel { display: flex; flex-direction: column; overflow: hidden; }
  .data-panel-header {
    padding: var(--cds-sp-04) var(--cds-sp-06);
    font-size: 0.75rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.32px;
    color: var(--cds-text-secondary);
    border-bottom: 1px solid var(--cds-border-subtle);
    display: flex; align-items: center; gap: var(--cds-sp-04);
  }
  .refresh-badge { margin-left: auto; font-size: 0.6875rem; color: var(--cds-text-helper); }

  .data-scroll {
    flex: 1; overflow-y: auto; padding: var(--cds-sp-06);
    display: flex; flex-direction: column; gap: var(--cds-sp-06);
  }

  .empty-state {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 100%; color: var(--cds-text-secondary); gap: var(--cds-sp-05);
    text-align: center; padding: var(--cds-sp-08);
  }
  .empty-state .icon { font-size: 3.5rem; opacity: 0.4; }
  .empty-state p { font-size: 0.8125rem; max-width: 20rem; line-height: 1.7; }
  .empty-state .hint {
    font-size: 0.75rem; color: var(--cds-link-primary);
    border: 1px dashed var(--cds-interactive);
    padding: var(--cds-sp-03) var(--cds-sp-05); border-radius: 0.9375rem;
  }

  .section-title {
    font-size: 0.75rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.32px;
    color: var(--cds-text-secondary); margin-bottom: var(--cds-sp-04);
    display: flex; align-items: center; gap: var(--cds-sp-03);
  }
  .section-title::after {
    content: ''; flex: 1; height: 1px; background: var(--cds-border-subtle);
  }

  .headline-block {
    background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    border-left: 3px solid var(--cds-interactive); padding: var(--cds-sp-05);
  }
  .headline-block .hl { font-size: 0.9375rem; font-weight: 600; line-height: 1.4; }
  .themes { margin-top: var(--cds-sp-04); display: flex; flex-wrap: wrap; gap: var(--cds-sp-03); }
  .tag {
    display: inline-flex; align-items: center;
    background: var(--cds-layer-accent); border: 1px solid transparent;
    border-radius: 0.9375rem; padding: var(--cds-sp-02) var(--cds-sp-04);
    font-size: 0.75rem; color: var(--cds-text-primary); line-height: 1;
  }
  .tag.theme { background: var(--cds-support-info-bg); color: var(--cds-link-primary); }

  /* ── News item cards ─────────────────────────────────────────────────── */
  .news-card {
    background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-05);
    transition: border-color var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .news-card:hover { border-color: var(--cds-border-strong); }
  .news-top {
    display: flex; align-items: center; gap: var(--cds-sp-03);
    margin-bottom: var(--cds-sp-03); flex-wrap: wrap;
  }
  .lab-pill {
    background: var(--cds-interactive); color: #fff;
    border-radius: 0.9375rem; padding: 1px var(--cds-sp-04);
    font-size: 0.6875rem; font-weight: 600; letter-spacing: 0.16px;
  }
  .news-date { font-size: 0.6875rem; color: var(--cds-text-helper); }
  .news-title { font-size: 0.875rem; font-weight: 600; line-height: 1.35; }
  .news-title a { color: var(--cds-link-primary); text-decoration: none; }
  .news-title a:hover { text-decoration: underline; }
  .news-summary {
    font-size: 0.8125rem; color: var(--cds-text-secondary); line-height: 1.6;
    margin-top: var(--cds-sp-03);
  }
  .news-tags { margin-top: var(--cds-sp-03); display: flex; flex-wrap: wrap; gap: var(--cds-sp-02); }
  .news-tags .tag { font-size: 0.6875rem; padding: 1px var(--cds-sp-03); }

  /* Status dot */
  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--cds-support-success); animation: pulse 2s infinite;
  }
  .status-dot.busy { background: var(--cds-support-warning); animation: none; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
  .status-badge { display: flex; align-items: center; gap: var(--cds-sp-03); }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name">
    <span class="cds-header__prefix">IBM</span>&nbsp;AI&nbsp;Labs&nbsp;News
  </div>
  <div class="cds-header__actions">
    <span class="status-badge">
      <span class="status-dot" id="statusDot"></span>
      <span class="cds-helper-01" id="statusText">Ready</span>
    </span>
  </div>
</header>

<div class="app-intro">
  <div class="app-intro__blurb">
    <strong>AI Labs News.</strong> A live digest of the latest posts from the major AI labs — OpenAI, Anthropic, Google DeepMind, Microsoft &amp; IBM Research, and more — pulled from their blog feeds and grouped by cross-lab theme.
  </div>
  <div class="app-intro__tools">
    <span class="tools-label">Tools</span>
    <span class="tool-pill">📰 RSS / Atom feeds</span>
    <span class="tool-pill">🏷 Lab registry</span>
    <span class="tool-pill">🧩 Theme digest</span>
    <span class="tool-pill">🔁 Dedupe &amp; merge</span>
  </div>
</div>

<main>
  <div class="chat-panel">
    <div class="panel-title">Chat with the agent</div>

    <div class="chips">
      <div class="chip" onclick="sendChip(this)">What's new in AI this week?</div>
      <div class="chip" onclick="sendChip(this)">Latest from OpenAI and Anthropic</div>
      <div class="chip" onclick="sendChip(this)">Recent Microsoft and IBM Research posts</div>
      <div class="chip" onclick="sendChip(this)">Anything new from Google DeepMind?</div>
      <div class="chip" onclick="sendChip(this)">AI agent news across the labs</div>
      <div class="chip" onclick="sendChip(this)">Which labs do you cover?</div>
    </div>

    <div class="messages" id="messages"></div>

    <div class="input-row">
      <input type="text" id="userInput"
        placeholder="Ask for the latest AI lab news…"
        onkeydown="if(event.key==='Enter') sendMessage()" />
      <button class="cds-btn btn" id="sendBtn" onclick="sendMessage()">Send</button>
    </div>
  </div>

  <div class="data-panel">
    <div class="data-panel-header">
      <span>Latest from the Labs</span>
      <span class="refresh-badge" id="refreshBadge">auto-refresh 10s</span>
    </div>
    <div class="data-scroll" id="dataScroll">
      <div class="empty-state" id="emptyState">
        <div class="icon">📰</div>
        <p>Ask for the latest research and product news from the major AI labs. The digest and individual posts appear here.</p>
        <div class="hint">Try: "Latest from OpenAI, Anthropic, and Google DeepMind"</div>
      </div>
    </div>
  </div>
</main>

<script>
  let SESSION_ID = sessionStorage.getItem('ai_labs_news_session');
  if (!SESSION_ID) {
    SESSION_ID = (crypto.randomUUID
      ? crypto.randomUUID()
      : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
          const r = Math.random() * 16 | 0;
          return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        }));
    sessionStorage.setItem('ai_labs_news_session', SESSION_ID);
  }

  const messagesEl = document.getElementById('messages');
  const inputEl    = document.getElementById('userInput');
  const sendBtn    = document.getElementById('sendBtn');
  const statusDot  = document.getElementById('statusDot');
  const statusText = document.getElementById('statusText');
  const dataScroll = document.getElementById('dataScroll');
  const emptyState = document.getElementById('emptyState');

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

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function fmtDate(iso) {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      if (isNaN(d)) return '';
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    } catch (_) { return ''; }
  }

  let _lastHash = '';

  function renderItems(items) {
    if (!items || items.length === 0) return null;
    return items.map(it => {
      const tags = (it.tags && it.tags.length)
        ? ('<div class="news-tags">' +
            it.tags.map(t => '<span class="tag">' + esc(t) + '</span>').join('') + '</div>')
        : '';
      const title = it.url
        ? '<a href="' + esc(it.url) + '" target="_blank" rel="noopener">' + esc(it.title || 'Untitled') + '</a>'
        : esc(it.title || 'Untitled');
      const date = fmtDate(it.published);
      return (
        '<div class="news-card">' +
          '<div class="news-top">' +
            '<span class="lab-pill">' + esc(it.lab || '') + '</span>' +
            (date ? '<span class="news-date">' + esc(date) + '</span>' : '') +
          '</div>' +
          '<div class="news-title">' + title + '</div>' +
          (it.summary ? '<div class="news-summary">' + esc(it.summary) + '</div>' : '') +
          tags +
        '</div>'
      );
    }).join('');
  }

  function refreshPanel(data) {
    const digest = data.digest;
    const hash = JSON.stringify(digest);
    if (hash === _lastHash) return;
    _lastHash = hash;
    if (!digest || !digest.items || digest.items.length === 0) return;

    emptyState.style.display = 'none';
    let html = '';

    if (digest.headline || (digest.themes && digest.themes.length)) {
      html += '<div class="headline-block">';
      if (digest.headline) html += '<div class="hl">' + esc(digest.headline) + '</div>';
      if (digest.themes && digest.themes.length) {
        html += '<div class="themes">' +
          digest.themes.map(t => '<span class="tag theme">' + esc(t) + '</span>').join('') +
          '</div>';
      }
      html += '</div>';
    }

    html += '<div class="section-title" style="margin-top:8px">Recent posts</div>';
    html += renderItems(digest.items) || '';

    dataScroll.innerHTML = '';
    dataScroll.appendChild(emptyState);
    const wrapper = document.createElement('div');
    wrapper.style.display = 'contents';
    wrapper.innerHTML = html;
    dataScroll.appendChild(wrapper);
  }

  async function fetchSession() {
    try {
      const res = await fetch('/session/' + SESSION_ID);
      if (res.ok) { refreshPanel(await res.json()); }
    } catch (_) { /* ignore */ }
  }
  setInterval(fetchSession, 10000);

  function resetPanel() {
    // Each question is answered fresh — clear the previous digest so stale
    // results from the prior question don't linger on the right.
    _lastHash = '';
    dataScroll.innerHTML = '';
    dataScroll.appendChild(emptyState);
    emptyState.style.display = '';
  }

  async function sendMessage() {
    const question = inputEl.value.trim();
    if (!question) return;
    inputEl.value = '';
    sendBtn.disabled = true;
    setStatus(true, 'Thinking…');
    resetPanel();
    addMessage(question, 'user');
    const thinking = addMessage('Pulling the latest feeds…', 'thinking');

    try {
      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, thread_id: SESSION_ID }),
      });
      const data = await res.json();
      thinking.remove();
      if (!res.ok) {
        addMessage('Error: ' + (data.answer || res.statusText), 'error');
      } else {
        addMessage(data.answer, 'agent');
        await fetchSession();
      }
    } catch (err) {
      thinking.remove();
      addMessage('Network error: ' + err.message, 'error');
    } finally {
      sendBtn.disabled = false;
      setStatus(false, 'Ready');
      inputEl.focus();
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
    + carbon_head("AI Labs News")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
