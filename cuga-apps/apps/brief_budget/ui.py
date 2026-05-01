"""Self-contained dark-themed HTML UI for Brief Budget. SSE-driven."""

_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brief Budget</title>
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
  header h1 {
    margin: 0;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.01em;
  }
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
  .badge.idle    { background: #1e293b;        color: #94a3b8; border-color: #334155;  }
  .badge.running { background: #1e3a8a33;      color: #93c5fd; border-color: #3b82f6;  }
  .badge.done    { background: #064e3b33;      color: #6ee7b7; border-color: #10b981;  }
  .badge.error   { background: #7f1d1d33;      color: #fca5a5; border-color: #ef4444;  }

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

  /* Left input panel */
  textarea#q {
    width: 100%;
    min-height: 110px;
    resize: vertical;
    background: #0f1117;
    color: #e2e8f0;
    border: 1px solid #2d2d4a;
    border-radius: 8px;
    padding: 10px 12px;
    font: inherit;
    font-size: 14px;
  }
  textarea#q:focus { outline: none; border-color: #6366f1; }
  .budget-row {
    margin-top: 14px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .budget-row label {
    font-size: 12px;
    font-weight: 600;
    color: #94a3b8;
  }
  input[type=range] {
    flex: 1;
    accent-color: #6366f1;
  }
  #budgetVal {
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    font-size: 14px;
    color: #fde68a;
    font-weight: 600;
    min-width: 28px;
    text-align: right;
  }
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
    margin-top: 14px;
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

  /* Budget meter */
  .meter {
    margin-top: 18px;
    padding: 12px;
    background: #0f1117;
    border: 1px solid #2d2d4a;
    border-radius: 8px;
  }
  .meter-row {
    display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 6px;
  }
  .meter-label { font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.06em; }
  .meter-vals  { font-family: ui-monospace, "SF Mono", monospace; font-size: 13px; color: #e2e8f0; }
  .meter-bar {
    height: 8px; background: #1e293b; border-radius: 4px; overflow: hidden;
  }
  .meter-fill {
    height: 100%;
    background: linear-gradient(90deg, #10b981, #fbbf24 70%, #ef4444);
    transition: width .3s ease;
    width: 0%;
  }

  /* Right side: vertical stack of three sections */
  .right {
    display: grid;
    grid-template-rows: minmax(0, 0.95fr) minmax(0, 1fr) minmax(0, 1.3fr);
    gap: 14px;
    overflow: hidden;
  }

  /* Plan panel */
  .plan-version-pill {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 999px;
    background: #312e81;
    color: #fde68a;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    margin-left: 8px;
    vertical-align: middle;
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

  /* Tool call log */
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
  .tool-call.acad   { border-left-color: #8b5cf6; }
  .tool-call.encyc  { border-left-color: #10b981; }
  .tool-call.error  { border-left-color: #ef4444; }
  .tool-call .tname {
    font-family: ui-monospace, "SF Mono", monospace;
    font-weight: 700;
    color: #e2e8f0;
  }
  .tool-call .targs {
    font-family: ui-monospace, "SF Mono", monospace;
    color: #94a3b8;
    font-size: 11px;
    margin-top: 2px;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .tool-call .tprev {
    color: #64748b;
    font-size: 11px;
    margin-top: 4px;
    font-style: italic;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .tool-call .pill {
    display: inline-block;
    padding: 0 6px;
    border-radius: 3px;
    background: #1e293b;
    color: #94a3b8;
    font-size: 10px;
    font-weight: 700;
    margin-left: 6px;
    vertical-align: middle;
  }

  /* Brief */
  .brief-body {
    font-size: 14px;
    line-height: 1.65;
    color: #e2e8f0;
  }
  .brief-body h1, .brief-body h2, .brief-body h3 {
    color: #fff;
    margin: 18px 0 8px;
  }
  .brief-body h3 { font-size: 15px; }
  .brief-body ul { padding-left: 22px; }
  .brief-body li { margin-bottom: 4px; }
  .brief-body a { color: #93c5fd; text-decoration: none; }
  .brief-body a:hover { text-decoration: underline; }
  .brief-body strong { color: #fde68a; }
  .brief-body code {
    background: #1e293b; padding: 1px 6px; border-radius: 4px;
    font-size: 12.5px;
  }

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
  <h1>Brief Budget <span class="subtitle">research brief on a hard tool-call budget · the planner is the demo</span></h1>
  <span id="status" class="badge idle">idle</span>
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
        <span style="font-size:11px;color:#64748b;">tool calls</span>
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
        Tool calls <span style="margin-left:8px; color:#64748b; font-weight: 500; text-transform:none; letter-spacing: 0;">— each call costs 1 from the budget</span>
        <span style="flex:1"></span>
        <span id="callCount" style="color:#64748b; font-weight: 500; text-transform: none;">0 calls</span>
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
      briefBody.innerHTML = `<div class="placeholder" style="color:#fca5a5">${escapeHtml(j.error || 'unknown error')}</div>`;
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
          briefBody.innerHTML = `<div class="placeholder" style="color:#fca5a5">${escapeHtml(ev.error)}</div>`;
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
</body>
</html>
"""
