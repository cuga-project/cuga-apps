"""
HTML UI for the Usage Collector dashboard.
Exported as _HTML — a single self-contained string served by FastAPI's "/" route.

Carbonized (IBM Carbon, g10 light) via the shared `_carbon` foundation.
Shows a cross-app usage table (requests today / 7d / total, unique visitors
today, last seen) with a 14-day sparkline per app. Polls /api/stats and
forwards any ?token=… from the page URL.
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { background: var(--cds-background); display: flex; flex-direction: column; }
  main { flex: 1; overflow-y: auto; padding: var(--cds-sp-07); }

  .summary { display: flex; gap: var(--cds-sp-05); flex-wrap: wrap; margin-bottom: var(--cds-sp-07); }
  .stat {
    background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    border-left: 3px solid var(--cds-interactive);
    padding: var(--cds-sp-05) var(--cds-sp-06); min-width: 10rem;
  }
  .stat .num { font-size: 1.75rem; font-weight: 600; font-family: var(--cds-font-mono); line-height: 1.1; }
  .stat .lbl { font-size: 0.6875rem; text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-secondary); margin-top: var(--cds-sp-02); }

  .toolbar { display: flex; align-items: center; gap: var(--cds-sp-04); margin-bottom: var(--cds-sp-04); }
  .toolbar h2 { font-size: 0.875rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-secondary); }
  .refresh-badge { margin-left: auto; font-size: 0.6875rem; color: var(--cds-text-helper); }

  table { width: 100%; border-collapse: collapse; background: var(--cds-layer-01); }
  th, td { text-align: left; padding: var(--cds-sp-04) var(--cds-sp-05); font-size: 0.8125rem; border-bottom: 1px solid var(--cds-border-subtle); }
  th { font-size: 0.6875rem; text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-secondary); font-weight: 600; }
  td.num, th.num { text-align: right; font-family: var(--cds-font-mono); }
  tr:hover td { background: var(--cds-layer-hover-01); }
  .app-name { font-weight: 600; }
  .muted { color: var(--cds-text-helper); }
  .today-pos { color: var(--cds-support-success); font-weight: 600; }

  .spark { display: inline-flex; align-items: flex-end; gap: 1px; height: 26px; }
  .spark .bar { width: 5px; background: var(--cds-interactive); opacity: 0.35; }
  .spark .bar.today { opacity: 1; background: var(--cds-support-success); }

  td.err, th.err { text-align: right; font-family: var(--cds-font-mono); color: var(--cds-support-error); }

  .utts { list-style: none; margin: 0; padding: 0; background: var(--cds-layer-01); }
  .utts li { display: flex; align-items: baseline; gap: var(--cds-sp-05); padding: var(--cds-sp-04) var(--cds-sp-05); border-bottom: 1px solid var(--cds-border-subtle); font-size: 0.8125rem; }
  .utts li:hover { background: var(--cds-layer-hover-01); }
  .utt-app { font-weight: 600; min-width: 9rem; color: var(--cds-text-secondary); }
  .utt-text { flex: 1; white-space: pre-wrap; word-break: break-word; }
  .utt-calls { display: inline-flex; flex-wrap: wrap; gap: var(--cds-sp-02); }
  .callchip { font-family: var(--cds-font-mono); font-size: 0.6875rem; padding: 1px 6px; white-space: nowrap;
              background: var(--cds-layer-accent-01); color: var(--cds-text-secondary); border: 1px solid var(--cds-border-subtle); }
  .utt-ago { white-space: nowrap; font-size: 0.6875rem; }

  .empty { color: var(--cds-text-secondary); padding: var(--cds-sp-07); text-align: center; }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--cds-support-success); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
  .status-badge { display: flex; align-items: center; gap: var(--cds-sp-03); }

  .search { margin-left: auto; min-width: 18rem; padding: var(--cds-sp-03) var(--cds-sp-04);
            font-size: 0.8125rem; background: var(--cds-field-01); color: var(--cds-text-primary);
            border: none; border-bottom: 1px solid var(--cds-border-strong); }
  .search:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; }

  /* Metric glossary */
  .legend { margin: 0 0 var(--cds-sp-07); background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle); }
  .legend summary { cursor: pointer; padding: var(--cds-sp-04) var(--cds-sp-05); font-size: 0.6875rem;
                    font-weight: 600; text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-secondary); }
  .legend dl { margin: 0; padding: 0 var(--cds-sp-05) var(--cds-sp-05);
               display: grid; grid-template-columns: max-content 1fr; gap: var(--cds-sp-03) var(--cds-sp-06); }
  .legend dt { font-weight: 600; font-size: 0.8125rem; font-family: var(--cds-font-mono); white-space: nowrap; }
  .legend dd { margin: 0; font-size: 0.8125rem; color: var(--cds-text-secondary); }
  /* Headers/cells carrying a tooltip get a dotted underline + help cursor. */
  th[title], .stat[title] { cursor: help; }
  th[title] { text-decoration: underline dotted var(--cds-border-strong); text-underline-offset: 3px; }

  /* Trend charts */
  .charts { display: grid; grid-template-columns: 1fr 1fr; gap: var(--cds-sp-06); margin-bottom: var(--cds-sp-07); }
  @media (max-width: 820px) { .charts { grid-template-columns: 1fr; } }
  .card { background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle); padding: var(--cds-sp-05); }
  .card h3 { margin: 0 0 var(--cds-sp-04); font-size: 0.75rem; font-weight: 600;
             text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-secondary); }
  .chart { width: 100%; height: 132px; display: block; }
  .chart .axlbl { font-size: 8px; fill: var(--cds-text-helper); font-family: var(--cds-font-mono); }
  rect.bar-ok  { fill: var(--cds-support-success); }
  rect.bar-err { fill: var(--cds-support-error); }
  rect.bar-req { fill: var(--cds-interactive); }
  .chart-legend { display: flex; gap: var(--cds-sp-05); margin-top: var(--cds-sp-03); font-size: 0.6875rem; color: var(--cds-text-secondary); }
  .chart-legend .key { display: inline-flex; align-items: center; gap: 4px; }
  .sw { width: 10px; height: 10px; display: inline-block; }
  .sw.ok { background: var(--cds-support-success); } .sw.err { background: var(--cds-support-error); } .sw.req { background: var(--cds-interactive); }

  /* Provider failure-reason chips */
  .codes { display: flex; flex-wrap: wrap; gap: 2px; justify-content: flex-end; margin-top: 2px; }
  .codechip { font-family: var(--cds-font-mono); font-size: 0.625rem; padding: 0 4px; white-space: nowrap;
              background: var(--cds-layer-accent-01); border: 1px solid var(--cds-border-subtle); color: var(--cds-text-secondary); }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;cuga-apps&nbsp;·&nbsp;Usage</div>
  <div class="cds-header__actions">
    <span class="status-badge"><span class="status-dot"></span><span class="cds-helper-01" id="statusText">Live</span></span>
  </div>
</header>

<main>
  <div class="summary" id="summary"></div>

  <details class="legend">
    <summary>What do these metrics mean?</summary>
    <dl>
      <dt>Requests</dt><dd>Tracked agent calls — POST requests to an app's endpoints. This is what the umbrella counts as an app "use".</dd>
      <dt>Today / 7-day / Total</dt><dd>Requests in the current UTC day, over the last 7 days, and since the collector started.</dd>
      <dt>Visitors</dt><dd>Unique anonymous visitors today — a daily-salted hash of the client IP. No IP is stored and the hash resets every day, so the same person counts once per day.</dd>
      <dt>API&nbsp;calls</dt><dd>External/provider API calls made while serving requests — e.g. <b>watsonx</b> (LLM), <b>tavily</b> (web search), <b>alpha_vantage</b> (finance). Counted per provider, per day.</dd>
      <dt>Errors</dt><dd>Provider calls that failed (the tool returned an error rather than a result).</dd>
      <dt>Utterances</dt><dd>The natural-language text users submitted. Obvious secrets are scrubbed and the text is truncated before it's stored.</dd>
      <dt>Last&nbsp;14&nbsp;days</dt><dd>Sparkline of daily request volume; the green bar is today. Hover a bar for that day's request + visitor counts.</dd>
      <dt>Last&nbsp;seen</dt><dd>Time since the app's most recent tracked request.</dd>
      <dt>×N&nbsp;chips</dt><dd>API calls a specific utterance triggered. Currently the in-process <b>LLM</b> calls (e.g. watsonx). Out-of-process MCP tools (tavily, geo, …) run in a separate server and appear only in the aggregate "Provider API calls" table above.</dd>
      <dt>Failure&nbsp;codes</dt><dd>Under each provider's error count: how those calls failed — an HTTP status like <b>429</b> (rate limit reached), <b>404</b>, <b>503</b>, or a label like <b>timeout</b>. Use these to see how often an API limit was hit.</dd>
    </dl>
  </details>

  <div class="charts">
    <div class="card">
      <h3>API calls — last 14 days</h3>
      <div id="chartCalls"></div>
      <div class="chart-legend">
        <span class="key"><span class="sw ok"></span>successful</span>
        <span class="key"><span class="sw err"></span>failed (429/404/…)</span>
      </div>
    </div>
    <div class="card">
      <h3>App visits — last 14 days</h3>
      <div id="chartVisits"></div>
      <div class="chart-legend">
        <span class="key"><span class="sw req"></span>requests · hover a column for unique visitors</span>
      </div>
    </div>
  </div>

  <div class="toolbar">
    <h2>Per-app usage</h2>
    <input id="search" class="search" type="search" placeholder="Filter apps, providers, utterances…" aria-label="Filter dashboard" />
    <span class="refresh-badge" id="refreshBadge">auto-refresh 15s</span>
  </div>
  <div id="tableWrap">
    <div class="empty" id="emptyState">No usage recorded yet. Once apps receive traffic, they'll appear here.</div>
  </div>

  <div class="toolbar" style="margin-top: var(--cds-sp-07)"><h2>Provider API calls</h2></div>
  <div id="provWrap"><div class="empty">No provider calls recorded yet.</div></div>

  <div class="toolbar" style="margin-top: var(--cds-sp-07)"><h2>Recent utterances</h2></div>
  <div id="uttWrap"><div class="empty">No utterances recorded yet.</div></div>
</main>

<script>
  const TOKEN = new URLSearchParams(location.search).get('token') || '';
  const statsUrl = '/api/stats' + (TOKEN ? ('?token=' + encodeURIComponent(TOKEN)) : '');

  function esc(s) { return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function ago(ts) {
    if (!ts) return '—';
    const s = Math.max(0, Date.now()/1000 - ts);
    if (s < 60) return 'just now';
    if (s < 3600) return Math.floor(s/60) + 'm ago';
    if (s < 86400) return Math.floor(s/3600) + 'h ago';
    return Math.floor(s/86400) + 'd ago';
  }
  function spark(series) {
    const max = Math.max(1, ...series.map(d => d.requests));
    return '<span class="spark" title="last ' + series.length + ' days">' +
      series.map((d,i) => {
        const h = Math.round((d.requests / max) * 26);
        const cls = (i === series.length - 1) ? 'bar today' : 'bar';
        return '<span class="' + cls + '" style="height:' + Math.max(2,h) + 'px" title="' +
               esc(d.day) + ': ' + d.requests + ' req, ' + d.uniques + ' visitors"></span>';
      }).join('') + '</span>';
  }

  function searching() { return !!(document.getElementById('search').value || '').trim(); }

  // Dependency-free stacked SVG bar chart. segs: [{key, cls, label}];
  // titleExtra(d) optionally appends to a day's hover tooltip (e.g. visitors).
  function chart(series, segs, titleExtra) {
    if (!series || !series.length) return '<div class="empty">No data yet.</div>';
    const slot = 22, bw = 14, H = 112, pad = 4;
    const W = series.length * slot;
    const max = Math.max(1, ...series.map(d => segs.reduce((s, sg) => s + (d[sg.key] || 0), 0)));
    let bars = '', hits = '';
    series.forEach((d, i) => {
      const x = i * slot + pad;
      let y = H;
      segs.forEach(sg => {
        const v = d[sg.key] || 0;
        if (v <= 0) return;
        const h = Math.max(1, Math.round((v / max) * (H - 4)));
        y -= h;
        bars += '<rect x="' + x + '" y="' + y + '" width="' + bw + '" height="' + h + '" class="' + sg.cls + '"></rect>';
      });
      // Full-height transparent hover target per day, carrying the COMPLETE
      // tooltip — so hovering anywhere in the column shows it (incl. visitors),
      // not just the thin/short visible bar.
      const parts = segs.map(sg => sg.label + ': ' + (d[sg.key] || 0));
      const title = esc(d.day) + ' — ' + parts.join(', ') + (titleExtra ? titleExtra(d) : '');
      hits += '<rect x="' + (i * slot) + '" y="0" width="' + slot + '" height="' + H +
              '" fill="transparent" pointer-events="all"><title>' + title + '</title></rect>';
    });
    const f = series[0].day.slice(5), l = series[series.length - 1].day.slice(5);
    return '<svg class="chart" viewBox="0 0 ' + (W + pad) + ' ' + (H + 16) + '" preserveAspectRatio="xMinYMid meet" role="img" aria-label="bar chart">' +
      bars + hits +
      '<text x="' + pad + '" y="' + (H + 13) + '" class="axlbl">' + esc(f) + '</text>' +
      '<text x="' + (W - slot + pad) + '" y="' + (H + 13) + '" class="axlbl">' + esc(l) + '</text>' +
      '</svg>';
  }

  function renderCharts(series) {
    const s = series || {};
    document.getElementById('chartCalls').innerHTML = chart(s.api_calls || [],
      [{key: 'calls', cls: 'bar-ok', label: 'OK'}, {key: 'errors', cls: 'bar-err', label: 'failed'}]);
    document.getElementById('chartVisits').innerHTML = chart(s.visits || [],
      [{key: 'requests', cls: 'bar-req', label: 'requests'}], d => ' (visitors: ' + (d.uniques || 0) + ')');
  }

  function renderProviders(provs) {
    const wrap = document.getElementById('provWrap');
    if (!provs.length) {
      wrap.innerHTML = '<div class="empty">' + (searching() ? 'No matching providers.' : 'No provider calls recorded yet.') + '</div>';
      return;
    }
    const rows = provs.map(p => {
      const codes = p.errors_by_code || {};
      const ckeys = Object.keys(codes).sort();
      const chips = ckeys.length
        ? '<div class="codes">' + ckeys.map(c =>
            '<span class="codechip" title="' + esc(c) + ': ' + codes[c] + ' failed call(s)">' +
            esc(c) + '×' + codes[c] + '</span>').join('') + '</div>'
        : '';
      return '<tr><td class="app-name">' + esc(p.provider) + '</td>' +
        '<td class="num ' + (p.calls_today ? 'today-pos' : 'muted') + '">' + (p.calls_today||0) + '</td>' +
        '<td class="num">' + (p.calls_total||0) + '</td>' +
        '<td class="num ' + (p.errors_total ? 'err' : 'muted') + '">' + (p.errors_total||0) + chips + '</td></tr>';
    }).join('');
    wrap.innerHTML = '<table><thead><tr>' +
      '<th title="External API the apps call — LLM (watsonx), web search (tavily), finance (alpha_vantage), …">Provider</th>' +
      '<th class="num" title="Successful calls so far today (UTC)">Today</th>' +
      '<th class="num" title="Successful calls since the collector started">Total</th>' +
      '<th class="num" title="Failed calls, with the reason breakdown below (429 = rate limit reached, 404, timeout, …)">Errors</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';
  }

  function callChips(calls) {
    if (!calls) return '';
    const keys = Object.keys(calls).sort();
    if (!keys.length) return '';
    return '<span class="utt-calls">' + keys.map(k =>
      '<span class="callchip" title="' + esc(k) + ' API calls triggered by this utterance">' +
      esc(k) + ' ×' + calls[k] + '</span>').join('') + '</span>';
  }

  function renderUtterances(utts) {
    const wrap = document.getElementById('uttWrap');
    if (!utts.length) {
      wrap.innerHTML = '<div class="empty">' + (searching() ? 'No matching utterances.' : 'No utterances recorded yet.') + '</div>';
      return;
    }
    wrap.innerHTML = '<ul class="utts">' + utts.map(u =>
      '<li><span class="utt-app">' + esc(u.app) + '</span>' +
      '<span class="utt-text">' + esc(u.text) + '</span>' +
      callChips(u.calls) +
      '<span class="utt-ago muted">' + ago(u.ts) + '</span></li>').join('') + '</ul>';
  }

  // [label, totals-key, tooltip] — the summary stat cards.
  const SUMMARY = [
    ['Apps active',           'apps',             'Apps that have received at least one tracked request.'],
    ['Requests today',        'requests_today',   'Tracked agent calls (POST requests) so far today (UTC).'],
    ['Unique visitors today', 'uniques_today',    'Distinct anonymous visitors today — a daily-salted IP hash. No IP is stored; resets each day.'],
    ['API calls today',       'calls_today',      'External/provider API calls today — watsonx (LLM), tavily (search), alpha_vantage (finance), …'],
    ['Utterances today',      'utterances_today', 'Natural-language inputs users submitted today (secrets scrubbed, text truncated).'],
    ['Requests all-time',     'requests_total',   'All tracked requests since the collector started.'],
  ];

  let LAST = null;   // most recent /api/stats payload, re-filtered on search

  function renderSummary(t) {
    document.getElementById('summary').innerHTML = SUMMARY.map(([l,k,desc]) =>
      '<div class="stat" title="' + esc(desc) + '"><div class="num">' + (t[k]||0) + '</div>' +
      '<div class="lbl">' + l + '</div></div>').join('');
  }

  function renderApps(apps) {
    const wrap = document.getElementById('tableWrap');
    if (!apps.length) {
      wrap.innerHTML = '<div class="empty">' + (searching()
        ? 'No matching apps.'
        : 'No usage recorded yet. Once apps receive traffic, they\'ll appear here.') + '</div>';
      return;
    }
    const rows = apps.map(a =>
      '<tr>' +
        '<td class="app-name">' + esc(a.app) + '</td>' +
        '<td class="num ' + (a.requests_today ? 'today-pos' : 'muted') + '">' + a.requests_today + '</td>' +
        '<td class="num">' + a.uniques_today + '</td>' +
        '<td class="num">' + a.requests_7d + '</td>' +
        '<td class="num">' + a.requests_total + '</td>' +
        '<td>' + spark(a.series || []) + '</td>' +
        '<td class="muted">' + ago(a.last_ts) + '</td>' +
      '</tr>').join('');
    wrap.innerHTML =
      '<table><thead><tr>' +
        '<th title="App name (the app directory)">App</th>' +
        '<th class="num" title="Tracked requests so far today (UTC)">Today</th>' +
        '<th class="num" title="Unique anonymous visitors today (daily-salted IP hash)">Visitors</th>' +
        '<th class="num" title="Requests over the last 7 days">7-day</th>' +
        '<th class="num" title="Requests since the collector started">Total</th>' +
        '<th title="Daily request volume; the green bar is today">Last 14 days</th>' +
        '<th title="Time since the app\'s most recent tracked request">Last seen</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';
  }

  // Store the payload, then (re)draw applying the current search filter. The
  // summary totals are always unfiltered; the three tables filter by query.
  function render(data) { LAST = data; draw(); }

  function draw() {
    const data = LAST || {};
    renderSummary(data.totals || {});
    renderCharts(data.series || {});
    const q = (document.getElementById('search').value || '').trim().toLowerCase();
    let apps  = data.apps || [];
    let provs = data.providers || [];
    let utts  = (data.utterances || {}).recent || [];
    if (q) {
      apps  = apps.filter(a => (a.app || '').toLowerCase().includes(q));
      provs = provs.filter(p => (p.provider || '').toLowerCase().includes(q));
      utts  = utts.filter(u => ((u.app || '') + ' ' + (u.text || '')).toLowerCase().includes(q));
    }
    renderApps(apps);
    renderProviders(provs);
    renderUtterances(utts);
  }

  async function refresh() {
    try {
      const res = await fetch(statsUrl);
      if (res.ok) { render(await res.json()); document.getElementById('statusText').textContent = 'Live'; }
      else { document.getElementById('statusText').textContent = 'Unauthorized'; }
    } catch (_) { document.getElementById('statusText').textContent = 'Offline'; }
  }
  document.getElementById('search').addEventListener('input', draw);
  refresh();
  setInterval(refresh, 15000);
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("cuga-apps Usage")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
