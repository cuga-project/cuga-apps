"""
HTML UI for the Meetup Finder demo app.
Exported as _HTML — a single self-contained string served by FastAPI's "/" route.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation.

Layout:
  Left  — Chat panel: prompt chips, message log, input field
  Right — Live data panel: search context + ranked event cards
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

  .info-block {
    background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-05);
  }
  .info-row {
    display: flex; flex-wrap: wrap; gap: var(--cds-sp-03); margin-bottom: var(--cds-sp-04);
  }
  .info-row:last-child { margin-bottom: 0; }
  .info-label {
    font-size: 0.6875rem; color: var(--cds-text-helper);
    text-transform: uppercase; letter-spacing: 0.32px;
    width: 100%; margin-bottom: var(--cds-sp-02);
  }
  .tag {
    display: inline-flex; align-items: center;
    background: var(--cds-layer-accent); border: 1px solid transparent;
    border-radius: 0.9375rem; padding: var(--cds-sp-02) var(--cds-sp-04);
    font-size: 0.75rem; color: var(--cds-text-primary); line-height: 1;
  }
  .tag.topic { background: var(--cds-support-info-bg);    color: var(--cds-link-primary); }
  .tag.loc   { background: var(--cds-support-success-bg); color: var(--cds-support-success); }
  .tag.when  { background: var(--cds-layer-accent);       color: var(--cds-text-primary); }

  /* ── Event cards ─────────────────────────────────────────────────────── */
  .ev-card {
    background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-05);
    transition: border-color var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .ev-card:hover { border-color: var(--cds-border-strong); }
  .ev-head {
    display: flex; align-items: flex-start; gap: var(--cds-sp-04); margin-bottom: var(--cds-sp-04);
  }
  .ev-date {
    background: var(--cds-interactive); color: #fff;
    border-radius: 0; min-width: 3rem; padding: var(--cds-sp-02);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    flex-shrink: 0; line-height: 1.1;
  }
  .ev-date .mon { font-size: 0.625rem; text-transform: uppercase; letter-spacing: 0.5px; }
  .ev-date .day { font-size: 1.125rem; font-weight: 600; font-family: var(--cds-font-mono); }
  .ev-title { font-size: 0.9375rem; font-weight: 600; line-height: 1.3; }
  .ev-title a { color: var(--cds-link-primary); text-decoration: none; }
  .ev-title a:hover { text-decoration: underline; }
  .ev-meta {
    font-size: 0.6875rem; color: var(--cds-text-secondary); margin-top: var(--cds-sp-02);
    display: flex; gap: var(--cds-sp-03); flex-wrap: wrap; align-items: center;
  }
  .ev-meta .badge {
    background: var(--cds-layer-accent); border: 1px solid var(--cds-border-subtle);
    padding: 1px var(--cds-sp-03); font-size: 0.6875rem; color: var(--cds-text-secondary);
  }
  .ev-meta .badge.src { color: var(--cds-link-primary); border-color: var(--cds-link-primary); text-transform: capitalize; }
  .ev-detail { padding-left: 3.875rem; font-size: 0.75rem; color: var(--cds-text-secondary); line-height: 1.5; }
  .ev-detail .row { margin-bottom: 2px; }
  .ev-why {
    padding-left: 3.875rem; margin-top: var(--cds-sp-03);
    font-size: 0.75rem; color: var(--cds-link-primary); font-style: italic;
  }

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
    <span class="cds-header__prefix">IBM</span>&nbsp;Meetup&nbsp;Finder
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
    <strong>Meetup Finder.</strong> Drives a real headless browser over Meetup, Luma, and Eventbrite to find upcoming tech/AI events near you, then ranks them with date, venue, host, and an RSVP link.
  </div>
  <div class="app-intro__tools">
    <span class="tools-label">Tools</span>
    <span class="tool-pill">🌐 Browser · Playwright</span>
    <span class="tool-pill">🤝 Meetup.com</span>
    <span class="tool-pill">📅 Luma</span>
    <span class="tool-pill">🎟 Eventbrite</span>
    <span class="tool-pill">🧬 JSON-LD extract</span>
  </div>
</div>

<main>
  <div class="chat-panel">
    <div class="panel-title">Chat with the agent</div>

    <div class="chips">
      <div class="chip" onclick="sendChip(this)">AI meetups in San Francisco this week</div>
      <div class="chip" onclick="sendChip(this)">LLM and agent events near New York</div>
      <div class="chip" onclick="sendChip(this)">Data engineering meetups in Austin this month</div>
      <div class="chip" onclick="sendChip(this)">Startup / founder events in London</div>
      <div class="chip" onclick="sendChip(this)">ML research talks in Boston this weekend</div>
      <div class="chip" onclick="sendChip(this)">Developer conferences in Seattle</div>
    </div>

    <div class="messages" id="messages"></div>

    <div class="input-row">
      <input type="text" id="userInput"
        placeholder="What kind of event, and where?"
        onkeydown="if(event.key==='Enter') sendMessage()" />
      <button class="cds-btn btn" id="sendBtn" onclick="sendMessage()">Send</button>
    </div>
  </div>

  <div class="data-panel">
    <div class="data-panel-header">
      <span>Upcoming Events</span>
      <span class="refresh-badge" id="refreshBadge">auto-refresh 10s</span>
    </div>
    <div class="data-scroll" id="dataScroll">
      <div class="empty-state" id="emptyState">
        <div class="icon">📅</div>
        <p>Tell the agent your interests and a city. It drives a real browser over Meetup, Luma, and Eventbrite and ranks the upcoming events here.</p>
        <div class="hint">Try: "AI agent meetups in San Francisco this week"</div>
      </div>
    </div>
  </div>
</main>

<script>
  let SESSION_ID = sessionStorage.getItem('meetup_finder_session');
  if (!SESSION_ID) {
    SESSION_ID = (crypto.randomUUID
      ? crypto.randomUUID()
      : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
          const r = Math.random() * 16 | 0;
          return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        }));
    sessionStorage.setItem('meetup_finder_session', SESSION_ID);
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

  function parseDate(s) {
    if (!s) return null;
    const d = new Date(s);
    return isNaN(d) ? null : d;
  }

  let _lastHash = '';

  function renderContext(data) {
    const chips = [];
    if (data.interests) chips.push('<span class="tag topic">' + esc(data.interests) + '</span>');
    if (data.location)  chips.push('<span class="tag loc">📍 ' + esc(data.location) + '</span>');
    if (data.when)      chips.push('<span class="tag when">🗓 ' + esc(data.when) + '</span>');
    if (chips.length === 0) return null;
    return '<div class="info-block"><div class="info-row">' +
           '<div class="info-label">Searching for</div>' + chips.join('') + '</div></div>';
  }

  function renderEvents(events) {
    if (!events || events.length === 0) return null;
    return events.map(ev => {
      const d = parseDate(ev.start);
      const mon = d ? d.toLocaleDateString(undefined, { month: 'short' }) : '–';
      const day = d ? d.getDate() : '?';
      const meta = [];
      if (ev.source) meta.push('<span class="badge src">' + esc(ev.source) + '</span>');
      if (ev.attendees != null && ev.attendees !== '') meta.push('<span class="badge">' + esc(ev.attendees) + ' going</span>');
      if (d) meta.push('<span class="badge">' + esc(d.toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })) + '</span>');

      const title = ev.url
        ? '<a href="' + esc(ev.url) + '" target="_blank" rel="noopener">' + esc(ev.title || 'Event') + '</a>'
        : esc(ev.title || 'Event');

      const detail = [];
      if (ev.venue) detail.push('<div class="row">📍 ' + esc(ev.venue) + '</div>');
      if (ev.host)  detail.push('<div class="row">👥 ' + esc(ev.host) + '</div>');

      return (
        '<div class="ev-card">' +
          '<div class="ev-head">' +
            '<div class="ev-date"><span class="mon">' + esc(mon) + '</span><span class="day">' + esc(day) + '</span></div>' +
            '<div>' +
              '<div class="ev-title">' + title + '</div>' +
              (meta.length ? '<div class="ev-meta">' + meta.join('') + '</div>' : '') +
            '</div>' +
          '</div>' +
          (detail.length ? '<div class="ev-detail">' + detail.join('') + '</div>' : '') +
          (ev.why ? '<div class="ev-why">✨ ' + esc(ev.why) + '</div>' : '') +
        '</div>'
      );
    }).join('');
  }

  function refreshPanel(data) {
    const hash = JSON.stringify({ e: data.events, i: data.interests, l: data.location, w: data.when });
    if (hash === _lastHash) return;
    _lastHash = hash;

    const hasEvents = data.events && data.events.length > 0;
    const ctx = renderContext(data);
    if (!hasEvents && !ctx) return;

    emptyState.style.display = 'none';
    let html = '';
    if (ctx) { html += '<div class="section-title">Search</div>' + ctx; }
    if (hasEvents) {
      html += '<div class="section-title" style="margin-top:8px">Ranked events</div>';
      html += renderEvents(data.events) || '';
    }

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

  async function sendMessage() {
    const question = inputEl.value.trim();
    if (!question) return;
    inputEl.value = '';
    sendBtn.disabled = true;
    setStatus(true, 'Browsing…');
    addMessage(question, 'user');
    const thinking = addMessage('Opening Meetup, Luma & Eventbrite…', 'thinking');

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
    + carbon_head("Meetup Finder")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
