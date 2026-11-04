"""
HTML UI for Dependency Drift Watcher.
Exported as _HTML — a single self-contained string served by the FastAPI root endpoint.

Carbonized via the shared `_carbon` foundation. Layout: left rail (watch packs,
scan, status, policies), centre chat, right panel with three tabs — Why (policy
decisions, sources, run receipt for the last answer), Findings, Approvals.
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  html, body { height: 100%; }
  body { background: var(--cds-background); display: flex; flex-direction: column; }

  .app-intro {
    display: flex; align-items: center; gap: var(--cds-sp-05); flex-wrap: wrap;
    padding: var(--cds-sp-04) var(--cds-sp-06);
    background: var(--cds-layer-01); border-bottom: 1px solid var(--cds-border-subtle);
  }
  .app-intro__blurb { font-size: 0.8125rem; color: var(--cds-text-secondary); line-height: 1.5; max-width: 52rem; }
  .app-intro__blurb strong { color: var(--cds-text-primary); font-weight: 600; }
  .app-intro__tools { margin-left: auto; display: flex; flex-wrap: wrap; gap: var(--cds-sp-03); align-items: center; }
  .tools-label { font-size: 0.625rem; text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-helper); }
  .tool-pill {
    font-size: 0.6875rem; color: var(--cds-text-secondary); background: var(--cds-layer-accent);
    border: 1px solid var(--cds-border-subtle); border-radius: 0.9375rem;
    padding: var(--cds-sp-01) var(--cds-sp-04); white-space: nowrap;
  }
  .tool-pill.tav { border-color: #0f62fe55; }

  main { display: grid; grid-template-columns: 220px minmax(0, 1fr) 400px; flex: 1; min-height: 0; overflow: hidden; }
  @media (max-width: 1100px) { main { grid-template-columns: 200px minmax(0, 1fr); } .side { grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--cds-border-subtle); } }
  @media (max-width: 720px)  { main { grid-template-columns: 1fr; overflow: visible; } .rail { border-right: 0; border-bottom: 1px solid var(--cds-border-subtle); } }

  .label { font-size: 0.6875rem; text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-secondary); font-weight: 600; }

  /* Left rail */
  .rail { border-right: 1px solid var(--cds-border-subtle); background: var(--cds-layer-01); padding: var(--cds-sp-05); display: flex; flex-direction: column; gap: var(--cds-sp-06); overflow-y: auto; }
  .packs { display: flex; flex-direction: column; gap: var(--cds-sp-02); }
  .pack { text-align: left; background: transparent; border: 1px solid transparent; padding: var(--cds-sp-03) var(--cds-sp-04); cursor: pointer; font: inherit; color: var(--cds-text-primary); }
  .pack:hover { background: var(--cds-layer-hover); }
  .pack.on { background: var(--cds-layer-accent); border-left: 3px solid var(--cds-interactive); font-weight: 600; }
  .pack small { display: block; font-weight: 400; color: var(--cds-text-helper); font-size: 0.6875rem; line-height: 1.4; margin-top: 2px; }
  .rail .cds-btn { width: 100%; }
  .kv { font-size: 0.75rem; color: var(--cds-text-secondary); display: grid; gap: var(--cds-sp-02); }
  .kv b { color: var(--cds-text-primary); font-weight: 500; }
  .policy-list { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--cds-sp-02); font-size: 0.75rem; color: var(--cds-text-secondary); }
  .policy-list li::before { content: "◆ "; color: var(--cds-interactive); }

  /* Chat */
  .chat { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
  .chips { display: flex; flex-wrap: wrap; gap: var(--cds-sp-03); padding: var(--cds-sp-05) var(--cds-sp-06) 0; }
  .chip { font-size: 0.75rem; padding: var(--cds-sp-02) var(--cds-sp-04); background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle); cursor: pointer; }
  .chip:hover { border-color: var(--cds-interactive); color: var(--cds-link-primary); }
  .messages { flex: 1; overflow-y: auto; padding: var(--cds-sp-05) var(--cds-sp-06); display: flex; flex-direction: column; gap: var(--cds-sp-04); }
  .msg { max-width: 92%; padding: var(--cds-sp-04) var(--cds-sp-05); font-size: 0.875rem; line-height: 1.6; word-break: break-word; }
  .msg.user { align-self: flex-end; background: var(--cds-interactive); color: var(--cds-text-on-color); }
  .msg.agent { align-self: flex-start; background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle); }
  .msg.thinking { align-self: flex-start; color: var(--cds-text-helper); font-style: italic; }
  .msg.error { align-self: flex-start; background: var(--cds-support-error-bg); color: var(--cds-text-primary); border-left: 3px solid var(--cds-support-error); }
  .msg .pack-tag { display: inline-block; font-size: 0.625rem; text-transform: uppercase; letter-spacing: 0.32px; opacity: .8; margin-bottom: 2px; }
  .input-row { display: flex; gap: 0; padding: var(--cds-sp-04) var(--cds-sp-06); border-top: 1px solid var(--cds-border-subtle); background: var(--cds-layer-01); }
  .input-row input { flex: 1; min-width: 0; background: var(--cds-field-01); border: 0; border-bottom: 1px solid var(--cds-border-strong); min-height: 3rem; padding: 0 var(--cds-sp-05); font: inherit; font-size: 0.875rem; color: var(--cds-text-primary); }
  .input-row input:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; }

  /* Right panel */
  .side { border-left: 1px solid var(--cds-border-subtle); display: flex; flex-direction: column; min-height: 0; overflow: hidden; background: var(--cds-background); }
  .tabs { display: flex; border-bottom: 1px solid var(--cds-border-subtle); background: var(--cds-layer-01); }
  .tab { flex: 1; background: transparent; border: 0; border-bottom: 2px solid transparent; padding: var(--cds-sp-04); font: inherit; font-size: 0.8125rem; cursor: pointer; color: var(--cds-text-secondary); }
  .tab.on { border-bottom-color: var(--cds-interactive); color: var(--cds-text-primary); font-weight: 600; }
  .tab .n { font-family: var(--cds-font-mono); font-size: 0.6875rem; margin-left: 4px; color: var(--cds-text-helper); }
  .pane { flex: 1; overflow-y: auto; padding: var(--cds-sp-05); display: none; }
  .pane.on { display: flex; flex-direction: column; gap: var(--cds-sp-05); }
  .empty { color: var(--cds-text-placeholder); font-size: 0.8125rem; line-height: 1.6; }
  .card { background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle); padding: var(--cds-sp-04); display: grid; gap: var(--cds-sp-02); font-size: 0.8125rem; }
  .card .k { font-family: var(--cds-font-mono); font-size: 0.6875rem; color: var(--cds-link-primary); }
  .card .muted { color: var(--cds-text-secondary); }
  .card.blocked { border-left: 3px solid var(--cds-support-error); }
  .card.applied { border-left: 3px solid var(--cds-support-warning); }
  .sources { display: grid; gap: var(--cds-sp-02); font-family: var(--cds-font-mono); font-size: 0.6875rem; overflow-wrap: anywhere; }
  .rcpt { display: grid; grid-template-columns: 1fr auto; gap: var(--cds-sp-02) var(--cds-sp-04); font-size: 0.8125rem; font-variant-numeric: tabular-nums; }
  .rcpt dt { color: var(--cds-text-secondary); } .rcpt dd { margin: 0; font-family: var(--cds-font-mono); text-align: right; }
  .sev { display: inline-block; font-size: 0.6875rem; font-weight: 600; padding: 1px 8px; border-radius: 1rem; }
  .sev.critical { background: var(--cds-support-error-bg); color: var(--cds-support-error); }
  .sev.review { background: var(--cds-support-warning-bg); color: #8e6a00; }
  .sev.fyi { background: var(--cds-support-info-bg); color: var(--cds-support-info); }
  .sev.none { background: var(--cds-support-success-bg); color: var(--cds-support-success); }
  .finding .dep { font-family: var(--cds-font-mono); font-weight: 600; }
  .finding .quote { font-style: italic; color: var(--cds-text-secondary); }
  .finding .acts, .proposal .acts { display: flex; gap: var(--cds-sp-03); flex-wrap: wrap; margin-top: var(--cds-sp-02); }
  .linkbtn { background: none; border: 0; color: var(--cds-link-primary); cursor: pointer; font: inherit; font-size: 0.75rem; padding: 0; }
  .proposal pre { margin: 0; font-family: var(--cds-font-mono); font-size: 0.6875rem; background: var(--cds-layer-accent); padding: var(--cds-sp-03); overflow-x: auto; white-space: pre; }
  .proposal.pending { border-left: 3px solid var(--cds-support-warning); }
  .status-pill { font-size: 0.6875rem; font-family: var(--cds-font-mono); }

  .status-badge { display: flex; align-items: center; gap: var(--cds-sp-03); }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--cds-support-success); }
  .status-dot.busy { background: var(--cds-interactive); animation: pulse 1.2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
  @media (prefers-reduced-motion: reduce) { .status-dot.busy { animation: none; } }

  .md-table { border-collapse: collapse; margin: var(--cds-sp-03) 0; font-size: 0.8125rem; max-width: 100%; display: block; overflow-x: auto; }
  .md-table th, .md-table td { border: 1px solid var(--cds-border-subtle); padding: var(--cds-sp-02) var(--cds-sp-03); text-align: left; vertical-align: top; }
  .md-table th { background: var(--cds-layer-accent); font-weight: 600; }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Dependency&nbsp;Drift&nbsp;Watcher</div>
  <div class="cds-header__actions status-badge">
    <div class="status-dot" id="statusDot"></div>
    <span id="statusText" class="cds-helper-01">Ready</span>
  </div>
</header>

<div class="app-intro">
  <div class="app-intro__blurb">
    <strong>Our code stays still. Its dependencies don't.</strong>
    The agent inventories the models and packages our apps use, checks official sources for what changed,
    and drafts the fix. Every claim is quoted and linked; nothing changes until you approve it.
  </div>
  <div class="app-intro__tools">
    <span class="tools-label">Tools</span>
    <span class="tool-pill tav">Tavily MCP · search · extract · map · crawl · research</span>
    <span class="tool-pill">GitHub MCP · releases · PRs</span>
    <span class="tool-pill">Repo inventory</span>
    <span class="tool-pill">CUGA policies</span>
  </div>
</div>

<main>
  <aside class="rail">
    <div>
      <div class="label">Watch packs</div>
      <div class="packs" id="packs"></div>
    </div>
    <button class="cds-btn" id="scanBtn" onclick="runScan()">Scan this pack</button>
    <div>
      <div class="label">Connections</div>
      <div class="kv" id="conn"><span>Loading…</span></div>
    </div>
    <div>
      <div class="label">CUGA policies</div>
      <ul class="policy-list" id="policies"><li>Registered on first question</li></ul>
      <div class="kv" style="margin-top:6px"><span>Plus code guards on every Tavily call: egress (no secrets or internal names) and official domains only.</span></div>
    </div>
  </aside>

  <section class="chat">
    <div class="chips" id="chips"></div>
    <div class="messages" id="messages"></div>
    <div class="input-row">
      <input type="text" id="userInput" placeholder="Ask what drifted, or about a model or package…"
             onkeydown="if(event.key==='Enter') sendMessage()" />
      <button class="cds-btn" id="sendBtn" onclick="sendMessage()">Ask</button>
    </div>
  </section>

  <aside class="side">
    <div class="tabs" role="tablist">
      <button class="tab on" data-pane="why" onclick="showTab('why')">Why</button>
      <button class="tab" data-pane="findings" onclick="showTab('findings')">Findings<span class="n" id="nFindings"></span></button>
      <button class="tab" data-pane="approvals" onclick="showTab('approvals')">Approvals<span class="n" id="nApprovals"></span></button>
    </div>
    <div class="pane on" id="pane-why">
      <p class="empty">Ask a question or run a scan. This panel shows which policies fired, the sources the agent read, and what the run cost.</p>
    </div>
    <div class="pane" id="pane-findings"><p class="empty">No findings yet.</p></div>
    <div class="pane" id="pane-approvals"><p class="empty">No fixes waiting. When the agent drafts one, it appears here for you to approve or reject.</p></div>
  </aside>
</main>

<script>
  let PACKS = [];
  let currentPack = 'models';
  const $ = id => document.getElementById(id);

  function escHtml(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Minimal, safe markdown → HTML (escapes first, then formats).
  function mdToHtml(text) {
    return mdTables(escHtml(text)
      .replace(/```[\s\S]*?```/g, m => '<pre style="white-space:pre-wrap;background:var(--cds-layer-accent);padding:8px;overflow:auto">' + m.replace(/```\w*/g, '') + '</pre>')
      .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>')
      .replace(/^\s*#{1,6}\s+(.+)$/gm, '<strong>$1</strong>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+?)`/g, '<code style="background:var(--cds-layer-accent);padding:1px 5px">$1</code>')
      .replace(/^\s*[-*]\s+(.+)$/gm, '&nbsp;&nbsp;• $1'))
      .replace(/\n/g, '<br>');
  }
  function mdTables(html) {
    const splitRow = row => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());
    return html.split(/(<pre[\s\S]*?<\/pre>)/).map((part, i) => i % 2 ? part :
      part.replace(/^[ \t]*\|.*\|[ \t]*\n[ \t]*\|[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|[ \t]*(?:\n[ \t]*\|.*\|[ \t]*)*$\n?/gm, block => {
        const [head, , ...body] = block.replace(/\n$/, '').split('\n');
        const th = splitRow(head).map(c => '<th>' + c + '</th>').join('');
        const trs = body.map(r => '<tr>' + splitRow(r).map(c => '<td>' + c + '</td>').join('') + '</tr>').join('');
        return '<table class="md-table"><thead><tr>' + th + '</tr></thead><tbody>' + trs + '</tbody></table>';
      })).join('');
  }

  function setBusy(busy, label) {
    $('statusDot').className = 'status-dot' + (busy ? ' busy' : '');
    $('statusText').textContent = label;
    $('sendBtn').disabled = busy; $('scanBtn').disabled = busy;
  }

  function addMessage(text, cls, packTitle) {
    const div = document.createElement('div');
    div.className = 'msg ' + cls;
    if (cls === 'agent') div.innerHTML = (packTitle ? '<span class="pack-tag">' + escHtml(packTitle) + ' pack</span><br>' : '') + mdToHtml(text);
    else div.textContent = text;
    $('messages').appendChild(div);
    $('messages').scrollTop = $('messages').scrollHeight;
    return div;
  }

  function showTab(name) {
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.dataset.pane === name));
    document.querySelectorAll('.pane').forEach(p => p.classList.toggle('on', p.id === 'pane-' + name));
  }

  function renderPacks() {
    $('packs').innerHTML = PACKS.map(p =>
      '<button class="pack' + (p.id === currentPack ? ' on' : '') + '" onclick="selectPack(\'' + p.id + '\')">'
      + escHtml(p.title) + '<small>' + escHtml(p.summary) + '</small></button>').join('');
    const pack = PACKS.find(p => p.id === currentPack);
    $('chips').innerHTML = (pack ? pack.examples : []).map(e =>
      '<div class="chip" onclick="sendChip(this)">' + escHtml(e) + '</div>').join('');
  }
  function selectPack(id) { currentPack = id; renderPacks(); loadFindings(); }

  async function loadStatus() {
    try {
      const s = await (await fetch('/status')).json();
      $('conn').innerHTML =
        '<span>Tavily: <b>' + escHtml(s.tavily) + '</b></span>' +
        '<span>GitHub: <b>' + escHtml(s.github) + '</b></span>' +
        '<span>PR target: <b>' + escHtml(s.pr_target || 'none (diff only)') + '</b></span>' +
        '<span>Model: <b>' + escHtml(s.model || '—') + '</b></span>' +
        (s.scan_every_hours ? '<span>Scan every <b>' + s.scan_every_hours + ' h</b></span>' : '');
      if (s.policies && s.policies.length)
        $('policies').innerHTML = s.policies.map(p => '<li>' + escHtml(p) + '</li>').join('');
    } catch (e) { $('conn').textContent = 'Status unavailable'; }
  }

  function renderWhy(data) {
    const pane = $('pane-why');
    const decisions = data.policy_decisions || [];
    const r = data.receipt || {};
    let html = '<div><div class="label">Policies and guards that fired</div></div>';
    html += decisions.length ? decisions.map(d => {
      const outcome = (d.outcome || '').toLowerCase();
      const cls = outcome.includes('block') ? 'blocked' : (outcome === 'applied' ? 'applied' : '');
      return '<div class="card ' + cls + '"><span class="k">' + escHtml(d.policy_type || 'policy') + ' · ' + escHtml(d.outcome || '') + '</span>'
        + '<b>' + escHtml(d.policy_name || '') + '</b>'
        + (d.reasoning ? '<span class="muted">' + escHtml(d.reasoning) + '</span>' : '') + '</div>';
    }).join('') : '<p class="empty">None for this answer.</p>';
    html += '<div><div class="label">Sources read</div></div>';
    html += (data.sources || []).length
      ? '<div class="sources">' + data.sources.map(u => '<a href="' + escHtml(u) + '" target="_blank" rel="noopener">' + escHtml(u) + '</a>').join('') + '</div>'
      : '<p class="empty">No outside sources for this answer.</p>';
    html += '<div><div class="label">Run receipt</div></div><dl class="rcpt">'
      + row('Tavily calls', r.tavily_calls) + row('GitHub calls', r.github_calls)
      + row('Repo and usage calls', r.internal_calls) + row('LLM calls', r.llm_calls)
      + row('Tokens', r.tokens != null ? Number(r.tokens).toLocaleString() : null)
      + row('Time', r.seconds != null ? r.seconds + ' s' : null) + row('Model', r.model) + '</dl>';
    pane.innerHTML = html;
    function row(k, v) { return v == null || v === '' ? '' : '<dt>' + k + '</dt><dd>' + escHtml(v) + '</dd>'; }
  }

  async function loadFindings() {
    const rows = await (await fetch('/findings?pack=' + encodeURIComponent(currentPack))).json();
    const open = rows.filter(f => f.status === 'open' && f.severity !== 'none').length;
    $('nFindings').textContent = rows.length ? '(' + open + ' open)' : '';
    $('pane-findings').innerHTML = rows.length ? rows.map(f =>
      '<div class="card finding">'
      + '<div><span class="sev ' + escHtml(f.severity) + '">' + escHtml(f.severity) + '</span> <span class="dep">' + escHtml(f.dependency) + '</span>'
      + ' <span class="status-pill">· ' + escHtml(f.status) + '</span></div>'
      + (f.summary ? '<span>' + escHtml(f.summary) + '</span>' : '')
      + (f.quote ? '<span class="quote">“' + escHtml(f.quote) + '”</span>' : '')
      + (f.source_url ? '<a class="k" href="' + escHtml(f.source_url) + '" target="_blank" rel="noopener">' + escHtml(f.source_url) + '</a>' : '')
      + (f.locations && f.locations.length ? '<span class="muted">Where: ' + escHtml(f.locations.join(', ')) + '</span>' : '')
      + (f.recommendation ? '<span class="muted">Do: ' + escHtml(f.recommendation) + '</span>' : '')
      + (f.note ? '<span class="muted">Note: ' + escHtml(f.note) + '</span>' : '')
      + '<div class="acts">'
      + (f.status !== 'accepted' ? '<button class="linkbtn" onclick="decide(\'' + f.id + '\',\'accepted\')">Accept risk</button>' : '')
      + (f.status !== 'resolved' ? '<button class="linkbtn" onclick="decide(\'' + f.id + '\',\'resolved\')">Mark resolved</button>' : '')
      + (f.status !== 'open' ? '<button class="linkbtn" onclick="decide(\'' + f.id + '\',\'open\')">Reopen</button>' : '')
      + '</div></div>').join('') : '<p class="empty">No findings for this pack yet. Run a scan.</p>';
  }

  async function decide(id, decision) {
    let note = '';
    if (decision === 'accepted') {
      const reason = window.prompt ? window.prompt('Why is this risk accepted? (optional)') : '';
      note = reason || '';
    }
    await fetch('/decisions', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ finding_id: id, decision, note }) });
    loadFindings();
  }

  async function loadProposals() {
    const rows = await (await fetch('/proposals')).json();
    const pending = rows.filter(p => p.status === 'pending').length;
    $('nApprovals').textContent = pending ? '(' + pending + ')' : '';
    $('pane-approvals').innerHTML = rows.length ? rows.map(p =>
      '<div class="card proposal ' + escHtml(p.status) + '">'
      + '<span class="k">' + escHtml(p.status) + ' · ' + escHtml(p.file_path) + '</span>'
      + '<b>' + escHtml(p.title) + '</b>'
      + '<span class="muted">' + escHtml(p.rationale) + '</span>'
      + (p.evidence_url ? '<a class="k" href="' + escHtml(p.evidence_url) + '" target="_blank" rel="noopener">' + escHtml(p.evidence_url) + '</a>' : '')
      + '<pre>' + escHtml(p.diff) + '</pre>'
      + (p.status === 'pending'
          ? '<div class="acts"><button class="cds-btn" onclick="decideProposal(\'' + p.id + '\',\'approve\')">Approve</button>'
            + '<button class="cds-btn cds-btn--secondary" onclick="decideProposal(\'' + p.id + '\',\'reject\')">Reject</button></div>'
          : '<span class="muted">' + escHtml(p.note) + (p.pr_url ? ' <a href="' + escHtml(p.pr_url) + '" target="_blank" rel="noopener">Open PR</a>' : '') + '</span>')
      + '</div>').join('') : '<p class="empty">No fixes waiting. When the agent drafts one, it appears here for you to approve or reject.</p>';
  }

  async function decideProposal(id, action) {
    setBusy(true, action === 'approve' ? 'Applying…' : 'Rejecting…');
    try {
      const res = await fetch('/proposals/' + id + '/' + action, { method: 'POST' });
      const d = await res.json();
      if (!res.ok) addMessage('Error: ' + (d.error || res.statusText), 'error');
    } finally { setBusy(false, 'Ready'); loadProposals(); }
  }

  async function run(url, body, label) {
    setBusy(true, 'Checking…');
    const thinking = addMessage(label, 'thinking');
    try {
      const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await res.json();
      thinking.remove();
      if (!res.ok) { addMessage(data.answer || res.statusText, 'error'); return; }
      const pack = PACKS.find(p => p.id === data.pack);
      addMessage(data.answer || '(no answer)', 'agent', pack ? pack.title : '');
      renderWhy(data); showTab('why');
      await loadFindings(); await loadProposals(); loadStatus();
      if ((data.proposals || []).length) showTab('approvals');
    } catch (err) {
      thinking.remove(); addMessage('Network error: ' + err.message, 'error');
    } finally { setBusy(false, 'Ready'); }
  }

  function sendMessage() {
    const q = $('userInput').value.trim();
    if (!q) return;
    $('userInput').value = '';
    addMessage(q, 'user');
    run('/ask', { question: q, pack: currentPack }, 'Inventorying our side, then reading official sources with Tavily…');
  }
  function sendChip(el) { $('userInput').value = el.textContent.trim(); sendMessage(); }
  function runScan() {
    const pack = PACKS.find(p => p.id === currentPack);
    addMessage('Scan the ' + (pack ? pack.title : currentPack) + ' pack', 'user');
    run('/scan', { pack: currentPack }, 'Running a full scan. This can take a minute or two…');
  }

  (async function init() {
    try { PACKS = await (await fetch('/packs')).json(); } catch (e) { PACKS = []; }
    renderPacks(); loadStatus(); loadFindings(); loadProposals();
  })();
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("Dependency Drift Watcher")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
