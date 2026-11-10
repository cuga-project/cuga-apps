"""
HTML UI for Web Researcher. Exported as _HTML — one self-contained string.

Carbonized via the shared `_carbon` foundation. Left: the question, research
mode, source controls and watch topics. Right: live progress while a job runs,
then four tabs — Answer, Evidence (each claim with its quote and a verified
badge), Why (policies and guards that fired, sources, run receipt), History.
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  html, body { height: 100%; }
  [hidden] { display: none !important; }
  body { background: var(--cds-background); display: flex; flex-direction: column; }

  .app-intro { display: flex; align-items: center; gap: var(--cds-sp-05); flex-wrap: wrap;
    padding: var(--cds-sp-04) var(--cds-sp-06); background: var(--cds-layer-01);
    border-bottom: 1px solid var(--cds-border-subtle); }
  .app-intro__blurb { font-size: 0.8125rem; color: var(--cds-text-secondary); line-height: 1.5; max-width: 50rem; }
  .app-intro__blurb strong { color: var(--cds-text-primary); font-weight: 600; }
  .app-intro__tools { margin-left: auto; display: flex; flex-wrap: wrap; gap: var(--cds-sp-03); align-items: center; }
  .tools-label { font-size: 0.625rem; text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-helper); }
  .tool-pill { font-size: 0.6875rem; color: var(--cds-text-secondary); background: var(--cds-layer-accent);
    border: 1px solid var(--cds-border-subtle); border-radius: 0.9375rem; padding: var(--cds-sp-01) var(--cds-sp-04); white-space: nowrap; }
  .tool-pill.tav { border-color: #0f62fe66; color: var(--cds-text-primary); }

  main { display: grid; grid-template-columns: 380px minmax(0, 1fr); flex: 1; min-height: 0; overflow: hidden; }
  @media (max-width: 900px) { main { grid-template-columns: 1fr; overflow: visible; } .left { border-right: 0; border-bottom: 1px solid var(--cds-border-subtle); } }

  .label { font-size: 0.6875rem; text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-secondary); font-weight: 600; }
  .left { border-right: 1px solid var(--cds-border-subtle); background: var(--cds-layer-01); overflow-y: auto;
    padding: var(--cds-sp-05); display: flex; flex-direction: column; gap: var(--cds-sp-05); }
  .field { display: grid; gap: var(--cds-sp-02); }
  textarea, input[type=text], input[type=password], select {
    width: 100%; background: var(--cds-field-01); border: 0; border-bottom: 1px solid var(--cds-border-strong);
    padding: var(--cds-sp-03) var(--cds-sp-04); font: inherit; font-size: 0.875rem; color: var(--cds-text-primary); }
  textarea { min-height: 5rem; resize: vertical; line-height: 1.5; }
  textarea:focus, input:focus, select:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; }
  .modes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 2px; }
  .mode { background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle); padding: var(--cds-sp-03);
    font: inherit; font-size: 0.75rem; cursor: pointer; color: var(--cds-text-primary); text-align: left; line-height: 1.3; }
  .mode small { display: block; color: var(--cds-text-helper); font-size: 0.625rem; margin-top: 2px; font-family: var(--cds-font-mono); }
  .mode.on { border-color: var(--cds-interactive); box-shadow: inset 0 0 0 1px var(--cds-interactive); background: var(--cds-layer-accent); font-weight: 600; }
  .mode-help { font-size: 0.75rem; color: var(--cds-text-secondary); line-height: 1.5; }
  .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--cds-sp-03); }
  .check { display: flex; align-items: center; gap: var(--cds-sp-03); font-size: 0.8125rem; color: var(--cds-text-secondary); }
  .go { width: 100%; max-width: none; }
  .chips { display: flex; flex-wrap: wrap; gap: var(--cds-sp-02); }
  .chip { font-size: 0.6875rem; padding: var(--cds-sp-02) var(--cds-sp-03); background: var(--cds-layer-02);
    border: 1px solid var(--cds-border-subtle); cursor: pointer; text-align: left; font-family: inherit; color: var(--cds-text-secondary); }
  .chip:hover { border-color: var(--cds-interactive); color: var(--cds-link-primary); }
  .topic { display: flex; gap: var(--cds-sp-03); align-items: flex-start; padding: var(--cds-sp-03) 0; border-bottom: 1px solid var(--cds-border-subtle); font-size: 0.8125rem; }
  .topic .q { flex: 1; } .topic .meta { font-size: 0.6875rem; color: var(--cds-text-helper); }
  .topic.off { opacity: .5; }
  .linkbtn { background: none; border: 0; color: var(--cds-link-primary); cursor: pointer; font: inherit; font-size: 0.75rem; padding: 0; }
  .warn { border-left: 3px solid var(--cds-support-warning); background: var(--cds-support-warning-bg); padding: var(--cds-sp-03) var(--cds-sp-04); font-size: 0.8125rem; }

  .right { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
  .tabs { display: flex; border-bottom: 1px solid var(--cds-border-subtle); background: var(--cds-layer-01); }
  .tab { background: transparent; border: 0; border-bottom: 2px solid transparent; padding: var(--cds-sp-04) var(--cds-sp-05);
    font: inherit; font-size: 0.8125rem; cursor: pointer; color: var(--cds-text-secondary); }
  .tab.on { border-bottom-color: var(--cds-interactive); color: var(--cds-text-primary); font-weight: 600; }
  .tab .n { font-family: var(--cds-font-mono); font-size: 0.6875rem; margin-left: 4px; color: var(--cds-text-helper); }
  .pane { flex: 1; overflow-y: auto; padding: var(--cds-sp-06); display: none; }
  .pane.on { display: block; }
  .empty { color: var(--cds-text-placeholder); font-size: 0.875rem; line-height: 1.6; max-width: 40rem; }

  .run-head { display: flex; flex-wrap: wrap; gap: var(--cds-sp-03); align-items: center; margin-bottom: var(--cds-sp-04); }
  .tag { font-size: 0.6875rem; font-family: var(--cds-font-mono); padding: 2px 8px; background: var(--cds-layer-accent); border: 1px solid var(--cds-border-subtle); }
  .tag.mode { background: var(--cds-interactive); color: var(--cds-text-on-color); border-color: var(--cds-interactive); }
  .q-title { font-size: 1.125rem; font-weight: 600; margin-bottom: var(--cds-sp-03); line-height: 1.35; }
  .verified-bar { display: flex; align-items: center; gap: var(--cds-sp-04); padding: var(--cds-sp-04); margin-bottom: var(--cds-sp-05);
    border: 1px solid var(--cds-border-subtle); background: var(--cds-layer-01); font-size: 0.875rem; }
  .meter { flex: 1; height: 6px; background: var(--cds-layer-accent); position: relative; max-width: 220px; }
  .meter i { position: absolute; inset: 0 auto 0 0; background: var(--cds-support-success); }
  .answer { font-size: 0.9375rem; line-height: 1.7; max-width: 52rem; }
  .answer a { color: var(--cds-link-primary); }
  .followups { margin-top: var(--cds-sp-06); display: grid; gap: var(--cds-sp-03); }
  .rate { margin-top: var(--cds-sp-06); display: flex; align-items: center; gap: var(--cds-sp-03); font-size: 0.8125rem; color: var(--cds-text-secondary); flex-wrap: wrap; }
  .rate button { font-size: 1rem; background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle); padding: 2px 10px; cursor: pointer; }
  .rate button.on { border-color: var(--cds-interactive); background: var(--cds-layer-accent); }

  .steps { display: grid; gap: var(--cds-sp-02); font-size: 0.8125rem; max-width: 52rem; }
  .step { display: grid; grid-template-columns: 3.5rem 1fr; gap: var(--cds-sp-03); padding: var(--cds-sp-02) 0; border-bottom: 1px dashed var(--cds-border-subtle); }
  .step .t { font-family: var(--cds-font-mono); font-size: 0.6875rem; color: var(--cds-text-helper); }
  .step b { font-weight: 600; }
  .spinner-line { display: flex; gap: var(--cds-sp-03); align-items: center; margin-bottom: var(--cds-sp-04); font-size: 0.875rem; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--cds-interactive); animation: pulse 1.2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .3; } }
  @media (prefers-reduced-motion: reduce) { .dot { animation: none; } }

  .claim { border: 1px solid var(--cds-border-subtle); background: var(--cds-layer-01); padding: var(--cds-sp-04) var(--cds-sp-05);
    margin-bottom: var(--cds-sp-04); display: grid; gap: var(--cds-sp-03); max-width: 52rem; }
  .claim.ok { border-left: 3px solid var(--cds-support-success); }
  .claim.no { border-left: 3px solid var(--cds-support-warning); }
  .claim.drop { border-left: 3px solid var(--cds-support-error); opacity: .85; }
  .badge.drop { background: var(--cds-support-error-bg); color: var(--cds-support-error); }
  .badge { font-size: 0.6875rem; font-weight: 600; padding: 1px 8px; border-radius: 1rem; justify-self: start; }
  .badge.ok { background: var(--cds-support-success-bg); color: var(--cds-support-success); }
  .badge.no { background: var(--cds-support-warning-bg); color: #8e6a00; }
  .claim .text { font-weight: 600; font-size: 0.875rem; }
  .claim blockquote { margin: 0; padding-left: var(--cds-sp-04); border-left: 2px solid var(--cds-border-strong); color: var(--cds-text-secondary); font-style: italic; font-size: 0.8125rem; }
  .claim .src { font-family: var(--cds-font-mono); font-size: 0.6875rem; overflow-wrap: anywhere; }
  .claim .how { font-size: 0.6875rem; color: var(--cds-text-helper); }
  .claim .passage { font-size: 0.8125rem; background: var(--cds-layer-accent); padding: var(--cds-sp-03); }

  .card { background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle); padding: var(--cds-sp-04); display: grid; gap: var(--cds-sp-02); font-size: 0.8125rem; margin-bottom: var(--cds-sp-03); max-width: 52rem; }
  .card .k { font-family: var(--cds-font-mono); font-size: 0.6875rem; color: var(--cds-link-primary); }
  .card.blocked { border-left: 3px solid var(--cds-support-error); }
  .card.applied { border-left: 3px solid var(--cds-support-info); }
  .card.flagged { border-left: 3px solid var(--cds-support-warning); }
  .muted { color: var(--cds-text-secondary); }
  .sources { display: grid; gap: var(--cds-sp-02); font-family: var(--cds-font-mono); font-size: 0.6875rem; overflow-wrap: anywhere; max-width: 52rem; }
  .rcpt { display: grid; grid-template-columns: max-content auto; gap: var(--cds-sp-02) var(--cds-sp-06); font-size: 0.8125rem; font-variant-numeric: tabular-nums; }
  .rcpt dt { color: var(--cds-text-secondary); } .rcpt dd { margin: 0; font-family: var(--cds-font-mono); }
  h3.sec { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-secondary); margin: var(--cds-sp-06) 0 var(--cds-sp-03); }
  h3.sec:first-child { margin-top: 0; }
  .hist { display: grid; grid-template-columns: 1fr auto auto; gap: var(--cds-sp-04); align-items: center; padding: var(--cds-sp-04); border-bottom: 1px solid var(--cds-border-subtle); cursor: pointer; font-size: 0.8125rem; max-width: 60rem; }
  .hist:hover { background: var(--cds-layer-hover); }
  .hist .t { font-weight: 500; }
  .hist .m { font-family: var(--cds-font-mono); font-size: 0.6875rem; color: var(--cds-text-helper); }

  .md-table { border-collapse: collapse; margin: var(--cds-sp-03) 0; font-size: 0.8125rem; display: block; overflow-x: auto; }
  .md-table th, .md-table td { border: 1px solid var(--cds-border-subtle); padding: var(--cds-sp-02) var(--cds-sp-03); text-align: left; vertical-align: top; }
  .md-table th { background: var(--cds-layer-accent); font-weight: 600; }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Web&nbsp;Researcher</div>
  <div class="cds-header__actions"><span class="cds-helper-01" id="hdr-status" style="color:#c6c6c6">Checking Tavily…</span></div>
</header>

<div class="app-intro">
  <div class="app-intro__blurb">
    <strong>Research you can check.</strong> Pick a mode: a researcher agent puts the matching Tavily capability to work, and a verifier agent checks every claim.
    Every claim comes with the exact sentence from its source, and the app checks that sentence is really on the page.
  </div>
  <div class="app-intro__tools">
    <span class="tools-label">Tavily MCP</span>
    <span class="tool-pill tav">search</span><span class="tool-pill tav">extract</span><span class="tool-pill tav">map</span>
    <span class="tool-pill tav">crawl</span><span class="tool-pill tav">research</span>
    <span class="tool-pill">CUGA · researcher + verifier agents</span>
  </div>
</div>

<main>
  <aside class="left">
    <div id="key-warn" class="warn" hidden>TAVILY_API_KEY is not set. Add it below or in build/.env.
      <div class="field" style="margin-top:8px"><input type="password" id="tavily-key" placeholder="tvly-…">
      <button class="cds-btn cds-btn--sm" onclick="saveKey()">Save key</button></div></div>

    <div class="field">
      <label class="label" for="q">Question</label>
      <textarea id="q" placeholder="Ask anything. Paste a URL to study a website."></textarea>
    </div>

    <div class="field">
      <span class="label">Mode</span>
      <div class="modes" id="modes"></div>
      <div class="mode-help" id="mode-help"></div>
    </div>

    <div class="field" id="site-field" hidden>
      <label class="label" for="site">Website</label>
      <input type="text" id="site" placeholder="https://docs.example.com">
    </div>
    <div class="field" id="depth-field" hidden>
      <label class="label" for="depth">Report depth (tavily_research)</label>
      <select id="depth"><option value="mini">mini · narrow questions, ~20 s</option><option value="pro">pro · broad topics, slower</option></select>
    </div>

    <div class="field">
      <span class="label">Sources</span>
      <select id="profile" onchange="syncSources()"></select>
      <div id="custom-field" class="field" hidden>
        <input type="text" id="inc" placeholder="Only these domains, comma-separated">
        <input type="text" id="exc" placeholder="Never these domains, comma-separated">
      </div>
      <div class="row2">
        <select id="tw"><option value="any">Any time</option><option value="day">Past day</option><option value="week">Past week</option><option value="month">Past month</option><option value="year">Past year</option></select>
        <label class="check"><input type="checkbox" id="news"> News only</label>
      </div>
    </div>

    <button class="cds-btn go" id="go" onclick="startResearch()">Research</button>

    <div class="field">
      <span class="label">Try</span>
      <div class="chips" id="examples"></div>
    </div>

    <div class="field">
      <span class="label">Watch topics · only what's new since the last run</span>
      <div id="topics"></div>
      <div class="row2" style="margin-top:6px">
        <input type="text" id="new-topic" placeholder="Topic to watch…">
        <select id="new-schedule"><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="hourly">Hourly</option></select>
      </div>
      <button class="cds-btn cds-btn--sm cds-btn--secondary" onclick="addTopic()">Add watch topic</button>
    </div>

    <div class="field">
      <span class="label">CUGA policies</span>
      <div class="mode-help" id="policies">Registered on the first question.</div>
    </div>
  </aside>

  <section class="right">
    <div class="tabs" role="tablist">
      <button class="tab on" data-pane="answer" onclick="showTab('answer')">Answer</button>
      <button class="tab" data-pane="evidence" onclick="showTab('evidence')">Evidence<span class="n" id="n-ev"></span></button>
      <button class="tab" data-pane="why" onclick="showTab('why')">Why</button>
      <button class="tab" data-pane="history" onclick="showTab('history')">History<span class="n" id="n-hist"></span></button>
    </div>
    <div class="pane on" id="pane-answer"><p class="empty">Ask a question on the left. While the agent works you'll see each Tavily call live; then the answer, every claim's evidence, and what governed the run.</p></div>
    <div class="pane" id="pane-evidence"><p class="empty">Claims and their quotes appear here after a run.</p></div>
    <div class="pane" id="pane-why"><p class="empty">Policies, guards, sources and the run receipt appear here after a run.</p></div>
    <div class="pane" id="pane-history"><p class="empty">No research yet.</p></div>
  </section>
</main>

<script>
const $ = id => document.getElementById(id);
const MODES = [
  ['auto', 'Auto', 'picks for you'], ['quick', 'Quick answer', 'search'], ['deep', 'Deep dive', 'search · extract'],
  ['site', 'Site study', 'map · crawl'], ['report', 'Report', 'research · extract'],
];
const HELP = {
  auto: 'Picks Site study when you paste a URL, Report when you ask for an overview, otherwise Deep dive.',
  quick: 'One or two fast Tavily searches; a short answer quoting the result snippets.',
  deep: 'Advanced searches for each sub-question, then tavily_extract pulls the exact passage from the best pages.',
  site: 'tavily_map lays out the website, tavily_crawl reads the relevant section; answers come only from that site.',
  report: 'tavily_research writes a cited report; the agent then re-reads key sources with tavily_extract to quote them.',
};
const EXAMPLES = {
  auto: ['What changed in the EU AI Act timeline in 2026?', 'https://docs.tavily.com — how does crawl differ from map?'],
  quick: ['Who maintains the Model Context Protocol specification?', 'What is Tavily\'s map endpoint for?'],
  deep: ['How do remote MCP servers handle authentication today?', 'What are the tradeoffs of speculative decoding for LLM serving?'],
  site: ['How does crawl differ from map, and when should I use each?|https://docs.tavily.com', 'What models does IBM watsonx.ai offer and which are deprecated?|https://www.ibm.com/products/watsonx-ai'],
  report: ['State of open-weight LLMs in late 2026: leading models, licenses and benchmarks', 'How are enterprises governing AI agents in 2026? Main approaches and standards'],
};
let mode = 'auto', current = null, poll = null;

function esc(s) { return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function mdToHtml(text) {
  return mdTables(esc(text)
    .replace(/```[\s\S]*?```/g, m => '<pre style="white-space:pre-wrap;background:var(--cds-layer-accent);padding:8px">' + m.replace(/```\w*/g,'') + '</pre>')
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>')
    .replace(/^\s*#{1,6}\s+(.+)$/gm, '<strong>$1</strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+?)`/g, '<code style="background:var(--cds-layer-accent);padding:1px 5px">$1</code>')
    .replace(/^\s*[-*]\s+(.+)$/gm, '&nbsp;&nbsp;• $1')).replace(/\n/g, '<br>');
}
function mdTables(html) {
  const row = r => r.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(c => c.trim());
  return html.split(/(<pre[\s\S]*?<\/pre>)/).map((part, i) => i % 2 ? part :
    part.replace(/^[ \t]*\|.*\|[ \t]*\n[ \t]*\|[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|[ \t]*(?:\n[ \t]*\|.*\|[ \t]*)*$\n?/gm, b => {
      const [h, , ...body] = b.replace(/\n$/,'').split('\n');
      return '<table class="md-table"><thead><tr>' + row(h).map(c => '<th>'+c+'</th>').join('') + '</tr></thead><tbody>'
        + body.map(r => '<tr>' + row(r).map(c => '<td>'+c+'</td>').join('') + '</tr>').join('') + '</tbody></table>';
    })).join('');
}
function showTab(n) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.dataset.pane === n));
  document.querySelectorAll('.pane').forEach(p => p.classList.toggle('on', p.id === 'pane-' + n));
}
async function post(url, body) {
  const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})});
  let d = {}; try { d = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error(d.error || r.statusText);
  return d;
}

function renderModes() {
  $('modes').innerHTML = MODES.map(([id, t, s]) => '<button class="mode' + (id === mode ? ' on' : '') + '" onclick="setMode(\'' + id + '\')">' + t + '<small>' + s + '</small></button>').join('');
  $('mode-help').textContent = HELP[mode];
  $('site-field').hidden = mode !== 'site';
  $('depth-field').hidden = mode !== 'report';
  $('examples').innerHTML = (EXAMPLES[mode] || []).map(e => '<button class="chip" onclick="useExample(this.dataset.e)" data-e="' + esc(e) + '">' + esc(e.split('|')[0]) + '</button>').join('');
}
function setMode(m) { mode = m; renderModes(); }
function useExample(e) {
  const [q, site] = e.split('|');
  $('q').value = q; if (site) $('site').value = site;
  startResearch();
}
function syncSources() { $('custom-field').hidden = $('profile').value !== 'custom'; }

async function loadStatus() {
  try {
    const s = await (await fetch('/status')).json();
    $('hdr-status').textContent = 'Tavily: ' + s.tavily;
    $('key-warn').hidden = !/not set/.test(s.tavily);
    $('profile').innerHTML = Object.entries(s.profiles).map(([k, v]) => '<option value="' + k + '">' + esc(v) + '</option>').join('');
    if (s.policies && s.policies.length) $('policies').innerHTML = s.policies.map(p => '◆ ' + esc(p)).join('<br>');
  } catch (e) { $('hdr-status').textContent = 'Status unavailable'; }
}
async function saveKey() {
  const k = $('tavily-key').value.trim(); if (!k) return;
  await post('/settings/credentials', {tavily_key: k}); $('tavily-key').value = ''; loadStatus();
}

function domains(s) { return (s || '').split(/[,\s]+/).map(x => x.trim()).filter(Boolean); }
async function startResearch() {
  const q = $('q').value.trim(); if (!q) { $('q').focus(); return; }
  const body = {question: q, mode, site_url: mode === 'site' ? $('site').value.trim() : '', profile: $('profile').value || 'web',
    include_domains: domains($('inc').value), exclude_domains: domains($('exc').value), time_window: $('tw').value,
    news: $('news').checked, report_model: $('depth').value};
  $('go').disabled = true; $('go').textContent = 'Researching…';
  try { const job = await post('/research', body); follow(job.id, q); }
  catch (e) { $('go').disabled = false; $('go').textContent = 'Research'; $('pane-answer').innerHTML = '<div class="warn">' + esc(e.message) + '</div>'; showTab('answer'); }
}
function follow(id, q) {
  clearInterval(poll); showTab('answer');
  const tick = async () => {
    let j; try { j = await (await fetch('/jobs/' + id)).json(); } catch (e) { return; }
    if (j.status === 'done' || j.status === 'error') {
      clearInterval(poll); $('go').disabled = false; $('go').textContent = 'Research';
      if (j.status === 'error') { $('pane-answer').innerHTML = '<div class="warn">' + esc(j.error) + '</div>' + stepsHtml(j.steps); return; }
      show(j.result, j.question, j.steps); loadHistory(); loadTopics(); loadStatus(); return;
    }
    $('pane-answer').innerHTML = '<div class="q-title">' + esc(j.question || q) + '</div><div class="spinner-line"><span class="dot"></span>'
      + (j.status === 'queued' && j.ahead ? 'Waiting for ' + j.ahead + ' earlier run(s)…' : 'Researching… ' + Math.round(j.elapsed) + ' s')
      + '</div>' + stepsHtml(j.steps);
  };
  tick(); poll = setInterval(tick, 1500);
}
function stepsHtml(steps) {
  return '<div class="steps">' + (steps || []).map(s => {
    const [head, ...rest] = s.text.split(' · ');
    return '<div class="step"><span class="t">' + s.t + ' s</span><span><b>' + esc(head) + '</b>' + (rest.length ? ' · ' + esc(rest.join(' · ')) : '') + '</span></div>';
  }).join('') + '</div>';
}

function show(r, question, steps) {
  current = r;
  const claims = r.claims || [], ok = claims.filter(c => c.verified).length;
  let h = '<div class="q-title">' + esc(question || r.topic || '') + '</div><div class="run-head"><span class="tag mode">' + esc(r.mode_title || r.mode) + '</span>'
    + '<span class="tag">' + esc(r.rules || '') + '</span>' + (r.receipt ? '<span class="tag">' + (r.receipt.tavily_calls || 0) + ' Tavily calls · ' + (r.receipt.seconds || '?') + ' s</span>' : '') + '</div>';
  if (claims.length) h += '<div class="verified-bar"><b>' + ok + ' of ' + claims.length + '</b> claims verified · quote checked on its page in code, support judged by the verifier agent'
    + '<span class="meter"><i style="width:' + Math.round(100 * ok / claims.length) + '%"></i></span><button class="linkbtn" onclick="showTab(\'evidence\')">See evidence →</button></div>';
  h += '<div class="answer">' + mdToHtml(r.answer || '') + '</div>';
  if ((r.follow_ups || []).length) h += '<div class="followups"><span class="label">Follow up</span>' + r.follow_ups.map(f => '<button class="chip" onclick="followUp(this.dataset.q)" data-q="' + esc(f) + '">' + esc(f) + '</button>').join('') + '</div>';
  if (r.report_id) h += '<div class="rate">Was this useful? <button id="up" onclick="rate(\'up\')">👍</button><button id="down" onclick="rate(\'down\')">👎</button><span id="rate-note">Ratings are saved with the report.</span></div>';
  if (steps && steps.length) h += '<h3 class="sec">How it ran</h3>' + stepsHtml(steps);
  $('pane-answer').innerHTML = h;
  renderEvidence(claims); renderWhy(r);
}
function followUp(q) { $('q').value = q; startResearch(); }

const VERDICT = {
  verified: ['ok', '✓ Verified'], revised: ['ok', '✓ Verified · better passage'], softened: ['ok', '✓ Verified · narrowed'],
  not_verified: ['no', '⚠ Not verified'], dropped: ['drop', '✕ Dropped'],
};
function renderEvidence(claims) {
  $('n-ev').textContent = claims.length ? '(' + claims.filter(c => c.verified).length + '/' + claims.length + ')' : '';
  $('pane-evidence').innerHTML = claims.length ? claims.map((c, i) => {
    const v = VERDICT[c.status] || (c.verified ? VERDICT.verified : VERDICT.not_verified);
    return '<div class="claim ' + v[0] + '" id="claim-' + i + '">'
    + '<span class="badge ' + v[0] + '">' + v[1] + '</span>'
    + '<div class="text">' + esc(c.claim) + '</div>'
    + (c.original_claim && c.original_claim !== c.claim ? '<div class="how">Researcher wrote: “' + esc(c.original_claim) + '”</div>' : '')
    + (c.quote ? '<blockquote>“' + esc(c.quote) + '”</blockquote>' : '')
    + (c.agent_quote && c.agent_quote !== c.quote ? '<div class="how">Researcher\'s quote, replaced: “' + esc(c.agent_quote) + '”</div>' : '')
    + (c.source_url ? '<a class="src" href="' + esc(c.source_url) + '" target="_blank" rel="noopener">' + esc(c.source_url) + '</a>' : '<span class="how">No source URL given</span>')
    + '<span class="how">' + esc((c.by === 'verifier' ? 'Verifier: ' : c.by ? 'Support check: ' : 'Check: ') + (c.checked || '')) + '</span>'
    + (c.contradiction ? '<div class="passage"><span class="label">What the page says instead</span><br>' + esc(c.contradiction) + '</div>' : '')
    + (!c.verified && !c.contradiction && c.passage ? '<div class="passage"><span class="label">Closest passage on the page</span><br>' + esc(c.passage) + '</div>' : '')
    + (c.source_url && c.quote ? '<div><button class="cds-btn cds-btn--sm cds-btn--tertiary" onclick="recheck(' + i + ')">Check again with tavily_extract</button> <span class="how" id="re-' + i + '"></span></div>' : '')
    + '</div>';
  }).join('') : '<p class="empty">This answer listed no claims to check.</p>';
}
async function recheck(i) {
  const c = current.claims[i]; $('re-' + i).textContent = 'Reading the page…';
  try { const d = await post('/verify', {claim: c.claim, quote: c.quote, url: c.source_url});
    $('re-' + i).textContent = (d.verified ? '✓ ' : '⚠ ') + d.note + (d.passage && !d.verified ? ' — “' + d.passage + '”' : '');
  } catch (e) { $('re-' + i).textContent = e.message; }
}
async function rate(v) {
  try { const d = await post('/feedback', {report_id: current.report_id, rating: v});
    $('up').classList.toggle('on', v === 'up'); $('down').classList.toggle('on', v === 'down'); $('rate-note').textContent = d.note;
  } catch (e) { $('rate-note').textContent = e.message; }
}

function renderWhy(r) {
  const d = r.policy_decisions || [], rc = r.receipt || {};
  let h = '<h3 class="sec">Policies and guards that fired</h3>';
  h += d.length ? d.map(x => { const o = (x.outcome || '').toLowerCase();
    const cls = o.includes('block') ? 'blocked' : o === 'flagged' ? 'flagged' : 'applied';
    return '<div class="card ' + cls + '"><span class="k">' + esc(x.policy_type || 'policy') + ' · ' + esc(x.outcome || '') + '</span><b>' + esc(x.policy_name || '') + '</b>'
      + (x.reasoning ? '<span class="muted">' + esc(x.reasoning) + '</span>' : '') + '</div>'; }).join('') : '<p class="empty">None for this run.</p>';
  h += '<h3 class="sec">Sources read</h3>' + ((r.sources || []).length ? '<div class="sources">' + r.sources.map(u => '<a href="' + esc(u) + '" target="_blank" rel="noopener">' + esc(u) + '</a>').join('') + '</div>' : '<p class="empty">No sources.</p>');
  const tools = Object.entries(rc.by_tool || {}).map(([k, v]) => k + ' × ' + v).join(', ');
  h += '<h3 class="sec">Run receipt</h3><dl class="rcpt">' + row('Tavily calls', rc.tavily_calls) + row('By tool', tools) + row('Pages re-read for claim checks', rc.claim_checks) + row('Verifier · Tavily calls', (rc.verifier || {}).tavily_calls) + row('Verifier · LLM calls', (rc.verifier || {}).llm_calls) + row('Verifier · tokens', (rc.verifier || {}).tokens != null ? Number(rc.verifier.tokens).toLocaleString() : null)
    + row('LLM calls', rc.llm_calls) + row('Tokens', rc.tokens != null ? Number(rc.tokens).toLocaleString() : null) + row('Time', rc.seconds != null ? rc.seconds + ' s' : null) + row('Model', rc.model) + '</dl>';
  $('pane-why').innerHTML = h;
  function row(k, v) { return v == null || v === '' ? '' : '<dt>' + k + '</dt><dd>' + esc(v) + '</dd>'; }
}

let HISTORY = [];
async function loadHistory() {
  try { HISTORY = await (await fetch('/reports')).json(); } catch (e) { return; }
  $('n-hist').textContent = HISTORY.length ? '(' + HISTORY.length + ')' : '';
  $('pane-history').innerHTML = HISTORY.length ? HISTORY.map((r, i) => {
    const c = r.claims || [], ok = c.filter(x => x.verified).length;
    return '<div class="hist" onclick="openReport(' + i + ')"><span class="t">' + esc(r.topic) + '</span><span class="m">' + esc(r.mode || r.source)
      + (c.length ? ' · ' + ok + '/' + c.length + ' verified' : '') + '</span><span class="m">' + new Date(r.created_at).toLocaleString() + '</span></div>';
  }).join('') : '<p class="empty">No research yet.</p>';
}
function openReport(i) {
  const r = HISTORY[i], x = r.extra || {};
  try { history.replaceState(null, '', '#r-' + r.id); } catch (e) {}
  show({report_id: r.id, answer: r.report, mode: r.mode, mode_title: r.mode ? (r.mode[0].toUpperCase() + r.mode.slice(1)) : r.source,
    rules: x.rules, claims: r.claims || [], follow_ups: x.follow_ups || [], sources: r.sources || [], receipt: r.receipt || {}, policy_decisions: []}, r.topic);
  showTab('answer');
}

async function loadTopics() {
  let ts = []; try { ts = await (await fetch('/topics')).json(); } catch (e) {}
  $('topics').innerHTML = ts.length ? ts.map(t => '<div class="topic' + (t.enabled ? '' : ' off') + '"><div class="q">' + esc(t.query)
    + '<div class="meta">' + esc(t.schedule) + ' · ' + (t.last_run ? 'last run ' + new Date(t.last_run).toLocaleDateString() : 'never run') + '</div></div>'
    + '<button class="linkbtn" onclick="runTopic(\'' + t.id + '\')">Run now</button>'
    + '<button class="linkbtn" onclick="toggleTopic(\'' + t.id + '\',' + !t.enabled + ')">' + (t.enabled ? 'Pause' : 'Resume') + '</button>'
    + '<button class="linkbtn" onclick="delTopic(\'' + t.id + '\')">Remove</button></div>').join('') : '<div class="mode-help">No watch topics yet.</div>';
}
async function addTopic() { const q = $('new-topic').value.trim(); if (!q) return; await post('/topics/add', {query: q, schedule: $('new-schedule').value}); $('new-topic').value = ''; loadTopics(); }
async function toggleTopic(id, en) { await post('/topics/toggle', {id, enabled: en}); loadTopics(); }
async function delTopic(id) { await post('/topics/delete', {id}); loadTopics(); }
async function runTopic(id) { const d = await post('/topics/run', {id}); $('go').disabled = true; follow(d.job_id, ''); }

renderModes(); loadStatus().then(syncSources); loadTopics();
// A link like /#r-<report id> opens that saved report (handy for sharing a result).
loadHistory().then(() => { const m = location.hash.match(/^#r-([0-9a-f]+)$/);
  if (m) { const i = HISTORY.findIndex(r => r.id === m[1]); if (i >= 0) openReport(i); } });
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("Web Researcher")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
