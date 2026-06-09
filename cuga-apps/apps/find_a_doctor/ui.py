"""
HTML UI for the Find a Doctor demo app.
Exported as _HTML — a single self-contained string served by FastAPI's "/" route.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation.

Layout:
  Left  — Chat panel: prompt chips, message log, input field
  Right — Live data panel: search context + ranked doctor cards (pros/cons)
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
    main { grid-template-columns: 1fr; }
  }

  /* ── App intro band: one-line blurb + the tools this app uses ─────────── */
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
  .tag.loc  { background: var(--cds-support-info-bg);    color: var(--cds-link-primary); }
  .tag.spec { background: var(--cds-support-success-bg); color: var(--cds-support-success); }
  .tag.pref { background: var(--cds-layer-accent);       color: var(--cds-text-primary); }

  /* ── Doctor cards ────────────────────────────────────────────────────── */
  .doc-card {
    background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-05);
    transition: border-color var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .doc-card:hover { border-color: var(--cds-border-strong); }
  .doc-head {
    display: flex; align-items: flex-start; gap: var(--cds-sp-04); margin-bottom: var(--cds-sp-04);
  }
  .doc-num {
    background: var(--cds-interactive); color: #fff;
    width: 1.625rem; height: 1.625rem; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.75rem; font-weight: 600; flex-shrink: 0;
    font-family: var(--cds-font-mono);
  }
  .doc-name { font-size: 0.9375rem; font-weight: 600; line-height: 1.3; color: var(--cds-text-primary); }
  .doc-meta {
    font-size: 0.6875rem; color: var(--cds-text-secondary); margin-top: var(--cds-sp-02);
    display: flex; gap: var(--cds-sp-03); flex-wrap: wrap; align-items: center;
  }
  .doc-meta .badge {
    background: var(--cds-layer-accent); border: 1px solid var(--cds-border-subtle);
    padding: 1px var(--cds-sp-03); font-size: 0.6875rem; color: var(--cds-text-secondary);
  }
  .doc-meta .badge.spec { color: var(--cds-support-success); border-color: var(--cds-support-success); }

  .doc-rating {
    padding-left: 2.375rem; font-size: 0.8125rem; color: var(--cds-text-secondary);
    line-height: 1.6; margin-bottom: var(--cds-sp-03);
  }
  .doc-exp {
    padding-left: 2.375rem; font-size: 0.75rem; color: var(--cds-link-primary);
    font-style: italic; margin-bottom: var(--cds-sp-03);
  }
  .doc-contact {
    padding-left: 2.375rem; font-size: 0.6875rem; color: var(--cds-text-helper);
    display: flex; flex-direction: column; gap: 2px; margin-bottom: var(--cds-sp-03);
  }
  .doc-contact a { color: var(--cds-link-primary); text-decoration: none; }
  .doc-contact a:hover { text-decoration: underline; }

  .pc-grid { padding-left: 2.375rem; display: grid; grid-template-columns: 1fr; gap: var(--cds-sp-03); }
  .pc-col .label { font-size: 0.6875rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.32px; }
  .pc-col.pros .label { color: var(--cds-support-success); }
  .pc-col.cons .label { color: var(--cds-support-error); }
  .pc-col ul { margin: var(--cds-sp-02) 0 0 0; padding-left: var(--cds-sp-05); }
  .pc-col li { font-size: 0.75rem; color: var(--cds-text-secondary); margin-bottom: var(--cds-sp-01); line-height: 1.5; }

  .doc-sources { padding-left: 2.375rem; margin-top: var(--cds-sp-04); font-size: 0.75rem; }
  .doc-sources summary { cursor: pointer; color: var(--cds-link-primary); font-weight: 600; }
  .doc-sources ul { margin-top: var(--cds-sp-03); padding-left: var(--cds-sp-05); }
  .doc-sources li { margin-bottom: var(--cds-sp-02); line-height: 1.4; }
  .doc-sources a { color: var(--cds-link-primary); text-decoration: none; }
  .doc-sources a:hover { text-decoration: underline; }
  .src-domain { color: var(--cds-text-helper); font-size: 0.6875rem; }

  .disclaimer {
    font-size: 0.6875rem; color: var(--cds-text-helper); line-height: 1.5;
    border-top: 1px solid var(--cds-border-subtle); padding-top: var(--cds-sp-04);
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
    <span class="cds-header__prefix">IBM</span>&nbsp;Find&nbsp;a&nbsp;Doctor
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
    <strong>Find a Doctor.</strong> Describe who you need and where — the agent
    pulls real listings and trusted-site review snippets, then ranks the matches
    with pros &amp; cons in the panel on the right. Informational only, not medical advice.
  </div>
  <div class="app-intro__tools">
    <span class="tools-label">Tools</span>
    <span class="tool-pill">📍 Geocoding · OSM</span>
    <span class="tool-pill">🏥 Listings · OpenStreetMap</span>
    <span class="tool-pill">🔎 Web search · Tavily</span>
    <span class="tool-pill">⭐ Reviews · Healthgrades/Zocdoc…</span>
  </div>
</div>

<main>
  <div class="chat-panel">
    <div class="panel-title">Chat with the agent</div>

    <div class="chips">
      <div class="chip" onclick="sendChip(this)">Find a cardiologist in Boston</div>
      <div class="chip" onclick="sendChip(this)">A really experienced pediatric dentist in Austin</div>
      <div class="chip" onclick="sendChip(this)">Dermatologist in Seattle, good reviews</div>
      <div class="chip" onclick="sendChip(this)">An OB-GYN in Chicago accepting new patients</div>
      <div class="chip" onclick="sendChip(this)">Top-rated orthopedic surgeon near San Mateo, CA</div>
      <div class="chip" onclick="sendChip(this)">A family doctor in Pleasantville NY who's good with kids</div>
    </div>

    <div class="messages" id="messages"></div>

    <div class="input-row">
      <input type="text" id="userInput"
        placeholder="Describe the doctor you're looking for…"
        onkeydown="if(event.key==='Enter') sendMessage()" />
      <button class="cds-btn btn" id="sendBtn" onclick="sendMessage()">Send</button>
    </div>
  </div>

  <div class="data-panel">
    <div class="data-panel-header">
      <span>Matching Doctors</span>
      <span class="refresh-badge" id="refreshBadge">auto-refresh 10s</span>
    </div>
    <div class="data-scroll" id="dataScroll">
      <div class="empty-state" id="emptyState">
        <div class="icon">🩺</div>
        <p>Tell the agent a location and what kind of doctor you need. It pulls listings and trusted-site reviews, then ranks them with pros and cons here.</p>
        <div class="hint">Try: "An experienced cardiologist in Boston with great reviews"</div>
      </div>
    </div>
  </div>
</main>

<script>
  let SESSION_ID = sessionStorage.getItem('find_a_doctor_session');
  if (!SESSION_ID) {
    SESSION_ID = (crypto.randomUUID
      ? crypto.randomUUID()
      : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
          const r = Math.random() * 16 | 0;
          return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        }));
    sessionStorage.setItem('find_a_doctor_session', SESSION_ID);
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

  function renderContext(data) {
    const chips = [];
    if (data.geo && data.geo.display_name)
      chips.push('<span class="tag loc">📍 ' + esc(data.geo.display_name) + '</span>');
    else if (data.location)
      chips.push('<span class="tag loc">📍 ' + esc(data.location) + '</span>');
    if (data.specialty && data.specialty !== '')
      chips.push('<span class="tag spec">' + esc(data.specialty) + '</span>');
    (data.preferences || []).forEach(p => chips.push('<span class="tag pref">' + esc(p) + '</span>'));
    if (chips.length === 0) return null;
    return '<div class="info-block"><div class="info-row">' +
           '<div class="info-label">Searching for</div>' + chips.join('') + '</div></div>';
  }

  function renderDoctors(docs) {
    if (!docs || docs.length === 0) return null;
    return docs.map((d, i) => {
      const meta = [];
      if (d.specialty) meta.push('<span class="badge spec">' + esc(d.specialty) + '</span>');
      if (d.distance_km != null) meta.push('<span class="badge">' + esc(d.distance_km) + ' km</span>');

      const contact = [];
      if (d.address) contact.push('<span>' + esc(d.address) + '</span>');
      if (d.phone) contact.push('<span>☎ ' + esc(d.phone) + '</span>');
      if (d.website) contact.push('<a href="' + esc(d.website) + '" target="_blank" rel="noopener">Website ↗</a>');
      const contactHtml = contact.length ? '<div class="doc-contact">' + contact.join('') + '</div>' : '';

      const pros = (d.pros && d.pros.length)
        ? '<div class="pc-col pros"><span class="label">Pros</span><ul>' +
            d.pros.map(p => '<li>' + esc(p) + '</li>').join('') + '</ul></div>' : '';
      const cons = (d.cons && d.cons.length)
        ? '<div class="pc-col cons"><span class="label">Cons</span><ul>' +
            d.cons.map(c => '<li>' + esc(c) + '</li>').join('') + '</ul></div>' : '';
      const pcHtml = (pros || cons) ? '<div class="pc-grid">' + pros + cons + '</div>' : '';

      const sources = (d.sources && d.sources.length)
        ? '<details class="doc-sources"><summary>Sources (' + d.sources.length + ')</summary><ul>' +
            d.sources.map(s => '<li><a href="' + esc(s.url) + '" target="_blank" rel="noopener">' +
              esc(s.title || s.url) + '</a> <span class="src-domain">' + esc(s.domain || '') +
              '</span></li>').join('') + '</ul></details>'
        : '';

      return (
        '<div class="doc-card">' +
          '<div class="doc-head">' +
            '<div class="doc-num">' + (i + 1) + '</div>' +
            '<div>' +
              '<div class="doc-name">' + esc(d.name || 'Doctor') + '</div>' +
              (meta.length ? '<div class="doc-meta">' + meta.join('') + '</div>' : '') +
            '</div>' +
          '</div>' +
          (d.rating_summary ? '<div class="doc-rating">' + esc(d.rating_summary) + '</div>' : '') +
          (d.experience_note ? '<div class="doc-exp">🎓 ' + esc(d.experience_note) + '</div>' : '') +
          contactHtml +
          pcHtml +
          sources +
        '</div>'
      );
    }).join('');
  }

  function refreshPanel(data) {
    const hash = JSON.stringify({ d: data.doctors, g: data.geo, s: data.specialty,
                                  l: data.location, p: data.preferences });
    if (hash === _lastHash) return;
    _lastHash = hash;

    const hasDocs = data.doctors && data.doctors.length > 0;
    const ctx = renderContext(data);
    if (!hasDocs && !ctx) return;

    emptyState.style.display = 'none';
    let html = '';
    if (ctx) { html += '<div class="section-title">Search</div>' + ctx; }
    if (hasDocs) {
      html += '<div class="section-title" style="margin-top:8px">Ranked matches</div>';
      html += renderDoctors(data.doctors) || '';
      html += '<div class="disclaimer">Informational only — not medical advice or an ' +
              'endorsement. Pros/cons summarize public reviews; verify credentials and ' +
              'fit before booking.</div>';
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
    setStatus(true, 'Thinking…');
    addMessage(question, 'user');
    const thinking = addMessage('Searching listings and reviews…', 'thinking');

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
    + carbon_head("Find a Doctor")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
