"""
HTML UI for the Movie Recommender demo app.
Exported as _HTML — a single self-contained string served by the FastAPI root endpoint.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation.

Layout:
  Left  — Chat panel: prompt chips, message history, input field
  Right — Live data panel: collected preferences + recommendation cards
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { display: flex; flex-direction: column; }

  /* ── Main layout ── */
  main {
    display: grid;
    grid-template-columns: 420px 1fr;
    gap: 0;
    flex: 1;
    min-height: 0;
    overflow: hidden;
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
    padding: var(--cds-sp-04);
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
  }
  .chip:hover { border-color: var(--cds-interactive); background: var(--cds-interactive); color: #fff; }

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
    font-size: 0.8125rem;
  }
  .msg.user {
    background: var(--cds-interactive);
    color: #fff;
    align-self: flex-end;
    font-size: 0.875rem;
  }
  .msg.agent {
    background: var(--cds-layer-02);
    border: 1px solid var(--cds-border-subtle);
    align-self: flex-start;
  }
  .msg.error {
    background: var(--cds-support-error-bg);
    border-left: 3px solid var(--cds-support-error);
    color: var(--cds-text-primary);
    align-self: flex-start;
  }
  .msg.thinking {
    color: var(--cds-text-secondary);
    font-style: italic;
    border: 1px dashed var(--cds-border-strong);
    align-self: flex-start;
  }

  /* Input row */
  .input-row {
    display: flex;
    gap: 0;
    padding: var(--cds-sp-04);
    border-top: 1px solid var(--cds-border-subtle);
  }
  .input-row input {
    flex: 1;
    background: var(--cds-field-01);
    color: var(--cds-text-primary);
    border: none;
    border-bottom: 1px solid var(--cds-border-strong);
    padding: 0 var(--cds-sp-05);
    min-height: 3rem;
    font-family: var(--cds-font-sans);
    font-size: 0.875rem;
    letter-spacing: 0.16px;
    outline: none;
    transition: outline var(--cds-dur-fast) var(--cds-ease-productive);
  }
  .input-row input:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; }
  .input-row input::placeholder { color: var(--cds-text-placeholder); }
  .btn {
    background: var(--cds-button-primary);
    color: var(--cds-text-on-color);
    border: 1px solid transparent;
    min-height: 3rem;
    padding: 0 var(--cds-sp-06);
    font-family: var(--cds-font-sans);
    font-size: 0.875rem;
    font-weight: 400;
    letter-spacing: 0.16px;
    cursor: pointer;
    transition: background var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .btn:hover  { background: var(--cds-button-primary-hover); }
  .btn:active { background: var(--cds-button-primary-active); }
  .btn:focus-visible, .btn:focus {
    outline: 2px solid var(--cds-focus);
    outline-offset: -2px;
    box-shadow: inset 0 0 0 1px var(--cds-focus-inset);
  }
  .btn:disabled {
    background: var(--cds-layer-accent);
    color: var(--cds-text-placeholder);
    cursor: not-allowed;
    box-shadow: none;
  }

  /* ── Right panel ── */
  .data-panel {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--cds-background);
  }
  .data-panel-header {
    padding: var(--cds-sp-04) var(--cds-sp-05);
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
  .refresh-badge {
    margin-left: auto;
    font-size: 0.625rem;
    color: var(--cds-text-helper);
    text-transform: none;
    letter-spacing: 0.16px;
  }

  .data-scroll {
    flex: 1;
    overflow-y: auto;
    padding: var(--cds-sp-06);
    display: flex;
    flex-direction: column;
    gap: var(--cds-sp-06);
  }

  /* Empty state */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--cds-text-secondary);
    gap: var(--cds-sp-05);
    text-align: center;
    padding: var(--cds-sp-08);
  }
  .empty-state .icon { font-size: 56px; opacity: 0.35; }
  .empty-state p { font-size: 0.8125rem; max-width: 300px; line-height: 1.7; }
  .empty-state .hint {
    font-size: 0.75rem;
    color: var(--cds-link-primary);
    border: 1px dashed var(--cds-interactive);
    padding: var(--cds-sp-03) var(--cds-sp-05);
    border-radius: 0.9375rem;
  }

  /* Section headers inside right panel */
  .section-title {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.32px;
    color: var(--cds-text-secondary);
    margin-bottom: var(--cds-sp-04);
    display: flex;
    align-items: center;
    gap: var(--cds-sp-03);
  }
  .section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--cds-border-subtle);
  }

  /* Preferences block */
  .prefs-block {
    background: var(--cds-layer-01);
    border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-05);
  }
  .pref-row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--cds-sp-03);
    margin-bottom: var(--cds-sp-04);
  }
  .pref-row:last-child { margin-bottom: 0; }
  .pref-label {
    font-size: 0.6875rem;
    color: var(--cds-text-helper);
    text-transform: uppercase;
    letter-spacing: 0.32px;
    width: 100%;
    margin-bottom: var(--cds-sp-02);
  }
  .pref-tag {
    background: var(--cds-layer-accent);
    border: 1px solid var(--cds-border-subtle);
    border-radius: 0.9375rem;
    padding: var(--cds-sp-01) var(--cds-sp-04);
    font-size: 0.75rem;
    color: var(--cds-text-primary);
  }
  .pref-tag.genre    { background: var(--cds-support-info-bg);    border-color: transparent; color: var(--cds-link-primary); }
  .pref-tag.liked    { background: var(--cds-support-success-bg); border-color: transparent; color: var(--cds-support-success); }
  .pref-tag.disliked { background: var(--cds-support-error-bg);   border-color: transparent; color: var(--cds-support-error); }
  .pref-tag.actor    { background: var(--cds-support-info-bg);    border-color: transparent; color: var(--cds-link-primary); }
  .pref-tag.director { background: var(--cds-support-warning-bg); border-color: transparent; color: var(--cds-text-primary); }
  .pref-tag.mood     { background: var(--cds-support-info-bg);    border-color: transparent; color: var(--cds-link-primary); }

  /* Recommendation cards */
  .rec-card {
    background: var(--cds-layer-01);
    border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-05);
    transition: background var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .rec-card:hover { background: var(--cds-layer-hover); }
  .rec-card-header {
    display: flex;
    align-items: flex-start;
    gap: var(--cds-sp-04);
    margin-bottom: var(--cds-sp-03);
  }
  .rec-number {
    background: var(--cds-interactive);
    color: #fff;
    width: 26px; height: 26px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    font-weight: 600;
    flex-shrink: 0;
    font-family: var(--cds-font-mono);
  }
  .rec-title {
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--cds-text-primary);
    line-height: 1.3;
  }
  .rec-meta {
    font-size: 0.6875rem;
    color: var(--cds-text-secondary);
    margin-top: var(--cds-sp-01);
    display: flex;
    gap: var(--cds-sp-03);
    flex-wrap: wrap;
    align-items: center;
  }
  .rec-meta .badge {
    background: var(--cds-layer-accent);
    border: 1px solid var(--cds-border-subtle);
    padding: 1px 7px;
    font-size: 0.6875rem;
    font-family: var(--cds-font-mono);
  }
  .rec-reason {
    font-size: 0.8125rem;
    color: var(--cds-text-secondary);
    line-height: 1.6;
    padding-left: 42px;
  }

  /* Status dot in header */
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
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Movie&nbsp;Recommender</div>
  <div class="cds-header__actions">
    <div class="status-dot" id="statusDot"></div>
    <span class="cds-helper-01" id="statusText">Ready</span>
  </div>
</header>

<div class="app-intro">
  <div class="app-intro__blurb">
    <strong>Movie Recommender.</strong> Describe your taste — genres, films, mood — and get a personalised set of watch-next picks with a reason for each.
  </div>
  <div class="app-intro__tools">
    <span class="tools-label">Tools</span>
    <span class="tool-pill">🎬 Movie picks · LLM</span>
    <span class="tool-pill">📚 Wikipedia</span>
    <span class="tool-pill">🗂 Taste profile</span>
  </div>
</div>

<main>
  <!-- Left: Chat panel -->
  <div class="chat-panel">
    <div class="panel-title">Chat with the agent</div>

    <div class="chips">
      <div class="chip" onclick="sendChip(this)">I love Inception and sci-fi thrillers — recommend 5 for tonight</div>
      <div class="chip" onclick="sendChip(this)">Something like Interstellar but more uplifting</div>
      <div class="chip" onclick="sendChip(this)">I enjoy Christopher Nolan and Denis Villeneuve — what should I watch?</div>
      <div class="chip" onclick="sendChip(this)">Cozy feel-good movies for a rainy night, nothing scary</div>
      <div class="chip" onclick="sendChip(this)">Fast, intense action films like Mad Max</div>
      <div class="chip" onclick="sendChip(this)">I dislike horror but love Tom Hanks dramas</div>
    </div>

    <div class="messages" id="messages"></div>

    <div class="input-row">
      <input
        type="text"
        id="userInput"
        placeholder="Describe what you like — genres, films, mood — in one message…"
        onkeydown="if(event.key==='Enter') sendMessage()"
      />
      <button class="btn" id="sendBtn" onclick="sendMessage()">Send</button>
    </div>
  </div>

  <!-- Right: Preferences + Recommendations -->
  <div class="data-panel">
    <div class="data-panel-header">
      <span>Your Profile &amp; Recommendations</span>
      <span class="refresh-badge" id="refreshBadge">auto-refresh 10s</span>
    </div>

    <div class="data-scroll" id="dataScroll">
      <div class="empty-state" id="emptyState">
        <div class="icon">🍿</div>
        <p>Start chatting! Tell the agent about movies you love, genres you enjoy, or your mood tonight.</p>
        <div class="hint">Try: "I love Inception and sci-fi thrillers"</div>
      </div>
    </div>
  </div>
</main>

<script>
  // ── Session management ──────────────────────────────────────────────────
  let SESSION_ID = sessionStorage.getItem('movie_recommender_session');
  if (!SESSION_ID) {
    SESSION_ID = crypto.randomUUID ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
    sessionStorage.setItem('movie_recommender_session', SESSION_ID);
  }

  // ── DOM refs ────────────────────────────────────────────────────────────
  const messagesEl  = document.getElementById('messages');
  const inputEl     = document.getElementById('userInput');
  const sendBtn     = document.getElementById('sendBtn');
  const statusDot   = document.getElementById('statusDot');
  const statusText  = document.getElementById('statusText');
  const dataScroll  = document.getElementById('dataScroll');
  const emptyState  = document.getElementById('emptyState');

  // ── Status helpers ──────────────────────────────────────────────────────
  function setStatus(busy, label) {
    statusDot.className = 'status-dot' + (busy ? ' busy' : '');
    statusText.textContent = label;
  }

  // ── Chat helpers ────────────────────────────────────────────────────────
  function addMessage(text, cls) {
    const div = document.createElement('div');
    div.className = 'msg ' + cls;
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function escHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Preferences + recommendations panel ────────────────────────────────
  let _lastHash = '';

  function renderPreferences(prefs) {
    const rows = [];

    function renderRow(label, items, tagClass) {
      if (!items || items.length === 0) return;
      rows.push(
        '<div class="pref-row">' +
        '<div class="pref-label">' + escHtml(label) + '</div>' +
        items.map(function(v) {
          return '<span class="pref-tag ' + tagClass + '">' + escHtml(v) + '</span>';
        }).join('') +
        '</div>'
      );
    }

    renderRow('Genres', prefs.genres, 'genre');
    renderRow('Movies I love', prefs.liked_movies, 'liked');
    renderRow('Movies I dislike', prefs.disliked_movies, 'disliked');
    renderRow('Favourite actors', prefs.favorite_actors, 'actor');
    renderRow('Favourite directors', prefs.favorite_directors, 'director');
    renderRow('Mood / vibe', prefs.moods, 'mood');

    if (rows.length === 0) return null;
    return '<div class="prefs-block">' + rows.join('') + '</div>';
  }

  function renderRecommendations(recs) {
    if (!recs || recs.length === 0) return null;
    const cards = recs.map(function(r, i) {
      const meta = [];
      if (r.year)   meta.push('<span class="badge">' + escHtml(String(r.year)) + '</span>');
      if (r.genre)  meta.push('<span class="badge">' + escHtml(r.genre) + '</span>');
      if (r.rating) meta.push('<span>' + escHtml(r.rating) + '</span>');
      return (
        '<div class="rec-card">' +
          '<div class="rec-card-header">' +
            '<div class="rec-number">' + (i + 1) + '</div>' +
            '<div>' +
              '<div class="rec-title">' + escHtml(r.title || 'Unknown') + '</div>' +
              (meta.length ? '<div class="rec-meta">' + meta.join('') + '</div>' : '') +
            '</div>' +
          '</div>' +
          (r.reason ? '<div class="rec-reason">' + escHtml(r.reason) + '</div>' : '') +
        '</div>'
      );
    }).join('');
    return cards;
  }

  function refreshPanel(data) {
    const hash = JSON.stringify(data);
    if (hash === _lastHash) return;
    _lastHash = hash;

    const hasPrefs = (
      (data.genres && data.genres.length) ||
      (data.liked_movies && data.liked_movies.length) ||
      (data.disliked_movies && data.disliked_movies.length) ||
      (data.favorite_actors && data.favorite_actors.length) ||
      (data.favorite_directors && data.favorite_directors.length) ||
      (data.moods && data.moods.length)
    );
    const hasRecs = data.recommendations && data.recommendations.length > 0;

    if (!hasPrefs && !hasRecs) return;

    emptyState.style.display = 'none';

    let html = '';
    if (hasPrefs) {
      html += '<div class="section-title">Your Preferences</div>';
      html += renderPreferences(data) || '';
    }
    if (hasRecs) {
      html += '<div class="section-title" style="margin-top:8px">Recommendations</div>';
      html += renderRecommendations(data.recommendations) || '';
    }

    // Replace content but keep empty state element
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
      if (res.ok) {
        const data = await res.json();
        refreshPanel(data);
      }
    } catch (_) { /* silently ignore network blips */ }
  }

  // Auto-refresh every 10 seconds
  setInterval(fetchSession, 10000);

  // ── Send message ────────────────────────────────────────────────────────
  async function sendMessage() {
    const question = inputEl.value.trim();
    if (!question) return;

    inputEl.value = '';
    sendBtn.disabled = true;
    setStatus(true, 'Thinking…');

    addMessage(question, 'user');
    const thinking = addMessage('Checking your taste and crafting suggestions…', 'thinking');

    try {
      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question, thread_id: SESSION_ID }),
      });
      const data = await res.json();
      thinking.remove();

      if (!res.ok) {
        addMessage('Error: ' + (data.answer || res.statusText), 'error');
      } else {
        addMessage(data.answer, 'agent');
        // Immediately refresh the side panel after each response
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
    + carbon_head("Movie Recommender")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
