"""
HTML UI for the City Beat demo app.
Exported as _HTML — a single self-contained string served by FastAPI's "/" route.

Layout:
  Left  — Chat panel: prompt chips, message log, input field
  Right — Live data panel: structured city briefing card built from MCP tool calls
"""

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>City Beat</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:       #0f1117;
    --card:     #1a1a2e;
    --border:   #2d2d4a;
    --accent:   #38bdf8;   /* sky blue */
    --accent2:  #a78bfa;   /* violet */
    --accent3:  #facc15;   /* sun yellow */
    --text:     #e2e8f0;
    --muted:    #8892a4;
    --danger:   #f87171;
    --success:  #4ade80;
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

  header {
    position: sticky; top: 0; z-index: 100;
    background: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 12px 24px;
    display: flex; align-items: center; gap: 14px;
  }
  .header-icon { font-size: 22px; }
  header h1 { font-size: 18px; font-weight: 700; letter-spacing: 0.4px; }
  header h1 span { color: var(--accent); }
  .status-badge {
    display: flex; align-items: center; gap: 6px;
    font-size: 12px; color: var(--muted); margin-left: auto;
  }
  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--success); animation: pulse 2s infinite;
  }
  .status-dot.busy { background: var(--accent); animation: none; }
  @keyframes pulse {
    0%, 100% { opacity: 1; } 50% { opacity: 0.4; }
  }

  main {
    display: grid;
    grid-template-columns: 420px 1fr;
    gap: 0; flex: 1; overflow: hidden;
    height: calc(100vh - 57px);
  }

  /* Chat panel */
  .chat-panel {
    background: var(--card); border-right: 1px solid var(--border);
    display: flex; flex-direction: column; overflow: hidden;
  }
  .panel-title {
    padding: 12px 18px; font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 1px;
    color: var(--muted); border-bottom: 1px solid var(--border);
  }
  .chips {
    display: flex; flex-wrap: wrap; gap: 6px;
    padding: 10px 14px; border-bottom: 1px solid var(--border);
  }
  .chip {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 20px; padding: 4px 11px;
    font-size: 12px; color: var(--muted); cursor: pointer;
    transition: all 0.15s; white-space: nowrap;
  }
  .chip:hover { border-color: var(--accent); color: var(--text); }

  .messages {
    flex: 1; overflow-y: auto; padding: 14px;
    display: flex; flex-direction: column; gap: 10px;
    scroll-behavior: smooth;
  }
  .messages::-webkit-scrollbar { width: 4px; }
  .messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  .msg {
    max-width: 100%; padding: 10px 14px; border-radius: 10px;
    line-height: 1.65; white-space: pre-wrap;
    word-break: break-word; font-size: 13px;
  }
  .msg.user {
    background: var(--accent); color: #fff;
    align-self: flex-end; border-bottom-right-radius: 3px;
    font-size: 14px;
  }
  .msg.agent {
    background: var(--bg); border: 1px solid var(--border);
    align-self: flex-start; border-bottom-left-radius: 3px;
  }
  .msg.error {
    background: rgba(248,113,113,0.12); border: 1px solid var(--danger);
    color: var(--danger); align-self: flex-start;
  }
  .msg.thinking {
    color: var(--muted); font-style: italic;
    border: 1px dashed var(--border); align-self: flex-start;
  }

  .input-row {
    display: flex; gap: 8px;
    padding: 12px 14px; border-top: 1px solid var(--border);
  }
  .input-row input {
    flex: 1; background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 9px 14px; color: var(--text);
    font-size: 14px; outline: none; transition: border-color 0.15s;
  }
  .input-row input:focus { border-color: var(--accent); }
  .input-row input::placeholder { color: var(--muted); }
  .btn {
    background: var(--accent); color: #06202b; border: none;
    border-radius: 8px; padding: 9px 18px;
    font-size: 14px; font-weight: 700;
    cursor: pointer; transition: opacity 0.15s;
  }
  .btn:hover  { opacity: 0.85; }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }

  /* Right data panel */
  .data-panel { display: flex; flex-direction: column; overflow: hidden; }
  .data-panel-header {
    padding: 12px 20px; font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 1px;
    color: var(--muted); border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 10px;
  }
  .refresh-badge { margin-left: auto; font-size: 10px; color: var(--muted); opacity: 0.6; }
  .data-scroll {
    flex: 1; overflow-y: auto; padding: 18px;
    display: flex; flex-direction: column; gap: 18px;
  }
  .data-scroll::-webkit-scrollbar { width: 4px; }
  .data-scroll::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  .empty-state {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 100%; color: var(--muted); gap: 14px;
    text-align: center; padding: 40px;
  }
  .empty-state .icon { font-size: 56px; opacity: 0.3; }
  .empty-state p { font-size: 13px; max-width: 320px; line-height: 1.7; }
  .empty-state .hint {
    font-size: 12px; color: var(--accent);
    border: 1px dashed var(--accent);
    padding: 6px 16px; border-radius: 20px; opacity: 0.75;
  }

  .section-title {
    font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 1px;
    color: var(--muted); margin-bottom: 10px;
    display: flex; align-items: center; gap: 8px;
  }
  .section-title::after {
    content: ''; flex: 1; height: 1px; background: var(--border);
  }

  /* City hero card */
  .city-card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 14px; padding: 18px 20px;
  }
  .city-card .city {
    font-size: 22px; font-weight: 700; line-height: 1.2; margin-bottom: 4px;
  }
  .city-card .city .accent { color: var(--accent); }
  .city-card .place {
    font-size: 12px; color: var(--muted); margin-bottom: 10px;
  }
  .city-card .tagline {
    font-size: 14px; color: #c0c8d8; line-height: 1.55;
    border-left: 3px solid var(--accent); padding-left: 10px;
    margin-top: 10px; font-style: italic;
  }
  .city-card .meta-row {
    display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px;
  }
  .pill {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 20px; padding: 3px 10px; font-size: 11px;
    color: var(--text);
  }
  .pill.lat { color: var(--accent2); border-color: var(--accent2); }

  /* Generic mini-block */
  .block {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 14px 16px;
  }
  .block h3 {
    font-size: 12px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.8px;
    color: var(--muted); margin-bottom: 8px;
  }
  .block .body { font-size: 13px; line-height: 1.6; color: #d6deea; }
  .block .body p { margin-bottom: 6px; }
  .block .body p:last-child { margin-bottom: 0; }
  .block .body a { color: var(--accent); text-decoration: none; }
  .block .body a:hover { text-decoration: underline; }

  /* News list */
  .news ol { padding-left: 18px; }
  .news li { margin-bottom: 8px; line-height: 1.5; }
  .news .src { color: var(--muted); font-size: 11px; display: block; margin-top: 2px; }

  /* Attractions */
  .attractions ul { list-style: none; padding: 0; }
  .attractions li {
    border-top: 1px solid var(--border);
    padding: 8px 0; display: flex; gap: 10px; align-items: center;
  }
  .attractions li:first-child { border-top: 0; }
  .attractions .name { flex: 1; font-weight: 600; color: var(--text); }
  .attractions .cat { font-size: 11px; color: var(--accent2); }
  .attractions .dist { font-size: 11px; color: var(--muted); }

  /* Crypto spotlight */
  .crypto {
    display: flex; align-items: center; gap: 14px;
  }
  .crypto .ticker {
    font-size: 18px; font-weight: 700; color: var(--accent3);
    text-transform: uppercase;
  }
  .crypto .price { font-size: 16px; font-weight: 700; }
  .crypto .change { font-size: 12px; padding: 2px 8px; border-radius: 12px; }
  .crypto .change.up   { background: rgba(74,222,128,0.16); color: var(--success); }
  .crypto .change.down { background: rgba(248,113,113,0.16); color: var(--danger);  }

  /* Watchlist */
  .watchlist {
    display: flex; flex-wrap: wrap; gap: 6px;
  }
  .watchlist .city-pill {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 20px; padding: 4px 12px; font-size: 12px;
    color: var(--accent2); cursor: pointer;
  }
  .watchlist .city-pill:hover { border-color: var(--accent2); }
</style>
</head>
<body>

<header>
  <div class="header-icon">🏙️</div>
  <h1>City <span>Beat</span></h1>
  <div class="status-badge">
    <div class="status-dot" id="statusDot"></div>
    <span id="statusText">Ready</span>
  </div>
</header>

<main>
  <div class="chat-panel">
    <div class="panel-title">Chat with the agent</div>

    <div class="chips">
      <div class="chip" onclick="sendChip(this)">Brief me on Lisbon</div>
      <div class="chip" onclick="sendChip(this)">What's happening in Tokyo today?</div>
      <div class="chip" onclick="sendChip(this)">Give me the beat on Mexico City</div>
      <div class="chip" onclick="sendChip(this)">Focus on tech startups</div>
      <div class="chip" onclick="sendChip(this)">Add live music to the focus</div>
      <div class="chip" onclick="sendChip(this)">Spotlight ETH on the briefing</div>
      <div class="chip" onclick="sendChip(this)">What can I do in Berlin tonight?</div>
      <div class="chip" onclick="sendChip(this)">Brief me on Bangalore — focus on weather and transit</div>
      <div class="chip" onclick="sendChip(this)">Clear the focus and give me a fresh take on Paris</div>
    </div>

    <div class="messages" id="messages"></div>

    <div class="input-row">
      <input type="text" id="userInput"
        placeholder="Ask for a city briefing…"
        onkeydown="if(event.key==='Enter') sendMessage()" />
      <button class="btn" id="sendBtn" onclick="sendMessage()">Send</button>
    </div>
  </div>

  <div class="data-panel">
    <div class="data-panel-header">
      <span>Briefing</span>
      <span class="refresh-badge" id="refreshBadge">auto-refresh 10s</span>
    </div>
    <div class="data-scroll" id="dataScroll">
      <div class="empty-state" id="emptyState">
        <div class="icon">🌐</div>
        <p>Name a city, optionally with a focus topic. The agent will pull weather, news, background, and (if you ask) crypto into one card.</p>
        <div class="hint">Try: "Brief me on Lisbon — focus on tech"</div>
      </div>
    </div>
  </div>
</main>

<script>
  let SESSION_ID = sessionStorage.getItem('city_beat_session');
  if (!SESSION_ID) {
    SESSION_ID = (crypto.randomUUID
      ? crypto.randomUUID()
      : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
          const r = Math.random() * 16 | 0;
          return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        }));
    sessionStorage.setItem('city_beat_session', SESSION_ID);
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

  let _lastHash = '';

  function renderHero(b, focusTopics, watchlist) {
    const lat = (b.lat != null && b.lon != null)
      ? '<span class="pill lat">' + esc(b.lat.toFixed ? b.lat.toFixed(3) : b.lat) +
        ', ' + esc(b.lon.toFixed ? b.lon.toFixed(3) : b.lon) + '</span>'
      : '';
    const focusPills = (focusTopics || []).map(f =>
      '<span class="pill">focus: ' + esc(f) + '</span>'
    ).join('');
    return (
      '<div class="city-card">' +
        '<div class="city"><span class="accent">' + esc(b.city || '?') + '</span></div>' +
        '<div class="place">' + esc(b.display_name || '') + '</div>' +
        (b.tagline ? '<div class="tagline">' + esc(b.tagline) + '</div>' : '') +
        '<div class="meta-row">' + lat + focusPills + '</div>' +
      '</div>'
    );
  }

  function renderWeather(w) {
    if (!w) return '';
    return (
      '<div class="block weather">' +
        '<h3>Weather</h3>' +
        '<div class="body">' +
          (w.current ? '<p><strong>' + esc(w.current) + '</strong></p>' : '') +
          (w.outlook ? '<p>' + esc(w.outlook) + '</p>' : '') +
        '</div>' +
      '</div>'
    );
  }

  function renderNews(items) {
    if (!items || items.length === 0) return '';
    const lis = items.map(it => {
      const link = it.url ? '<a href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
        esc(it.title || it.url) + '</a>' : esc(it.title || '');
      const snip = it.snippet ? ' — ' + esc(it.snippet) : '';
      const host = (function() {
        try { return new URL(it.url).hostname; } catch (_) { return ''; }
      })();
      return '<li>' + link + snip + (host ? '<span class="src">' + esc(host) + '</span>' : '') + '</li>';
    }).join('');
    return '<div class="block news"><h3>Today\'s news</h3><div class="body"><ol>' + lis + '</ol></div></div>';
  }

  function renderWiki(w) {
    if (!w || !w.summary) return '';
    return (
      '<div class="block wiki">' +
        '<h3>Background</h3>' +
        '<div class="body">' +
          '<p>' + esc(w.summary) + '</p>' +
          (w.url ? '<p><a href="' + esc(w.url) + '" target="_blank" rel="noopener">More on Wikipedia →</a></p>' : '') +
        '</div>' +
      '</div>'
    );
  }

  function renderAttractions(items) {
    if (!items || items.length === 0) return '';
    const lis = items.map(a => {
      const dist = (a.distance_m != null) ? (Math.round(a.distance_m) + ' m away') : '';
      return '<li><span class="name">' + esc(a.name || '?') + '</span>' +
             (a.category ? '<span class="cat">' + esc(a.category) + '</span>' : '') +
             (dist ? '<span class="dist">' + esc(dist) + '</span>' : '') +
             '</li>';
    }).join('');
    return '<div class="block attractions"><h3>Nearby attractions</h3><div class="body"><ul>' + lis + '</ul></div></div>';
  }

  function renderCrypto(c) {
    if (!c) return '';
    const change = (c.change_24h_pct != null)
      ? '<span class="change ' + (c.change_24h_pct >= 0 ? 'up' : 'down') + '">' +
        (c.change_24h_pct >= 0 ? '+' : '') + Number(c.change_24h_pct).toFixed(2) + '% 24h</span>'
      : '';
    const price = (c.price_usd != null) ? '<span class="price">$' + Number(c.price_usd).toLocaleString() + '</span>' : '';
    return (
      '<div class="block">' +
        '<h3>Crypto spotlight</h3>' +
        '<div class="body crypto">' +
          '<span class="ticker">' + esc(c.ticker || '?') + '</span>' +
          price + change +
        '</div>' +
      '</div>'
    );
  }

  function renderWatchlist(list) {
    if (!list || list.length <= 1) return '';
    const pills = list.map(c => '<span class="city-pill" onclick="askCity(\'' + esc(c).replace(/\\/g,'\\\\').replace(/\'/g,'\\\'') + '\')">' + esc(c) + '</span>').join('');
    return (
      '<div class="block">' +
        '<h3>Watchlist</h3>' +
        '<div class="body"><div class="watchlist">' + pills + '</div></div>' +
      '</div>'
    );
  }

  function refreshPanel(state) {
    const hash = JSON.stringify(state);
    if (hash === _lastHash) return;
    _lastHash = hash;

    const b = state.briefing;
    if (!b) return;

    emptyState.style.display = 'none';

    let html = '';
    html += renderHero(b, state.focus_topics, state.watchlist);
    html += renderWeather(b.weather);
    html += renderNews(b.news);
    html += renderAttractions(b.attractions);
    html += renderWiki(b.wiki);
    html += renderCrypto(b.crypto);
    html += renderWatchlist(state.watchlist);

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
    } catch (_) { /* ignore */ }
  }
  setInterval(fetchSession, 10000);

  async function sendMessage() {
    const question = inputEl.value.trim();
    if (!question) return;
    inputEl.value = '';
    sendBtn.disabled = true;
    setStatus(true, 'Building briefing…');
    addMessage(question, 'user');
    const thinking = addMessage('Pulling weather, news, background…', 'thinking');

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

  function askCity(city) {
    inputEl.value = 'Brief me on ' + city;
    sendMessage();
  }
</script>
</body>
</html>
"""
