"""
HTML UI for the Recipe Composer demo app.
Exported as _HTML — a single self-contained string served by FastAPI's "/" route.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation.

Layout:
  Left  — Chat panel: prompt chips, message log, input field
  Right — Live data panel: current pantry + diet + suggested recipe cards
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { background: var(--cds-background); display: flex; flex-direction: column; }

  main {
    display: grid;
    grid-template-columns: 26rem 1fr;
    gap: 0; flex: 1; overflow: hidden;
    height: calc(100vh - 3rem);
  }
  @media (max-width: 820px) {
    main { grid-template-columns: 1fr; height: auto; }
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
  .tag.pantry  { background: var(--cds-support-success-bg); color: var(--cds-support-success); }
  .tag.diet    { background: var(--cds-support-info-bg);    color: var(--cds-link-primary); }
  .tag.allergy { background: var(--cds-support-error-bg);   color: var(--cds-support-error); }

  /* ── Recipe cards ────────────────────────────────────────────────────── */
  .rec-card {
    background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-05);
    transition: border-color var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .rec-card:hover { border-color: var(--cds-border-strong); }
  .rec-head {
    display: flex; align-items: flex-start; gap: var(--cds-sp-04); margin-bottom: var(--cds-sp-04);
  }
  .rec-num {
    background: var(--cds-interactive); color: #fff;
    width: 1.625rem; height: 1.625rem; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.75rem; font-weight: 600; flex-shrink: 0;
    font-family: var(--cds-font-mono);
  }
  .rec-title { font-size: 0.9375rem; font-weight: 600; line-height: 1.3; color: var(--cds-text-primary); }
  .rec-meta {
    font-size: 0.6875rem; color: var(--cds-text-secondary); margin-top: var(--cds-sp-02);
    display: flex; gap: var(--cds-sp-03); flex-wrap: wrap; align-items: center;
  }
  .rec-meta .badge {
    background: var(--cds-layer-accent); border: 1px solid var(--cds-border-subtle);
    padding: 1px var(--cds-sp-03); font-size: 0.6875rem; color: var(--cds-text-secondary);
  }
  .rec-meta .difficulty.easy   { color: var(--cds-support-success); border-color: var(--cds-support-success); }
  .rec-meta .difficulty.medium { color: var(--cds-link-primary);    border-color: var(--cds-link-primary); }
  .rec-meta .difficulty.hard   { color: var(--cds-support-error);   border-color: var(--cds-support-error); }

  .rec-why {
    font-size: 0.8125rem; color: var(--cds-text-secondary); line-height: 1.6;
    padding-left: 2.375rem; margin-bottom: var(--cds-sp-03);
  }
  .rec-detail { padding-left: 2.375rem; font-size: 0.75rem; }
  .rec-uses, .rec-missing { margin-top: var(--cds-sp-03); }
  .rec-uses .label    { color: var(--cds-support-success); font-weight: 600; }
  .rec-missing .label { color: var(--cds-link-primary); font-weight: 600; }
  .rec-detail ul { margin: var(--cds-sp-02) 0 0 0; padding-left: var(--cds-sp-05); color: var(--cds-text-secondary); }
  .rec-detail li { margin-bottom: var(--cds-sp-01); line-height: 1.5; }

  .rec-steps { padding-left: 2.375rem; margin-top: var(--cds-sp-04); font-size: 0.75rem; }
  .rec-steps summary { cursor: pointer; color: var(--cds-link-primary); font-weight: 600; }
  .rec-steps ol { margin-top: var(--cds-sp-03); padding-left: var(--cds-sp-05); color: var(--cds-text-secondary); }
  .rec-steps li { margin-bottom: var(--cds-sp-02); line-height: 1.5; }

  /* Status dot (the one rounded accent in the header) */
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
    <span class="cds-header__prefix">IBM</span>&nbsp;Recipe&nbsp;Composer
  </div>
  <div class="cds-header__actions">
    <span class="status-badge">
      <span class="status-dot" id="statusDot"></span>
      <span class="cds-helper-01" id="statusText">Ready</span>
    </span>
  </div>
</header>

<main>
  <div class="chat-panel">
    <div class="panel-title">Chat with the agent</div>

    <div class="chips">
      <div class="chip" onclick="sendChip(this)">I have chicken breast and rice</div>
      <div class="chip" onclick="sendChip(this)">Add eggs, spinach, and tomato</div>
      <div class="chip" onclick="sendChip(this)">I'm vegetarian</div>
      <div class="chip" onclick="sendChip(this)">I'm allergic to peanut butter</div>
      <div class="chip" onclick="sendChip(this)">What can I cook tonight?</div>
      <div class="chip" onclick="sendChip(this)">Suggest something quick under 20 minutes</div>
      <div class="chip" onclick="sendChip(this)">What can I substitute for butter?</div>
      <div class="chip" onclick="sendChip(this)">Roughly how many calories in 200g of pasta?</div>
      <div class="chip" onclick="sendChip(this)">Anything with high protein?</div>
    </div>

    <div class="messages" id="messages"></div>

    <div class="input-row">
      <input type="text" id="userInput"
        placeholder="Tell me what's in your pantry…"
        onkeydown="if(event.key==='Enter') sendMessage()" />
      <button class="cds-btn btn" id="sendBtn" onclick="sendMessage()">Send</button>
    </div>
  </div>

  <div class="data-panel">
    <div class="data-panel-header">
      <span>Your Pantry &amp; Tonight's Ideas</span>
      <span class="refresh-badge" id="refreshBadge">auto-refresh 10s</span>
    </div>
    <div class="data-scroll" id="dataScroll">
      <div class="empty-state" id="emptyState">
        <div class="icon">🥕</div>
        <p>Tell the agent what's in your pantry, and any diet or allergies. It will keep this panel in sync.</p>
        <div class="hint">Try: "I have chicken, rice, broccoli, and soy sauce"</div>
      </div>
    </div>
  </div>
</main>

<script>
  // Session id
  let SESSION_ID = sessionStorage.getItem('recipe_composer_session');
  if (!SESSION_ID) {
    SESSION_ID = (crypto.randomUUID
      ? crypto.randomUUID()
      : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
          const r = Math.random() * 16 | 0;
          return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        }));
    sessionStorage.setItem('recipe_composer_session', SESSION_ID);
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

  function renderInfoBlock(data) {
    const rows = [];
    if (data.pantry && data.pantry.length) {
      rows.push(
        '<div class="info-row">' +
        '<div class="info-label">In your pantry (' + data.pantry.length + ')</div>' +
        data.pantry.map(p => '<span class="tag pantry">' + esc(p) + '</span>').join('') +
        '</div>'
      );
    }
    if (data.diet && data.diet !== 'no preference' && data.diet !== '') {
      rows.push(
        '<div class="info-row">' +
        '<div class="info-label">Diet</div>' +
        '<span class="tag diet">' + esc(data.diet) + '</span>' +
        '</div>'
      );
    }
    if (data.allergies && data.allergies.length) {
      rows.push(
        '<div class="info-row">' +
        '<div class="info-label">Allergies / avoid</div>' +
        data.allergies.map(a => '<span class="tag allergy">' + esc(a) + '</span>').join('') +
        '</div>'
      );
    }
    if (rows.length === 0) return null;
    return '<div class="info-block">' + rows.join('') + '</div>';
  }

  function renderRecipes(recs) {
    if (!recs || recs.length === 0) return null;
    return recs.map((r, i) => {
      const meta = [];
      if (r.time_minutes != null) meta.push('<span class="badge">' + esc(r.time_minutes) + ' min</span>');
      if (r.difficulty) {
        const cls = String(r.difficulty).toLowerCase();
        meta.push('<span class="badge difficulty ' + esc(cls) + '">' + esc(r.difficulty) + '</span>');
      }
      if (r.calories_est != null) meta.push('<span class="badge">~' + esc(r.calories_est) + ' kcal</span>');

      const usesHtml = (r.uses && r.uses.length)
        ? ('<div class="rec-uses"><span class="label">Uses:</span><ul>' +
            r.uses.map(u => '<li>' + esc(u) + '</li>').join('') + '</ul></div>')
        : '';
      const missingHtml = (r.missing && r.missing.length)
        ? ('<div class="rec-missing"><span class="label">Pick up:</span><ul>' +
            r.missing.map(m => '<li>' + esc(m) + '</li>').join('') + '</ul></div>')
        : '';
      const stepsHtml = (r.steps && r.steps.length)
        ? ('<details class="rec-steps"><summary>How to cook it</summary><ol>' +
            r.steps.map(s => '<li>' + esc(s) + '</li>').join('') + '</ol></details>')
        : '';

      return (
        '<div class="rec-card">' +
          '<div class="rec-head">' +
            '<div class="rec-num">' + (i + 1) + '</div>' +
            '<div>' +
              '<div class="rec-title">' + esc(r.title || 'Recipe') + '</div>' +
              (meta.length ? '<div class="rec-meta">' + meta.join('') + '</div>' : '') +
            '</div>' +
          '</div>' +
          (r.why ? '<div class="rec-why">' + esc(r.why) + '</div>' : '') +
          ((usesHtml || missingHtml) ? '<div class="rec-detail">' + usesHtml + missingHtml + '</div>' : '') +
          stepsHtml +
        '</div>'
      );
    }).join('');
  }

  function refreshPanel(data) {
    const hash = JSON.stringify(data);
    if (hash === _lastHash) return;
    _lastHash = hash;

    const hasInfo = (data.pantry && data.pantry.length) ||
                    (data.diet && data.diet !== '') ||
                    (data.allergies && data.allergies.length);
    const hasRecs = data.recipes && data.recipes.length > 0;

    if (!hasInfo && !hasRecs) return;

    emptyState.style.display = 'none';
    let html = '';
    if (hasInfo) {
      html += '<div class="section-title">Your kitchen</div>';
      html += renderInfoBlock(data) || '';
    }
    if (hasRecs) {
      html += '<div class="section-title" style="margin-top:8px">Tonight\'s ideas</div>';
      html += renderRecipes(data.recipes) || '';
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
    setStatus(true, 'Thinking…');
    addMessage(question, 'user');
    const thinking = addMessage('Working on it…', 'thinking');

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
    + carbon_head("Recipe Composer")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
