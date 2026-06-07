"""Self-contained HTML UI for Brief Budget. SSE-driven.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation. Layout, ids, fetch URLs, SSE handling and copy are
preserved exactly — only the styling is restyled to the Carbon look.
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

  /* App-level status badges (pills — Carbon's one rounded element) */
  .badge {
    font-size: 0.75rem;
    padding: 0 var(--cds-sp-03);
    height: 1.5rem;
    display: inline-flex; align-items: center;
    border-radius: 0.9375rem;
    font-weight: 500;
    letter-spacing: 0.16px;
    white-space: nowrap;
  }
  .badge.idle    { background: var(--cds-layer-accent);    color: var(--cds-text-secondary); }
  .badge.running { background: var(--cds-support-info-bg);    color: var(--cds-link-primary); }
  .badge.done    { background: var(--cds-support-success-bg); color: var(--cds-support-success); }
  .badge.error   { background: var(--cds-support-error-bg);   color: var(--cds-support-error); }

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
    padding: var(--cds-sp-03) var(--cds-sp-05);
    border-bottom: 1px solid var(--cds-border-subtle);
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--cds-text-secondary);
    letter-spacing: 0.32px;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    background: var(--cds-layer-accent);
    height: 2.5rem;
  }
  .panel-body {
    padding: var(--cds-sp-05);
    overflow-y: auto;
    flex: 1;
  }

  /* Left input panel */
  textarea#q {
    width: 100%;
    min-height: 110px;
    resize: vertical;
    background: var(--cds-field-01);
    color: var(--cds-text-primary);
    border: none;
    border-bottom: 1px solid var(--cds-border-strong);
    padding: var(--cds-sp-04) var(--cds-sp-05);
    font-family: var(--cds-font-sans);
    font-size: 0.875rem;
    line-height: 1.43;
    letter-spacing: 0.16px;
  }
  textarea#q::placeholder { color: var(--cds-text-placeholder); }
  textarea#q:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; }

  .budget-row {
    margin-top: var(--cds-sp-05);
    display: flex;
    align-items: center;
    gap: var(--cds-sp-04);
  }
  .budget-row label {
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--cds-text-secondary);
    letter-spacing: 0.32px;
  }
  input[type=range] {
    flex: 1;
    accent-color: var(--cds-interactive);
  }
  #budgetVal {
    font-family: var(--cds-font-mono);
    font-size: 0.875rem;
    color: var(--cds-text-primary);
    font-weight: 600;
    min-width: 28px;
    text-align: right;
  }

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
    margin-top: var(--cds-sp-05);
    text-align: left;
    transition: background var(--cds-dur-mod) var(--cds-ease-productive);
  }
  button#run:hover  { background: var(--cds-button-primary-hover); }
  button#run:active { background: var(--cds-button-primary-active); }
  button#run:focus-visible, button#run:focus {
    outline: 2px solid var(--cds-focus);
    outline-offset: -2px;
    box-shadow: inset 0 0 0 1px var(--cds-focus-inset);
  }
  button#run:disabled { background: var(--cds-layer-accent); color: var(--cds-text-placeholder); cursor: wait; box-shadow: none; }

  .examples {
    margin-top: var(--cds-sp-06);
    border-top: 1px solid var(--cds-border-subtle);
    padding-top: var(--cds-sp-04);
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

  /* Budget meter */
  .meter {
    margin-top: var(--cds-sp-06);
    padding: var(--cds-sp-04);
    background: var(--cds-layer-02);
    border: 1px solid var(--cds-border-subtle);
  }
  .meter-row {
    display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: var(--cds-sp-03);
  }
  .meter-label { font-size: 0.75rem; font-weight: 600; color: var(--cds-text-secondary); letter-spacing: 0.32px; }
  .meter-vals  { font-family: var(--cds-font-mono); font-size: 0.8125rem; color: var(--cds-text-primary); }
  .meter-bar {
    height: 8px; background: var(--cds-layer-accent); overflow: hidden;
  }
  .meter-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--cds-support-success), var(--cds-support-warning) 70%, var(--cds-support-error));
    transition: width .3s ease;
    width: 0%;
  }

  /* Right side: vertical stack of three sections */
  .right {
    display: grid;
    grid-template-rows: minmax(0, 0.95fr) minmax(0, 1fr) minmax(0, 1.3fr);
    gap: var(--cds-sp-05);
    overflow: hidden;
  }

  /* Plan panel */
  .plan-version-pill {
    display: inline-block;
    padding: 1px var(--cds-sp-03);
    border-radius: 0.9375rem;
    background: var(--cds-support-info-bg);
    color: var(--cds-link-primary);
    font-size: 0.625rem;
    font-weight: 600;
    letter-spacing: 0.16px;
    margin-left: var(--cds-sp-03);
    vertical-align: middle;
  }
  .plan-card {
    border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-04);
    margin-bottom: var(--cds-sp-04);
    background: var(--cds-layer-02);
  }
  .plan-card.current {
    border-color: var(--cds-interactive);
    box-shadow: 0 0 0 1px var(--cds-interactive) inset;
  }
  .plan-card-meta {
    font-size: 0.6875rem;
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

  /* Tool call log */
  .tool-call {
    border-left: 3px solid var(--cds-border-strong);
    padding: var(--cds-sp-03) var(--cds-sp-04);
    margin-bottom: var(--cds-sp-03);
    background: var(--cds-layer-02);
    font-size: 0.75rem;
  }
  .tool-call.plan   { border-left-color: var(--cds-interactive); }
  .tool-call.web    { border-left-color: var(--cds-support-info); }
  .tool-call.acad   { border-left-color: #8a3ffc; }
  .tool-call.encyc  { border-left-color: var(--cds-support-success); }
  .tool-call.error  { border-left-color: var(--cds-support-error); }
  .tool-call .tname {
    font-family: var(--cds-font-mono);
    font-weight: 600;
    color: var(--cds-text-primary);
  }
  .tool-call .targs {
    font-family: var(--cds-font-mono);
    color: var(--cds-text-secondary);
    font-size: 0.6875rem;
    margin-top: 2px;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .tool-call .tprev {
    color: var(--cds-text-helper);
    font-size: 0.6875rem;
    margin-top: var(--cds-sp-02);
    font-style: italic;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .tool-call .pill {
    display: inline-block;
    padding: 0 var(--cds-sp-03);
    border-radius: 0.9375rem;
    background: var(--cds-layer-accent);
    color: var(--cds-text-secondary);
    font-size: 0.625rem;
    font-weight: 600;
    margin-left: var(--cds-sp-03);
    vertical-align: middle;
  }

  /* Brief */
  .brief-body {
    font-size: 0.875rem;
    line-height: 1.65;
    color: var(--cds-text-primary);
  }
  .brief-body h1, .brief-body h2, .brief-body h3 {
    color: var(--cds-text-primary);
    margin: var(--cds-sp-06) 0 var(--cds-sp-03);
    font-weight: 600;
  }
  .brief-body h3 { font-size: 0.9375rem; }
  .brief-body ul { padding-left: var(--cds-sp-06); }
  .brief-body li { margin-bottom: var(--cds-sp-02); }
  .brief-body a { color: var(--cds-link-primary); text-decoration: none; }
  .brief-body a:hover { color: var(--cds-link-hover); text-decoration: underline; }
  .brief-body strong { color: var(--cds-text-primary); font-weight: 600; }
  .brief-body code {
    background: var(--cds-layer-accent); color: var(--cds-link-primary);
    padding: 1px var(--cds-sp-03);
    font-family: var(--cds-font-mono);
    font-size: 0.8125rem;
  }

  .placeholder {
    color: var(--cds-text-placeholder);
    font-style: italic;
    font-size: 0.8125rem;
    text-align: center;
    padding: var(--cds-sp-06);
  }
  .footer-note {
    padding: var(--cds-sp-03) var(--cds-sp-05);
    font-size: 0.75rem;
    color: var(--cds-text-helper);
    text-align: center;
    border-top: 1px solid var(--cds-border-subtle);
    background: var(--cds-layer-01);
  }
  .panel-header .meta {
    margin-left: var(--cds-sp-03); color: var(--cds-text-helper);
    font-weight: 400; text-transform: none; letter-spacing: 0;
  }
  .panel-header .count {
    color: var(--cds-text-helper); font-weight: 400; text-transform: none; letter-spacing: 0;
  }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name">
    <span class="cds-header__prefix">IBM</span>&nbsp;Brief&nbsp;Budget
  </div>
  <div class="cds-header__actions">
    <span class="cds-helper-01">research brief on a hard tool-call budget · the planner is the demo</span>
    <span id="status" class="badge idle">idle</span>
  </div>
</header>

<main>
  <!-- Left: input -->
  <section class="panel">
    <div class="panel-header">Ask</div>
    <div class="panel-body">
      <textarea id="q" placeholder="A research question for the brief — e.g. 'What's the state of MoE architectures in LLMs?'"></textarea>

      <div class="budget-row">
        <label for="budget">Budget</label>
        <input id="budget" type="range" min="5" max="40" value="15" step="1">
        <span id="budgetVal">15</span>
        <span style="font-size:0.75rem;color:var(--cds-text-helper);">tool calls</span>
      </div>

      <button id="run">Generate brief</button>

      <div class="meter">
        <div class="meter-row">
          <span class="meter-label">Budget used</span>
          <span class="meter-vals" id="meterText">— / —</span>
        </div>
        <div class="meter-bar"><div class="meter-fill" id="meterFill"></div></div>
      </div>

      <div class="examples">
        <div class="examples-label">Try one</div>
        <div class="chips">
          <span class="chip">What's the state of MoE architectures in LLMs?</span>
          <span class="chip">Compare RAG benchmarks 2025–2026 (BEIR, BERGEN, etc.)</span>
          <span class="chip">Open problems in agent observability</span>
          <span class="chip">Recent advances in LoRA fine-tuning of code models</span>
          <span class="chip">How are AI agents being applied to bug triage?</span>
        </div>
      </div>
    </div>
  </section>

  <!-- Right: plan + tool log + brief stacked -->
  <div class="right">

    <section class="panel">
      <div class="panel-header">
        Plan <span class="meta">— what the agent decided to do</span>
        <span style="flex:1"></span>
        <span id="planCount" class="count">no plan yet</span>
      </div>
      <div class="panel-body" id="planBody">
        <div class="placeholder">The agent's plan will appear here as soon as it calls <code>propose_plan</code>.</div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">
        Tool calls <span class="meta">— each call costs 1 from the budget</span>
        <span style="flex:1"></span>
        <span id="callCount" class="count">0 calls</span>
      </div>
      <div class="panel-body" id="logBody">
        <div class="placeholder">Tool calls will stream here as the agent executes its plan.</div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">Brief</div>
      <div class="panel-body" id="briefBody">
        <div class="placeholder">The synthesized brief will appear here when the agent finishes.</div>
      </div>
    </section>
  </div>
</main>

<div class="footer-note">
  Plan + tool calls stream live via SSE. The system prompt is goal-shaped: the agent picks its own sub-topics and tool mix.
</div>

<script>
  const qEl       = document.getElementById('q');
  const budgetEl  = document.getElementById('budget');
  const budgetVal = document.getElementById('budgetVal');
  const runBtn    = document.getElementById('run');
  const status    = document.getElementById('status');
  const meterText = document.getElementById('meterText');
  const meterFill = document.getElementById('meterFill');
  const planBody  = document.getElementById('planBody');
  const planCount = document.getElementById('planCount');
  const logBody   = document.getElementById('logBody');
  const callCount = document.getElementById('callCount');
  const briefBody = document.getElementById('briefBody');

  budgetEl.addEventListener('input', () => { budgetVal.textContent = budgetEl.value; });
  document.querySelectorAll('.chip').forEach(c =>
    c.addEventListener('click', () => { qEl.value = c.textContent; qEl.focus(); })
  );

  let totalBudget = 0;
  let usedSoFar = 0;
  let planVersion = 0;
  let callsLogged = 0;

  function setStatus(label, cls) {
    status.textContent = label;
    status.className = 'badge ' + cls;
  }

  function updateMeter() {
    if (!totalBudget) {
      meterText.textContent = '— / —';
      meterFill.style.width = '0%';
      return;
    }
    meterText.textContent = `${usedSoFar} / ${totalBudget}`;
    meterFill.style.width = `${Math.min(100, (usedSoFar / totalBudget) * 100)}%`;
  }

  function classifyTool(name) {
    if (name === 'propose_plan') return 'plan';
    if (name.startsWith('search_arxiv') || name.startsWith('get_arxiv') ||
        name.startsWith('search_semantic_scholar') || name.startsWith('get_paper_references')) return 'acad';
    if (name.startsWith('search_wikipedia') || name.startsWith('get_wikipedia') ||
        name.startsWith('get_article') || name.startsWith('get_related')) return 'encyc';
    return 'web';
  }

  function clearPlaceholders() {
    [planBody, logBody, briefBody].forEach(el => {
      const p = el.querySelector('.placeholder');
      if (p) p.remove();
    });
  }

  function addPlan(plan, version, used, remaining) {
    clearPlaceholders();
    // Mark previous as not current
    planBody.querySelectorAll('.plan-card.current').forEach(el => el.classList.remove('current'));
    const card = document.createElement('div');
    card.className = 'plan-card current';
    const meta = document.createElement('div');
    meta.className = 'plan-card-meta';
    meta.innerHTML = `<span>v${version} · proposed at ${used} / ${totalBudget} used</span><span>${remaining} calls remaining</span>`;
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
    callsLogged++;
    callCount.textContent = `${callsLogged} call${callsLogged === 1 ? '' : 's'}`;
    const div = document.createElement('div');
    div.className = 'tool-call ' + classifyTool(ev.tool);
    const argStr = JSON.stringify(ev.args, null, 0).slice(0, 250);
    div.innerHTML = `
      <div><span class="tname">${ev.tool}</span><span class="pill">${ev.used}/${totalBudget}</span></div>
      <div class="targs">${escapeHtml(argStr)}</div>
    `;
    logBody.prepend(div);
  }

  function annotateLastToolCall(ev) {
    // Find the most recent .tool-call matching ev.tool
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

  function setBrief(markdown) {
    clearPlaceholders();
    briefBody.innerHTML = `<div class="brief-body">${markdownToHtml(markdown)}</div>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, ch => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    })[ch]);
  }

  // Tiny markdown renderer — handles headings, bold, italic, lists, links, paragraphs
  function markdownToHtml(md) {
    if (!md) return '';
    let out = escapeHtml(md);
    out = out.replace(/^### (.*)$/gm, '<h3>$1</h3>');
    out = out.replace(/^## (.*)$/gm, '<h2>$1</h2>');
    out = out.replace(/^# (.*)$/gm, '<h1>$1</h1>');
    out = out.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    out = out.replace(/\*(.+?)\*/g, '<em>$1</em>');
    out = out.replace(/`([^`]+?)`/g, '<code>$1</code>');
    out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    // Lists: convert runs of "- " lines into <ul>
    out = out.replace(/(?:^|\n)((?:- .*(?:\n|$))+)/g, (_m, block) => {
      const items = block.trim().split('\n').map(l => l.replace(/^- /, '').trim());
      return '\n<ul>' + items.map(i => `<li>${i}</li>`).join('') + '</ul>';
    });
    // Paragraphs: split by blank line, wrap non-block lines
    out = out.split(/\n\n+/).map(block => {
      if (/^<(h\d|ul|ol|pre|blockquote)/i.test(block.trim())) return block;
      return `<p>${block.replace(/\n/g, '<br>')}</p>`;
    }).join('\n');
    return out;
  }

  async function run() {
    const question = qEl.value.trim();
    if (!question) return;
    const budget = parseInt(budgetEl.value, 10);

    runBtn.disabled = true;
    setStatus('starting…', 'running');
    totalBudget = budget;
    usedSoFar = 0;
    planVersion = 0;
    callsLogged = 0;
    planBody.innerHTML = '<div class="placeholder">Waiting for plan…</div>';
    logBody.innerHTML  = '<div class="placeholder">Waiting for tool calls…</div>';
    briefBody.innerHTML = '<div class="placeholder">Brief will appear when synthesis finishes…</div>';
    planCount.textContent = 'no plan yet';
    callCount.textContent = '0 calls';
    updateMeter();

    let resp;
    try {
      resp = await fetch('/api/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({question, budget})
      });
    } catch (e) {
      setStatus('network error', 'error');
      runBtn.disabled = false;
      return;
    }
    const j = await resp.json();
    if (j.error || !j.session_id) {
      setStatus('error', 'error');
      briefBody.innerHTML = `<div class="placeholder" style="color:var(--cds-support-error)">${escapeHtml(j.error || 'unknown error')}</div>`;
      runBtn.disabled = false;
      return;
    }
    setStatus('running…', 'running');

    const sse = new EventSource(`/api/stream/${j.session_id}`);
    sse.onmessage = (e) => {
      let ev;
      try { ev = JSON.parse(e.data); } catch (_) { return; }
      switch (ev.type) {
        case 'init':
          totalBudget = ev.budget;
          updateMeter();
          break;
        case 'plan':
          addPlan(ev.plan, ev.version, ev.used, ev.remaining);
          break;
        case 'tool_call':
          usedSoFar = ev.used;
          updateMeter();
          addToolCall(ev);
          break;
        case 'tool_result':
          annotateLastToolCall(ev);
          break;
        case 'budget_exhausted':
          setStatus('budget exhausted', 'error');
          break;
        case 'brief':
          setBrief(ev.brief);
          break;
        case 'error':
          setStatus('error', 'error');
          briefBody.innerHTML = `<div class="placeholder" style="color:var(--cds-support-error)">${escapeHtml(ev.error)}</div>`;
          break;
        case 'done':
          if (ev.status === 'done') setStatus(`done · ${ev.used}/${ev.budget} used`, 'done');
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
  qEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) run();
  });
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("Brief Budget")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
