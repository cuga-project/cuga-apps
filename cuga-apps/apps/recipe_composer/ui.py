"""
HTML UI for the Recipe Composer demo app.
Exported as _HTML — a single self-contained string served by FastAPI's "/" route.

Layout:
  Left  — Chat panel: prompt chips, message log, input field
  Right — Live data panel: current pantry + diet + suggested recipe cards
"""

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Recipe Composer</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:       #0f1117;
    --card:     #1a1a2e;
    --border:   #2d2d4a;
    --accent:   #fb923c;   /* warm orange */
    --accent2:  #4ade80;   /* fresh green */
    --accent3:  #facc15;   /* yellow */
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
    background: var(--card);
    border-right: 1px solid var(--border);
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
    background: var(--accent); color: #fff; border: none;
    border-radius: 8px; padding: 9px 18px;
    font-size: 14px; font-weight: 600;
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

  .info-block {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px;
  }
  .info-row {
    display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px;
  }
  .info-row:last-child { margin-bottom: 0; }
  .info-label {
    font-size: 11px; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.8px;
    width: 100%; margin-bottom: 4px;
  }
  .tag {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 20px; padding: 3px 11px;
    font-size: 12px; color: var(--text);
  }
  .tag.pantry  { border-color: var(--accent2); color: var(--accent2); }
  .tag.diet    { border-color: var(--accent3); color: var(--accent3); }
  .tag.allergy { border-color: var(--danger);  color: var(--danger);  }

  /* Recipe cards */
  .rec-card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px;
    transition: border-color 0.2s;
  }
  .rec-card:hover { border-color: var(--accent); }
  .rec-head {
    display: flex; align-items: flex-start; gap: 12px; margin-bottom: 10px;
  }
  .rec-num {
    background: var(--accent); color: #fff;
    width: 26px; height: 26px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 700; flex-shrink: 0;
  }
  .rec-title { font-size: 15px; font-weight: 700; line-height: 1.3; }
  .rec-meta {
    font-size: 11px; color: var(--muted); margin-top: 3px;
    display: flex; gap: 8px; flex-wrap: wrap; align-items: center;
  }
  .rec-meta .badge {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 4px; padding: 1px 7px; font-size: 11px;
  }
  .rec-meta .difficulty.easy   { color: var(--success); border-color: var(--success); }
  .rec-meta .difficulty.medium { color: var(--accent3); border-color: var(--accent3); }
  .rec-meta .difficulty.hard   { color: var(--danger);  border-color: var(--danger);  }

  .rec-why {
    font-size: 13px; color: #c0c8d8; line-height: 1.6;
    padding-left: 38px; margin-bottom: 8px;
  }
  .rec-detail { padding-left: 38px; font-size: 12px; }
  .rec-uses, .rec-missing {
    margin-top: 6px;
  }
  .rec-uses .label   { color: var(--success); font-weight: 600; }
  .rec-missing .label { color: var(--accent3); font-weight: 600; }
  .rec-detail ul { margin: 4px 0 0 0; padding-left: 18px; color: var(--muted); }
  .rec-detail li { margin-bottom: 2px; line-height: 1.5; }

  .rec-steps { padding-left: 38px; margin-top: 10px; font-size: 12px; }
  .rec-steps summary { cursor: pointer; color: var(--accent); font-weight: 600; }
  .rec-steps ol { margin-top: 8px; padding-left: 18px; color: #c0c8d8; }
  .rec-steps li { margin-bottom: 4px; line-height: 1.5; }
</style>
</head>
<body>

<header>
  <div class="header-icon">🍳</div>
  <h1>Recipe <span>Composer</span></h1>
  <div class="status-badge">
    <div class="status-dot" id="statusDot"></div>
    <span id="statusText">Ready</span>
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
      <button class="btn" id="sendBtn" onclick="sendMessage()">Send</button>
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
</body>
</html>
"""
