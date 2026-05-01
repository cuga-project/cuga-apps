"""Self-contained dark-themed HTML UI for Trip Designer. SSE-driven."""

_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trip Designer</title>
<style>
  *  { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  header {
    padding: 14px 20px;
    background: #1a1a2e;
    border-bottom: 1px solid #2d2d4a;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    position: sticky;
    top: 0;
    z-index: 5;
  }
  header h1 { margin: 0; font-size: 18px; font-weight: 700; letter-spacing: -0.01em; }
  header h1 span.subtitle {
    margin-left: 12px;
    font-size: 12px;
    font-weight: 500;
    color: #94a3b8;
    letter-spacing: 0;
  }
  .badge {
    font-size: 12px;
    padding: 5px 11px;
    border-radius: 999px;
    font-weight: 600;
    border: 1px solid;
  }
  .badge.idle    { background: #1e293b;   color: #94a3b8; border-color: #334155;  }
  .badge.running { background: #1e3a8a33; color: #93c5fd; border-color: #3b82f6;  }
  .badge.done    { background: #064e3b33; color: #6ee7b7; border-color: #10b981;  }
  .badge.error   { background: #7f1d1d33; color: #fca5a5; border-color: #ef4444;  }

  main {
    flex: 1;
    display: grid;
    grid-template-columns: 380px 1fr;
    gap: 14px;
    padding: 14px;
    overflow: hidden;
    min-height: 0;
  }
  .panel {
    background: #1a1a2e;
    border: 1px solid #2d2d4a;
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .panel-header {
    padding: 10px 14px;
    border-bottom: 1px solid #2d2d4a;
    font-size: 11px;
    font-weight: 700;
    color: #94a3b8;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .panel-body {
    padding: 14px;
    overflow-y: auto;
    flex: 1;
  }

  /* Form */
  .form-row { margin-bottom: 12px; }
  .form-row label {
    display: block;
    font-size: 11px;
    font-weight: 700;
    color: #94a3b8;
    letter-spacing: 0.04em;
    margin-bottom: 4px;
    text-transform: uppercase;
  }
  .form-row input, .form-row select, .form-row textarea {
    width: 100%;
    background: #0f1117;
    color: #e2e8f0;
    border: 1px solid #2d2d4a;
    border-radius: 7px;
    padding: 8px 10px;
    font: inherit;
    font-size: 13px;
  }
  .form-row textarea { resize: vertical; min-height: 50px; }
  .form-row input:focus, .form-row select:focus, .form-row textarea:focus {
    outline: none; border-color: #6366f1;
  }
  .form-row .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }

  button#run {
    width: 100%;
    background: #6366f1;
    color: #fff;
    border: 0;
    border-radius: 8px;
    padding: 11px 16px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    margin-top: 8px;
    transition: background .15s ease;
  }
  button#run:hover  { background: #818cf8; }
  button#run:disabled { opacity: 0.55; cursor: wait; }

  .examples {
    margin-top: 18px;
    border-top: 1px dashed #2d2d4a;
    padding-top: 12px;
  }
  .examples-label {
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748b;
    margin-bottom: 8px;
    font-weight: 700;
  }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    font-size: 11.5px;
    padding: 5px 9px;
    border-radius: 6px;
    background: #0f1117;
    border: 1px solid #2d2d4a;
    color: #cbd5e1;
    cursor: pointer;
    line-height: 1.35;
  }
  .chip:hover { border-color: #6366f1; color: #fff; background: #1e1b4b; }

  /* Right column */
  .right {
    display: grid;
    grid-template-rows: minmax(0, 0.95fr) minmax(0, 1fr) minmax(0, 1.4fr);
    gap: 14px;
    overflow: hidden;
  }

  .plan-card {
    border: 1px solid #2d2d4a;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 10px;
    background: #0f1117;
  }
  .plan-card.current {
    border-color: #6366f1;
    box-shadow: 0 0 0 1px #6366f1 inset;
  }
  .plan-card-meta {
    font-size: 10.5px;
    color: #64748b;
    margin-bottom: 6px;
    display: flex; justify-content: space-between;
  }
  .plan-card .plan-text {
    font-size: 12.5px;
    color: #cbd5e1;
    white-space: pre-wrap;
    line-height: 1.5;
  }

  .tool-call {
    border-left: 3px solid #475569;
    padding: 6px 10px;
    margin-bottom: 6px;
    background: #0f1117;
    border-radius: 4px;
    font-size: 12px;
  }
  .tool-call.plan   { border-left-color: #6366f1; }
  .tool-call.web    { border-left-color: #0ea5e9; }
  .tool-call.encyc  { border-left-color: #10b981; }
  .tool-call.geo    { border-left-color: #f59e0b; }
  .tool-call.error  { border-left-color: #ef4444; }
  .tool-call .tname { font-family: ui-monospace, "SF Mono", monospace; font-weight: 700; color: #e2e8f0; }
  .tool-call .targs { font-family: ui-monospace, "SF Mono", monospace; color: #94a3b8; font-size: 11px; margin-top: 2px; white-space: pre-wrap; word-break: break-word; }
  .tool-call .tprev { color: #64748b; font-size: 11px; margin-top: 4px; font-style: italic; white-space: pre-wrap; word-break: break-word; }
  .tool-call .pill { display:inline-block; padding:0 6px; border-radius:3px; background:#1e293b; color:#94a3b8; font-size:10px; font-weight:700; margin-left:6px; vertical-align: middle; }

  .iti-body { font-size: 14px; line-height: 1.65; color: #e2e8f0; }
  .iti-body h1, .iti-body h2, .iti-body h3, .iti-body h4 { color: #fff; margin: 18px 0 8px; }
  .iti-body h3 { font-size: 15px; }
  .iti-body h4 { font-size: 13.5px; color: #fde68a; }
  .iti-body ul { padding-left: 22px; }
  .iti-body li { margin-bottom: 4px; }
  .iti-body a { color: #93c5fd; text-decoration: none; }
  .iti-body a:hover { text-decoration: underline; }
  .iti-body strong { color: #fde68a; }
  .iti-body code { background: #1e293b; padding: 1px 6px; border-radius: 4px; font-size: 12.5px; }

  .placeholder {
    color: #475569;
    font-style: italic;
    font-size: 13px;
    text-align: center;
    padding: 20px;
  }
  .footer-note {
    padding: 6px 14px;
    font-size: 11px;
    color: #64748b;
    text-align: center;
    border-top: 1px solid #1e293b;
  }
</style>
</head>
<body>
<header>
  <h1>Trip Designer <span class="subtitle">light prompt · CUGA decides the workflow · plan + tool calls stream live</span></h1>
  <span id="status" class="badge idle">idle</span>
</header>

<main>
  <!-- Left: form -->
  <section class="panel">
    <div class="panel-header">Trip details</div>
    <div class="panel-body">
      <div class="form-row">
        <label for="destination">Destination</label>
        <input id="destination" type="text" placeholder="e.g. Berlin, Kyoto, Lisbon">
      </div>

      <div class="form-row">
        <div class="row2">
          <div>
            <label for="days">Days</label>
            <input id="days" type="number" value="5" min="1" max="30">
          </div>
          <div>
            <label for="month">Month</label>
            <input id="month" type="text" value="June" placeholder="any">
          </div>
        </div>
      </div>

      <div class="form-row">
        <label for="origin">Origin city (optional)</label>
        <input id="origin" type="text" placeholder="e.g. New York">
      </div>

      <div class="form-row">
        <label for="interests">Interests</label>
        <input id="interests" type="text" placeholder="comma-separated · e.g. history, street food, jazz">
      </div>

      <div class="form-row">
        <label for="style">Travel style</label>
        <select id="style">
          <option value="">— any —</option>
          <option value="budget">budget</option>
          <option value="mid-range" selected>mid-range</option>
          <option value="luxury">luxury</option>
          <option value="backpacker">backpacker</option>
          <option value="family">family</option>
        </select>
      </div>

      <div class="form-row">
        <label for="constraints">Hard constraints</label>
        <textarea id="constraints" placeholder="e.g. must finish at airport by 3pm Friday · max 30 min between activities · vegetarian only"></textarea>
      </div>

      <button id="run">Design itinerary</button>

      <div class="examples">
        <div class="examples-label">Quick fills</div>
        <div class="chips">
          <span class="chip" data-d="Berlin" data-days="5" data-m="March" data-i="history, street food">Berlin · history + street food (5d)</span>
          <span class="chip" data-d="Kyoto" data-days="4" data-m="November" data-i="temples, gardens, food">Kyoto · 4-day temple + food</span>
          <span class="chip" data-d="Lisbon" data-days="3" data-m="May" data-i="azulejos, fado, viewpoints">Lisbon · 3-day cultural</span>
          <span class="chip" data-d="Reykjavik" data-days="6" data-m="February" data-i="northern lights, hot springs, glaciers">Reykjavik · 6-day winter</span>
        </div>
      </div>
    </div>
  </section>

  <!-- Right: plan + tool log + itinerary -->
  <div class="right">

    <section class="panel">
      <div class="panel-header">
        Plan <span style="margin-left:8px; color:#64748b; font-weight: 500; text-transform:none; letter-spacing: 0;">— what the agent decided to do</span>
        <span style="flex:1"></span>
        <span id="planCount" style="color:#64748b; font-weight: 500; text-transform: none;">no plan yet</span>
      </div>
      <div class="panel-body" id="planBody">
        <div class="placeholder">The agent's plan will appear here as soon as it calls <code>propose_plan</code>.</div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        Tool calls <span style="margin-left:8px; color:#64748b; font-weight: 500; text-transform:none; letter-spacing: 0;">— what the agent actually fetched</span>
        <span style="flex:1"></span>
        <span id="callCount" style="color:#64748b; font-weight: 500; text-transform: none;">0 calls</span>
      </div>
      <div class="panel-body" id="logBody">
        <div class="placeholder">Tool calls will stream here as the agent executes its plan.</div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">Itinerary</div>
      <div class="panel-body" id="itiBody">
        <div class="placeholder">The itinerary will appear here when the agent finishes.</div>
      </div>
    </section>
  </div>
</main>

<div class="footer-note">
  System prompt is &lt;30 lines and prescribes nothing about workflow or tool order. Decomposition is the agent's job.
</div>

<script>
  const dEl = document.getElementById('destination');
  const daysEl = document.getElementById('days');
  const monthEl = document.getElementById('month');
  const originEl = document.getElementById('origin');
  const interestsEl = document.getElementById('interests');
  const styleEl = document.getElementById('style');
  const constraintsEl = document.getElementById('constraints');
  const runBtn = document.getElementById('run');
  const status = document.getElementById('status');
  const planBody = document.getElementById('planBody');
  const planCount = document.getElementById('planCount');
  const logBody = document.getElementById('logBody');
  const callCount = document.getElementById('callCount');
  const itiBody = document.getElementById('itiBody');

  document.querySelectorAll('.chip').forEach(c => c.addEventListener('click', () => {
    dEl.value         = c.dataset.d || '';
    daysEl.value      = c.dataset.days || '5';
    monthEl.value     = c.dataset.m || '';
    interestsEl.value = c.dataset.i || '';
    dEl.focus();
  }));

  let callsLogged = 0;
  let planVersion = 0;

  function setStatus(label, cls) {
    status.textContent = label;
    status.className = 'badge ' + cls;
  }

  function classifyTool(name) {
    if (name === 'propose_plan') return 'plan';
    if (name === 'geocode' || name === 'find_hikes' || name === 'search_attractions' || name === 'get_weather') return 'geo';
    if (name.startsWith('search_wikipedia') || name.startsWith('get_wikipedia') ||
        name.startsWith('get_article') || name.startsWith('get_related') ||
        name.startsWith('search_arxiv') || name.startsWith('get_arxiv') ||
        name.startsWith('search_semantic_scholar') || name.startsWith('get_paper_references')) return 'encyc';
    return 'web';
  }

  function clearPlaceholders() {
    [planBody, logBody, itiBody].forEach(el => {
      const p = el.querySelector('.placeholder');
      if (p) p.remove();
    });
  }

  function addPlan(plan, version, atCalls) {
    clearPlaceholders();
    planBody.querySelectorAll('.plan-card.current').forEach(el => el.classList.remove('current'));
    const card = document.createElement('div');
    card.className = 'plan-card current';
    const meta = document.createElement('div');
    meta.className = 'plan-card-meta';
    meta.innerHTML = `<span>v${version} · proposed after ${atCalls} call${atCalls === 1 ? '' : 's'}</span><span>plan</span>`;
    const body = document.createElement('div');
    body.className = 'plan-text';
    body.textContent = plan;
    card.appendChild(meta);
    card.appendChild(body);
    planBody.prepend(card);
    planVersion = version;
    planCount.textContent = `${version} plan${version === 1 ? '' : 's'}`;
  }

  function addToolCall(ev) {
    clearPlaceholders();
    callsLogged = ev.count;
    callCount.textContent = `${callsLogged} call${callsLogged === 1 ? '' : 's'}`;
    const div = document.createElement('div');
    div.className = 'tool-call ' + classifyTool(ev.tool);
    const argStr = JSON.stringify(ev.args, null, 0).slice(0, 250);
    div.innerHTML = `
      <div><span class="tname">${ev.tool}</span><span class="pill">#${ev.count}</span></div>
      <div class="targs">${escapeHtml(argStr)}</div>
    `;
    logBody.prepend(div);
  }

  function annotateLastToolCall(ev) {
    const found = logBody.querySelector('.tool-call');
    if (!found) return;
    if (!ev.ok) found.classList.add('error');
    if (ev.preview) {
      let prev = found.querySelector('.tprev');
      if (!prev) {
        prev = document.createElement('div');
        prev.className = 'tprev';
        found.appendChild(prev);
      }
      prev.textContent = (ev.ok ? '→ ' : '✗ ') + ev.preview;
    }
  }

  function setItinerary(markdown) {
    clearPlaceholders();
    itiBody.innerHTML = `<div class="iti-body">${markdownToHtml(markdown)}</div>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, ch => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    })[ch]);
  }

  function markdownToHtml(md) {
    if (!md) return '';
    let out = escapeHtml(md);
    out = out.replace(/^#### (.*)$/gm, '<h4>$1</h4>');
    out = out.replace(/^### (.*)$/gm, '<h3>$1</h3>');
    out = out.replace(/^## (.*)$/gm, '<h2>$1</h2>');
    out = out.replace(/^# (.*)$/gm, '<h1>$1</h1>');
    out = out.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    out = out.replace(/\*(.+?)\*/g, '<em>$1</em>');
    out = out.replace(/`([^`]+?)`/g, '<code>$1</code>');
    out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    out = out.replace(/(?:^|\n)((?:- .*(?:\n|$))+)/g, (_m, block) => {
      const items = block.trim().split('\n').map(l => l.replace(/^- /, '').trim());
      return '\n<ul>' + items.map(i => `<li>${i}</li>`).join('') + '</ul>';
    });
    out = out.split(/\n\n+/).map(block => {
      if (/^<(h\d|ul|ol|pre|blockquote)/i.test(block.trim())) return block;
      return `<p>${block.replace(/\n/g, '<br>')}</p>`;
    }).join('\n');
    return out;
  }

  async function run() {
    if (!dEl.value.trim()) { dEl.focus(); return; }

    const payload = {
      destination: dEl.value.trim(),
      days: parseInt(daysEl.value, 10) || 5,
      travel_month: monthEl.value.trim(),
      origin_city: originEl.value.trim(),
      interests: interestsEl.value.split(',').map(s => s.trim()).filter(Boolean),
      travel_style: styleEl.value,
      constraints: constraintsEl.value.trim(),
    };

    runBtn.disabled = true;
    setStatus('starting…', 'running');
    callsLogged = 0;
    planVersion = 0;
    planBody.innerHTML = '<div class="placeholder">Waiting for plan…</div>';
    logBody.innerHTML  = '<div class="placeholder">Waiting for tool calls…</div>';
    itiBody.innerHTML  = '<div class="placeholder">Itinerary will appear here when synthesis finishes…</div>';
    planCount.textContent = 'no plan yet';
    callCount.textContent = '0 calls';

    let resp;
    try {
      resp = await fetch('/api/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
    } catch (e) {
      setStatus('network error', 'error');
      runBtn.disabled = false;
      return;
    }
    const j = await resp.json();
    if (j.error || !j.session_id) {
      setStatus('error', 'error');
      itiBody.innerHTML = `<div class="placeholder" style="color:#fca5a5">${escapeHtml(j.error || 'unknown error')}</div>`;
      runBtn.disabled = false;
      return;
    }
    setStatus('running…', 'running');

    const sse = new EventSource(`/api/stream/${j.session_id}`);
    sse.onmessage = (e) => {
      let ev;
      try { ev = JSON.parse(e.data); } catch (_) { return; }
      switch (ev.type) {
        case 'init': break;
        case 'plan':
          addPlan(ev.plan, ev.version, ev.at_calls);
          break;
        case 'tool_call':
          addToolCall(ev);
          break;
        case 'tool_result':
          annotateLastToolCall(ev);
          break;
        case 'itinerary':
          setItinerary(ev.itinerary);
          break;
        case 'error':
          setStatus('error', 'error');
          itiBody.innerHTML = `<div class="placeholder" style="color:#fca5a5">${escapeHtml(ev.error)}</div>`;
          break;
        case 'done':
          if (ev.status === 'done') setStatus(`done · ${ev.tool_call_count} calls`, 'done');
          else if (ev.status === 'error') setStatus('error', 'error');
          runBtn.disabled = false;
          sse.close();
          break;
      }
    };
    sse.onerror = () => {
      setStatus('stream lost', 'error');
      runBtn.disabled = false;
      sse.close();
    };
  }

  runBtn.addEventListener('click', run);
  document.querySelectorAll('input, textarea, select').forEach(el => {
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) run();
    });
  });
</script>
</body>
</html>
"""
