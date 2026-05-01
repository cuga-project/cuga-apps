"""
HTML UI for the Movie Recommender demo app.
Exported as _HTML — a single self-contained string served by the FastAPI root endpoint.

Layout:
  Left  — Chat panel: prompt chips, message history, input field
  Right — Live data panel: collected preferences + recommendation cards
"""

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Movie Recommender</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:       #0f1117;
    --card:     #1a1a2e;
    --border:   #2d2d4a;
    --accent:   #e040fb;
    --accent2:  #00d4aa;
    --accent3:  #ff9800;
    --text:     #e2e8f0;
    --muted:    #8892a4;
    --danger:   #ff4d6d;
    --success:  #00c896;
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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
    gap: 14px;
  }
  .header-icon { font-size: 22px; }
  header h1 { font-size: 18px; font-weight: 700; letter-spacing: 0.4px; }
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
    padding: 12px 18px;
    font-size: 11px;
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
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
  }
  .chip {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 4px 11px;
    font-size: 12px;
    color: var(--muted);
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .chip:hover { border-color: var(--accent); color: var(--text); }

  /* Messages */
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    scroll-behavior: smooth;
  }
  .messages::-webkit-scrollbar { width: 4px; }
  .messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  .msg {
    max-width: 100%;
    padding: 10px 14px;
    border-radius: 10px;
    line-height: 1.65;
    white-space: pre-wrap;
    word-break: break-word;
    font-size: 13px;
  }
  .msg.user {
    background: var(--accent);
    color: #fff;
    align-self: flex-end;
    border-bottom-right-radius: 3px;
    font-size: 14px;
  }
  .msg.agent {
    background: var(--bg);
    border: 1px solid var(--border);
    align-self: flex-start;
    border-bottom-left-radius: 3px;
  }
  .msg.error {
    background: rgba(255,77,109,0.12);
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
    padding: 12px 14px;
    border-top: 1px solid var(--border);
  }
  .input-row input {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 9px 14px;
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
    padding: 9px 18px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .btn:hover  { opacity: 0.85; }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ── Right panel ── */
  .data-panel {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .data-panel-header {
    padding: 12px 20px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .refresh-badge {
    margin-left: auto;
    font-size: 10px;
    color: var(--muted);
    opacity: 0.6;
  }

  .data-scroll {
    flex: 1;
    overflow-y: auto;
    padding: 18px;
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  .data-scroll::-webkit-scrollbar { width: 4px; }
  .data-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  /* Empty state */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--muted);
    gap: 14px;
    text-align: center;
    padding: 40px;
  }
  .empty-state .icon { font-size: 56px; opacity: 0.25; }
  .empty-state p { font-size: 13px; max-width: 300px; line-height: 1.7; }
  .empty-state .hint {
    font-size: 12px;
    color: var(--accent);
    border: 1px dashed var(--accent);
    padding: 6px 16px;
    border-radius: 20px;
    opacity: 0.7;
  }

  /* Section headers inside right panel */
  .section-title {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--muted);
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  /* Preferences block */
  .prefs-block {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
  }
  .pref-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 10px;
  }
  .pref-row:last-child { margin-bottom: 0; }
  .pref-label {
    font-size: 11px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.8px;
    width: 100%;
    margin-bottom: 4px;
  }
  .pref-tag {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 3px 11px;
    font-size: 12px;
    color: var(--text);
  }
  .pref-tag.genre   { border-color: #6c63ff; color: #a89cf7; }
  .pref-tag.liked   { border-color: var(--success); color: var(--success); }
  .pref-tag.disliked{ border-color: var(--danger); color: var(--danger); }
  .pref-tag.actor   { border-color: var(--accent2); color: var(--accent2); }
  .pref-tag.director{ border-color: var(--accent3); color: var(--accent3); }
  .pref-tag.mood    { border-color: var(--accent); color: var(--accent); }

  /* Recommendation cards */
  .rec-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    transition: border-color 0.2s;
  }
  .rec-card:hover { border-color: var(--accent); }
  .rec-card-header {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 8px;
  }
  .rec-number {
    background: var(--accent);
    color: #fff;
    width: 26px; height: 26px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    flex-shrink: 0;
  }
  .rec-title {
    font-size: 15px;
    font-weight: 700;
    color: var(--text);
    line-height: 1.3;
  }
  .rec-meta {
    font-size: 11px;
    color: var(--muted);
    margin-top: 2px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }
  .rec-meta .badge {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 7px;
    font-size: 11px;
  }
  .rec-reason {
    font-size: 13px;
    color: #c0c8d8;
    line-height: 1.6;
    padding-left: 38px;
  }
</style>
</head>
<body>

<header>
  <div class="header-icon">🎬</div>
  <h1>Movie <span>Recommender</span></h1>
  <div class="status-badge">
    <div class="status-dot" id="statusDot"></div>
    <span id="statusText">Ready</span>
  </div>
</header>

<main>
  <!-- Left: Chat panel -->
  <div class="chat-panel">
    <div class="panel-title">Chat with the agent</div>

    <div class="chips">
      <div class="chip" onclick="sendChip(this)">I love thriller movies</div>
      <div class="chip" onclick="sendChip(this)">My favourite film is Inception</div>
      <div class="chip" onclick="sendChip(this)">I enjoy Christopher Nolan's work</div>
      <div class="chip" onclick="sendChip(this)">Recommend me something like Interstellar</div>
      <div class="chip" onclick="sendChip(this)">I'm in the mood for something uplifting</div>
      <div class="chip" onclick="sendChip(this)">I love sci-fi and action films</div>
      <div class="chip" onclick="sendChip(this)">Suggest 5 movies for tonight</div>
      <div class="chip" onclick="sendChip(this)">I dislike horror movies</div>
      <div class="chip" onclick="sendChip(this)">My favourite actor is Tom Hanks</div>
    </div>

    <div class="messages" id="messages"></div>

    <div class="input-row">
      <input
        type="text"
        id="userInput"
        placeholder="Tell me what you enjoy watching…"
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
</body>
</html>
"""
