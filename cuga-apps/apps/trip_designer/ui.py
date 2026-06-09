"""Self-contained HTML UI for Trip Designer. SSE-driven.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation. Layout: left trip-details form, right stacked plan /
tool-call log / itinerary panels, streamed live over SSE.
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { height: 100vh; display: flex; flex-direction: column; }

  /* Header status badge (kept as a Carbon pill / tag) */
  header.app-header {
    display: flex; align-items: center; justify-content: space-between; gap: var(--cds-sp-05);
  }
  header.app-header .subtitle {
    margin-left: var(--cds-sp-04);
    font-size: 0.75rem; font-weight: 400;
    color: var(--cds-text-helper); letter-spacing: 0;
  }
  .badge {
    display: inline-flex; align-items: center; gap: var(--cds-sp-02);
    font-size: 0.75rem; padding: 0 var(--cds-sp-03); height: 1.5rem;
    border-radius: 0.9375rem; font-weight: 400; letter-spacing: 0.16px;
    white-space: nowrap;
  }
  .badge.idle    { background: var(--cds-layer-accent);     color: var(--cds-text-secondary); }
  .badge.running { background: var(--cds-support-info-bg);   color: var(--cds-link-primary); }
  .badge.done    { background: var(--cds-support-success-bg);color: var(--cds-support-success); }
  .badge.error   { background: var(--cds-support-error-bg);  color: var(--cds-support-error); }

  main {
    flex: 1;
    display: grid;
    grid-template-columns: 380px 1fr;
    gap: var(--cds-sp-05);
    padding: var(--cds-sp-05);
    overflow: hidden;
    min-height: 0;
  }

  .panel {
    background: var(--cds-layer-01);
    border: 1px solid var(--cds-border-subtle);
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .panel-header {
    padding: var(--cds-sp-04) var(--cds-sp-05);
    border-bottom: 1px solid var(--cds-border-subtle);
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--cds-text-secondary);
    letter-spacing: 0.32px;
    text-transform: uppercase;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .panel-body {
    padding: var(--cds-sp-05);
    overflow-y: auto;
    flex: 1;
  }

  /* Form */
  .form-row { margin-bottom: var(--cds-sp-05); }
  .form-row label {
    display: block;
    font-size: 0.75rem;
    font-weight: 400;
    color: var(--cds-text-secondary);
    letter-spacing: 0.32px;
    margin-bottom: var(--cds-sp-03);
  }
  .form-row input, .form-row select, .form-row textarea {
    width: 100%;
    background: var(--cds-field-01);
    color: var(--cds-text-primary);
    border: none;
    border-bottom: 1px solid var(--cds-border-strong);
    padding: 0 var(--cds-sp-05);
    min-height: 2.5rem;
    font-family: var(--cds-font-sans);
    font-size: 0.875rem; letter-spacing: 0.16px;
  }
  .form-row textarea { resize: vertical; min-height: 4rem; padding: var(--cds-sp-04) var(--cds-sp-05); line-height: 1.43; }
  .form-row input::placeholder, .form-row textarea::placeholder { color: var(--cds-text-placeholder); }
  .form-row input:focus, .form-row select:focus, .form-row textarea:focus {
    outline: 2px solid var(--cds-focus); outline-offset: -2px;
  }
  .form-row select {
    appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6l.7-.7L8 9.6l4.3-4.3.7.7z'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right var(--cds-sp-05) center;
    padding-right: var(--cds-sp-08);
  }
  .form-row .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--cds-sp-04); }

  button#run {
    width: 100%;
    background: var(--cds-button-primary);
    color: var(--cds-text-on-color);
    border: 1px solid transparent;
    padding: 0 var(--cds-sp-05);
    min-height: 3rem;
    font-family: var(--cds-font-sans);
    font-size: 0.875rem;
    font-weight: 400;
    letter-spacing: 0.16px;
    cursor: pointer;
    margin-top: var(--cds-sp-03);
    text-align: left;
    transition: background var(--cds-dur-mod) var(--cds-ease-productive);
  }
  button#run:hover  { background: var(--cds-button-primary-hover); }
  button#run:active { background: var(--cds-button-primary-active); }
  button#run:focus-visible, button#run:focus {
    outline: 2px solid var(--cds-focus); outline-offset: -2px;
    box-shadow: inset 0 0 0 1px var(--cds-focus-inset);
  }
  button#run:disabled { background: var(--cds-layer-accent); color: var(--cds-text-placeholder); cursor: wait; }

  .examples {
    margin-top: var(--cds-sp-06);
    border-top: 1px solid var(--cds-border-subtle);
    padding-top: var(--cds-sp-05);
  }
  .examples-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.32px;
    color: var(--cds-text-helper);
    margin-bottom: var(--cds-sp-03);
    font-weight: 600;
  }
  .chips { display: flex; flex-wrap: wrap; gap: var(--cds-sp-03); }
  .chip {
    font-size: 0.75rem;
    padding: var(--cds-sp-02) var(--cds-sp-04);
    border-radius: 0.9375rem;
    background: var(--cds-layer-02);
    border: 1px solid var(--cds-border-subtle);
    color: var(--cds-text-secondary);
    cursor: pointer;
    line-height: 1.35;
    transition: all var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .chip:hover { border-color: var(--cds-interactive); color: #fff; background: var(--cds-interactive); }

  /* Right column */
  .right {
    display: grid;
    grid-template-rows: minmax(0, 0.95fr) minmax(0, 1fr) minmax(0, 1.4fr);
    gap: var(--cds-sp-05);
    overflow: hidden;
  }

  .plan-card {
    border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-04) var(--cds-sp-05);
    margin-bottom: var(--cds-sp-04);
    background: var(--cds-layer-02);
  }
  .plan-card.current {
    border-color: var(--cds-interactive);
    box-shadow: 0 0 0 1px var(--cds-interactive) inset;
  }
  .plan-card-meta {
    font-size: 0.75rem;
    color: var(--cds-text-helper);
    margin-bottom: var(--cds-sp-03);
    display: flex; justify-content: space-between;
  }
  .plan-card .plan-text {
    font-size: 0.8125rem;
    color: var(--cds-text-secondary);
    white-space: pre-wrap;
    line-height: 1.5;
  }

  .tool-call {
    border-left: 3px solid var(--cds-border-strong);
    padding: var(--cds-sp-03) var(--cds-sp-04);
    margin-bottom: var(--cds-sp-03);
    background: var(--cds-layer-02);
    font-size: 0.75rem;
  }
  .tool-call.plan   { border-left-color: var(--cds-interactive); }
  .tool-call.web    { border-left-color: var(--cds-link-primary); }
  .tool-call.encyc  { border-left-color: var(--cds-support-success); }
  .tool-call.geo    { border-left-color: var(--cds-support-warning); }
  .tool-call.error  { border-left-color: var(--cds-support-error); }
  .tool-call .tname { font-family: var(--cds-font-mono); font-weight: 600; color: var(--cds-text-primary); }
  .tool-call .targs { font-family: var(--cds-font-mono); color: var(--cds-text-secondary); font-size: 0.6875rem; margin-top: 2px; white-space: pre-wrap; word-break: break-word; }
  .tool-call .tprev { color: var(--cds-text-helper); font-size: 0.6875rem; margin-top: var(--cds-sp-02); font-style: italic; white-space: pre-wrap; word-break: break-word; }
  .tool-call .pill { display:inline-block; padding:0 var(--cds-sp-03); height: 1.125rem; line-height: 1.125rem; border-radius:0.9375rem; background:var(--cds-layer-accent); color:var(--cds-text-secondary); font-size:0.625rem; font-weight:600; margin-left:var(--cds-sp-03); vertical-align: middle; font-family: var(--cds-font-mono); }

  .iti-body { font-size: 0.875rem; line-height: 1.65; color: var(--cds-text-primary); }
  .iti-body h1, .iti-body h2, .iti-body h3, .iti-body h4 { color: var(--cds-text-primary); margin: var(--cds-sp-06) 0 var(--cds-sp-03); font-weight: 600; }
  .iti-body h3 { font-size: 1rem; }
  .iti-body h4 { font-size: 0.875rem; color: var(--cds-link-primary); }
  .iti-body ul { padding-left: 1.4rem; }
  .iti-body li { margin-bottom: var(--cds-sp-02); }
  .iti-body a { color: var(--cds-link-primary); text-decoration: none; }
  .iti-body a:hover { text-decoration: underline; color: var(--cds-link-hover); }
  .iti-body strong { color: var(--cds-text-primary); font-weight: 600; }
  .iti-body code { background: var(--cds-layer-accent); color: var(--cds-link-primary); padding: 1px var(--cds-sp-03); font-family: var(--cds-font-mono); font-size: 0.8125rem; }

  .placeholder {
    color: var(--cds-text-placeholder);
    font-style: italic;
    font-size: 0.8125rem;
    text-align: center;
    padding: var(--cds-sp-06);
  }
  .placeholder code { font-family: var(--cds-font-mono); color: var(--cds-link-primary); }
  .footer-note {
    padding: var(--cds-sp-03) var(--cds-sp-05);
    font-size: 0.75rem;
    color: var(--cds-text-helper);
    text-align: center;
    border-top: 1px solid var(--cds-border-subtle);
  }
</style>"""

_BODY = r"""
<header class="cds-header app-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Trip&nbsp;Designer
    <span class="subtitle">light prompt · CUGA decides the workflow · plan + tool calls stream live</span>
  </div>
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
        Plan <span style="margin-left:8px; color:var(--cds-text-helper); font-weight: 400; text-transform:none; letter-spacing: 0;">— what the agent decided to do</span>
        <span style="flex:1"></span>
        <span id="planCount" style="color:var(--cds-text-helper); font-weight: 400; text-transform: none;">no plan yet</span>
      </div>
      <div class="panel-body" id="planBody">
        <div class="placeholder">The agent's plan will appear here as soon as it calls <code>propose_plan</code>.</div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        Tool calls <span style="margin-left:8px; color:var(--cds-text-helper); font-weight: 400; text-transform:none; letter-spacing: 0;">— what the agent actually fetched</span>
        <span style="flex:1"></span>
        <span id="callCount" style="color:var(--cds-text-helper); font-weight: 400; text-transform: none;">0 calls</span>
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
      itiBody.innerHTML = `<div class="placeholder" style="color:var(--cds-support-error)">${escapeHtml(j.error || 'unknown error')}</div>`;
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
          itiBody.innerHTML = `<div class="placeholder" style="color:var(--cds-support-error)">${escapeHtml(ev.error)}</div>`;
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
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("Trip Designer")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
