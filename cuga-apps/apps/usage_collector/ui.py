"""
HTML UI for the Usage Collector dashboard.
Exported as _HTML — a single self-contained string served by FastAPI's "/" route.

Carbonized (IBM Carbon, g10 light) via the shared `_carbon` foundation.

Layout: a tabbed dashboard polling /api/stats (forwarding any ?token=… from the
page URL). Tabs:
  • Overview   — summary cards + interactive daily charts (API calls, MCP tool
                 calls, app visits, unique visitors/day). Every chart has a hover
                 tooltip showing the exact day and counts, plus dated x-axis ticks.
  • Apps       — per-app table with windowed columns (today / yesterday / 7d /
                 14d / 1m / 3m / total) + last seen and a 14-day sparkline, with a
                 Requests/Visitors metric toggle.
  • API calls  — provider (LLM/search/finance) windowed call counts, failure
                 reasons, and last seen.
  • MCP        — MCP servers & tools: each server's per-day status up top, the
                 tools (windowed columns + last seen) broken out below.
  • Utterances — recent natural-language inputs (text scrubbed/truncated), with
                 time-window filter chips (today / yesterday / 7d / 14d / 1m / 3m /
                 all) showing the exact per-window count.

All tables and the downloadable JSON/CSV report carry the same time-window
breakdown; the CSV adds WIN-* rows (the period column holds the window name).
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { background: var(--cds-background); display: flex; flex-direction: column; }
  main { flex: 1; overflow-y: auto; padding: var(--cds-sp-07); }

  .summary { display: flex; gap: var(--cds-sp-05); flex-wrap: wrap; margin-bottom: var(--cds-sp-06); }
  .stat {
    background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    border-left: 3px solid var(--cds-interactive);
    padding: var(--cds-sp-05) var(--cds-sp-06); min-width: 10rem;
  }
  .stat .num { font-size: 1.75rem; font-weight: 600; font-family: var(--cds-font-mono); line-height: 1.1; }
  .stat .lbl { font-size: 0.6875rem; text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-secondary); margin-top: var(--cds-sp-02); }

  /* Tab bar */
  .tabs { display: flex; align-items: stretch; gap: 0; border-bottom: 1px solid var(--cds-border-subtle);
          margin-bottom: var(--cds-sp-06); flex-wrap: wrap; }
  .tab { appearance: none; background: none; border: none; cursor: pointer;
         padding: var(--cds-sp-04) var(--cds-sp-06); font-size: 0.8125rem; font-weight: 600;
         color: var(--cds-text-secondary); border-bottom: 2px solid transparent; }
  .tab:hover { background: var(--cds-layer-hover-01); color: var(--cds-text-primary); }
  .tab.active { color: var(--cds-text-primary); border-bottom-color: var(--cds-interactive); }
  .tab .badge { font-family: var(--cds-font-mono); font-weight: 600; margin-left: 0.4rem;
                font-size: 0.6875rem; color: var(--cds-text-helper); }
  .tab.active .badge { color: var(--cds-interactive); }
  .tabsearch { margin-left: auto; align-self: center; min-width: 16rem; padding: var(--cds-sp-03) var(--cds-sp-04);
               font-size: 0.8125rem; background: var(--cds-field-01); color: var(--cds-text-primary);
               border: none; border-bottom: 1px solid var(--cds-border-strong); }
  .tabsearch:focus { outline: 2px solid var(--cds-focus); outline-offset: -2px; }
  .panel { display: none; }
  .panel.active { display: block; }

  .toolbar { display: flex; align-items: center; gap: var(--cds-sp-04); margin-bottom: var(--cds-sp-04); }
  .toolbar h2 { font-size: 0.875rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-secondary); }
  .refresh-badge { margin-left: auto; font-size: 0.6875rem; color: var(--cds-text-helper); }
  .dl-group { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
  .dl-label { font-size: 0.6875rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--cds-text-helper); }
  .dl-btn { font-size: 0.75rem; font-weight: 600; color: #fff; background: #0f62fe; padding: 0.25rem 0.6rem; text-decoration: none; white-space: nowrap; }
  .dl-btn:hover { background: #0353e9; }
  .dl-link { font-size: 0.6875rem; color: #78a9ff; text-decoration: none; white-space: nowrap; }
  .dl-link:hover { text-decoration: underline; }

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

  /* Metric glossary */
  .legend { margin: 0 0 var(--cds-sp-06); background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle); }
  .legend summary { cursor: pointer; padding: var(--cds-sp-04) var(--cds-sp-05); font-size: 0.6875rem;
                    font-weight: 600; text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-secondary); }
  .legend dl { margin: 0; padding: 0 var(--cds-sp-05) var(--cds-sp-05);
               display: grid; grid-template-columns: max-content 1fr; gap: var(--cds-sp-03) var(--cds-sp-06); }
  .legend dt { font-weight: 600; font-size: 0.8125rem; font-family: var(--cds-font-mono); white-space: nowrap; }
  .legend dd { margin: 0; font-size: 0.8125rem; color: var(--cds-text-secondary); }
  th[title], .stat[title] { cursor: help; }
  th[title] { text-decoration: underline dotted var(--cds-border-strong); text-underline-offset: 3px; }

  /* Trend charts */
  .charts { display: grid; grid-template-columns: 1fr 1fr; gap: var(--cds-sp-06); margin-bottom: var(--cds-sp-07); }
  @media (max-width: 980px) { .charts { grid-template-columns: 1fr; } }
  .card { background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle); padding: var(--cds-sp-05); }
  .card h3 { margin: 0 0 var(--cds-sp-02); font-size: 0.75rem; font-weight: 600;
             text-transform: uppercase; letter-spacing: 0.32px; color: var(--cds-text-secondary); }
  .card .sub { font-size: 0.6875rem; color: var(--cds-text-helper); margin: 0 0 var(--cds-sp-04); }
  .chart-host { position: relative; width: 100%; }
  .chart { width: 100%; height: 150px; display: block; overflow: visible; }
  .chart .axlbl { font-size: 9px; fill: var(--cds-text-helper); font-family: var(--cds-font-mono); }
  .chart .ymax { font-size: 9px; fill: var(--cds-text-secondary); font-family: var(--cds-font-mono); }
  .chart .grid { stroke: var(--cds-border-subtle); stroke-width: 1; }
  .chart .axis { stroke: var(--cds-border-strong); stroke-width: 1; }
  .chart rect.hl { fill: var(--cds-layer-accent-01); opacity: 0.55; pointer-events: none; }
  rect.bar-ok  { fill: var(--cds-support-success); }
  rect.bar-err { fill: var(--cds-support-error); }
  rect.bar-req { fill: var(--cds-interactive); }
  rect.bar-mcp { fill: #8a3ffc; }
  rect.bar-vis { fill: #007d79; }
  .chart-legend { display: flex; gap: var(--cds-sp-05); margin-top: var(--cds-sp-03); font-size: 0.6875rem; color: var(--cds-text-secondary); flex-wrap: wrap; }
  .chart-legend .key { display: inline-flex; align-items: center; gap: 4px; }
  .sw { width: 10px; height: 10px; display: inline-block; }
  .sw.ok { background: var(--cds-support-success); } .sw.err { background: var(--cds-support-error); }
  .sw.req { background: var(--cds-interactive); } .sw.mcp { background: #8a3ffc; }
  .sw.vis { background: #007d79; }

  /* Floating chart tooltip (one shared element, positioned at the cursor) */
  .charttt { position: fixed; z-index: 2147483640; pointer-events: none; display: none;
             background: var(--cds-text-primary); color: var(--cds-background);
             padding: 6px 9px; font-size: 0.75rem; line-height: 1.35; max-width: 16rem;
             box-shadow: 0 2px 8px rgba(0,0,0,0.25); }
  .charttt .d { font-family: var(--cds-font-mono); font-weight: 600; margin-bottom: 2px; }
  .charttt .row { display: flex; gap: 0.6rem; justify-content: space-between; }
  .charttt .row .v { font-family: var(--cds-font-mono); }

  /* Provider failure-reason chips */
  .codes { display: flex; flex-wrap: wrap; gap: 2px; justify-content: flex-end; margin-top: 2px; }
  .codechip { font-family: var(--cds-font-mono); font-size: 0.625rem; padding: 0 4px; white-space: nowrap;
              background: var(--cds-layer-accent-01); border: 1px solid var(--cds-border-subtle); color: var(--cds-text-secondary); }

  /* MCP servers & tools */
  .srv { background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle); margin-bottom: var(--cds-sp-06); }
  .srv > summary { list-style: none; cursor: pointer; padding: var(--cds-sp-05); display: grid;
                   grid-template-columns: 1fr auto; gap: var(--cds-sp-04) var(--cds-sp-06); align-items: center; }
  .srv > summary::-webkit-details-marker { display: none; }
  .srv-name { font-size: 1rem; font-weight: 600; display: flex; align-items: center; gap: var(--cds-sp-03); }
  .srv-name .caret { transition: transform 0.15s; color: var(--cds-text-helper); font-size: 0.75rem; }
  .srv[open] .srv-name .caret { transform: rotate(90deg); }
  .srv-metrics { display: flex; gap: var(--cds-sp-06); }
  .srv-metric { text-align: right; }
  .srv-metric .n { font-family: var(--cds-font-mono); font-size: 1.1rem; font-weight: 600; }
  .srv-metric .n.err { color: var(--cds-support-error); }
  .srv-metric .l { font-size: 0.625rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--cds-text-helper); }
  .srv-body { padding: 0 var(--cds-sp-05) var(--cds-sp-05); border-top: 1px solid var(--cds-border-subtle); }
  .srv-chart-wrap { max-width: 520px; margin: var(--cds-sp-05) 0; }
  .srv-sub { font-size: 0.6875rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.32px;
             color: var(--cds-text-secondary); margin: var(--cds-sp-05) 0 var(--cds-sp-03); }

  /* Segmented control (Apps table metric toggle: requests / visitors) */
  .segmented { display: inline-flex; border: 1px solid var(--cds-border-strong); }
  .segmented button { appearance: none; background: var(--cds-field-01); border: none; cursor: pointer;
    padding: 0.25rem 0.7rem; font-size: 0.75rem; font-weight: 600; color: var(--cds-text-secondary); }
  .segmented button + button { border-left: 1px solid var(--cds-border-strong); }
  .segmented button.on { background: var(--cds-interactive); color: #fff; }

  /* Time-window filter chips (utterances tab) */
  .filterbar { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; margin-bottom: var(--cds-sp-04); }
  .filterbar .flbl { font-size: 0.6875rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--cds-text-helper); margin-right: 0.2rem; }
  .fchip { appearance: none; cursor: pointer; background: var(--cds-field-01); color: var(--cds-text-secondary);
    border: 1px solid var(--cds-border-subtle); padding: 0.2rem 0.55rem; font-size: 0.75rem; font-weight: 600;
    display: inline-flex; align-items: baseline; gap: 0.35rem; }
  .fchip:hover { background: var(--cds-layer-hover-01); color: var(--cds-text-primary); }
  .fchip.on { background: var(--cds-interactive); color: #fff; border-color: var(--cds-interactive); }
  .fchip .fc { font-family: var(--cds-font-mono); font-size: 0.6875rem; opacity: 0.85; }
  .filter-note { font-size: 0.6875rem; color: var(--cds-text-helper); margin: 0 0 var(--cds-sp-04); }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;cuga-apps&nbsp;·&nbsp;Usage</div>
  <div class="cds-header__actions">
    <span class="dl-group" id="dlGroup">
      <span class="dl-label">Reports</span>
      <a id="dlDailyCsv"    class="dl-btn"  download>↓ Daily CSV</a>
      <a id="dlMonthlyCsv"  class="dl-btn"  download>↓ Monthly CSV</a>
      <a id="dlDailyJson"   class="dl-link" download>daily JSON</a>
      <a id="dlMonthlyJson" class="dl-link" download>monthly JSON</a>
    </span>
    <span class="status-badge"><span class="status-dot"></span><span class="cds-helper-01" id="statusText">Live</span></span>
  </div>
</header>

<main>
  <div class="summary" id="summary"></div>

  <details class="legend">
    <summary>What do these metrics mean?</summary>
    <dl>
      <dt>Requests</dt><dd>Tracked agent calls — POST requests to an app's endpoints. This is what the umbrella counts as an app "use".</dd>
      <dt>Time&nbsp;windows</dt><dd>Every table breaks counts into <b>Today</b>, <b>Yesterday</b>, <b>7d</b>, <b>14d</b>, <b>1m</b> (30 days), <b>3m</b> (90 days) and <b>Total</b> (all-time), all in UTC. An N-day window includes today plus the prior N−1 days.</dd>
      <dt>Visitors</dt><dd>Unique anonymous visitors — a daily-salted hash of the client IP. No IP is stored and the hash resets every day, so the same person counts once per day; multi-day windows sum the daily unique counts. Toggle the <b>Apps</b> table between Requests and Visitors, and see the <b>Unique visitors per day</b> chart on Overview.</dd>
      <dt>API&nbsp;calls</dt><dd>External/provider API calls made while serving requests — e.g. <b>watsonx</b> (LLM), <b>tavily</b> (web search), <b>alpha_vantage</b> (finance). Counted per provider, per day.</dd>
      <dt>MCP&nbsp;tool&nbsp;calls</dt><dd>Invocations of MCP <b>tools</b> on a given MCP <b>server</b> (web, knowledge, geo, finance, …). Counted per server and per tool, per day — see the <b>MCP</b> tab.</dd>
      <dt>Errors</dt><dd>Calls that failed (the provider/tool returned an error rather than a result).</dd>
      <dt>Utterances</dt><dd>The natural-language text users submitted. Obvious secrets are scrubbed and the text is truncated before it's stored.</dd>
      <dt>Charts</dt><dd>Daily bars for the last 14 days. <b>Hover any column</b> for that day's exact counts; the x-axis ticks show the dates.</dd>
      <dt>Last&nbsp;seen</dt><dd>Time since the app's most recent tracked request.</dd>
    </dl>
  </details>

  <div class="tabs" id="tabs">
    <button class="tab active" data-tab="overview">Overview</button>
    <button class="tab" data-tab="apps">Apps <span class="badge" id="cntApps"></span></button>
    <button class="tab" data-tab="providers">API calls <span class="badge" id="cntProv"></span></button>
    <button class="tab" data-tab="mcp">MCP servers &amp; tools <span class="badge" id="cntMcp"></span></button>
    <button class="tab" data-tab="utterances">Utterances <span class="badge" id="cntUtt"></span></button>
    <input id="search" class="tabsearch" type="search" placeholder="Filter the current tab…" aria-label="Filter dashboard" />
  </div>

  <!-- Overview -->
  <section class="panel active" data-panel="overview">
    <div class="charts">
      <div class="card">
        <h3>Provider API calls — last 14 days</h3>
        <p class="sub">watsonx (LLM), tavily (search), alpha_vantage (finance), … · hover a day for exact counts</p>
        <div class="chart-host"><div id="chartCalls"></div></div>
        <div class="chart-legend">
          <span class="key"><span class="sw ok"></span>successful</span>
          <span class="key"><span class="sw err"></span>failed (429/404/…)</span>
        </div>
      </div>
      <div class="card">
        <h3>MCP tool calls — last 14 days</h3>
        <p class="sub">across all MCP servers &amp; tools · hover a day for exact counts</p>
        <div class="chart-host"><div id="chartMcp"></div></div>
        <div class="chart-legend">
          <span class="key"><span class="sw mcp"></span>successful</span>
          <span class="key"><span class="sw err"></span>failed</span>
        </div>
      </div>
      <div class="card">
        <h3>App visits — last 14 days</h3>
        <p class="sub">tracked requests across every app · hover a day for requests + visitors</p>
        <div class="chart-host"><div id="chartVisits"></div></div>
        <div class="chart-legend">
          <span class="key"><span class="sw req"></span>requests</span>
        </div>
      </div>
      <div class="card">
        <h3>Unique visitors per day — last 14 days</h3>
        <p class="sub">distinct anonymous visitors/day (daily-salted IP hash) across every app · hover a day for the count</p>
        <div class="chart-host"><div id="chartVisitors"></div></div>
        <div class="chart-legend">
          <span class="key"><span class="sw vis"></span>unique visitors</span>
        </div>
      </div>
    </div>
  </section>

  <!-- Apps -->
  <section class="panel" data-panel="apps">
    <div class="toolbar">
      <h2>Per-app usage</h2>
      <span class="segmented" id="appsMetric" role="group" aria-label="Metric">
        <button data-metric="requests" class="on">Requests</button>
        <button data-metric="uniques">Visitors</button>
      </span>
      <span class="refresh-badge" id="refreshBadge">auto-refresh 15s</span>
    </div>
    <div id="tableWrap"><div class="empty">No usage recorded yet. Once apps receive traffic, they'll appear here.</div></div>
  </section>

  <!-- API providers -->
  <section class="panel" data-panel="providers">
    <div class="toolbar"><h2>Provider API calls</h2></div>
    <div id="provWrap"><div class="empty">No provider calls recorded yet.</div></div>
  </section>

  <!-- MCP servers & tools -->
  <section class="panel" data-panel="mcp">
    <div class="card" style="margin-bottom: var(--cds-sp-06)">
      <h3>MCP tool calls — last 14 days (all servers)</h3>
      <p class="sub">hover a day for exact counts</p>
      <div class="chart-host" style="max-width: 640px"><div id="chartMcp2"></div></div>
      <div class="chart-legend">
        <span class="key"><span class="sw mcp"></span>successful</span>
        <span class="key"><span class="sw err"></span>failed</span>
      </div>
    </div>
    <div class="toolbar"><h2>Per-server &amp; per-tool usage</h2></div>
    <div id="mcpWrap"><div class="empty">No MCP tool calls recorded yet.</div></div>
  </section>

  <!-- Utterances -->
  <section class="panel" data-panel="utterances">
    <div class="toolbar"><h2>Recent utterances</h2></div>
    <div class="filterbar" id="uttFilter"><span class="flbl">Window</span></div>
    <p class="filter-note" id="uttNote"></p>
    <div id="uttWrap"><div class="empty">No utterances recorded yet.</div></div>
  </section>
</main>

<script>
  const TOKEN = new URLSearchParams(location.search).get('token') || '';
  const statsUrl = '/api/stats' + (TOKEN ? ('?token=' + encodeURIComponent(TOKEN)) : '');

  // Report download links — RELATIVE url on purpose (see prior note): <a href>
  // navigations aren't re-prefixed by the nginx fetch()-shim, so a relative path
  // resolves against <base href> when path-routed and against "/" standalone.
  const reportUrl = (g, f) =>
    'api/report?granularity=' + g + '&format=' + f +
    (TOKEN ? ('&token=' + encodeURIComponent(TOKEN)) : '');
  document.getElementById('dlDailyCsv').href    = reportUrl('daily', 'csv');
  document.getElementById('dlMonthlyCsv').href  = reportUrl('monthly', 'csv');
  document.getElementById('dlDailyJson').href   = reportUrl('daily', 'json');
  document.getElementById('dlMonthlyJson').href = reportUrl('monthly', 'json');

  function esc(s) { return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function ago(ts) {
    if (!ts) return '—';
    const s = Math.max(0, Date.now()/1000 - ts);
    if (s < 60) return 'just now';
    if (s < 3600) return Math.floor(s/60) + 'm ago';
    if (s < 86400) return Math.floor(s/3600) + 'h ago';
    return Math.floor(s/86400) + 'd ago';
  }
  const WD = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const MO = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function fmtDay(day) {           // "2026-06-19" -> "Thu Jun 19"
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day || '');
    if (!m) return day || '';
    const d = new Date(Date.UTC(+m[1], +m[2]-1, +m[3]));
    return WD[d.getUTCDay()] + ' ' + MO[+m[2]-1] + ' ' + (+m[3]);
  }

  // The fixed time windows every table column / utterance filter uses.
  // [json-key, header label, tooltip]. "total" is all-time.
  const WINS = [
    ['today',     'Today',     'so far today (UTC)'],
    ['yesterday', 'Yesterday', 'the previous UTC day'],
    ['7d',        '7d',        'last 7 days (incl. today)'],
    ['14d',       '14d',       'last 14 days'],
    ['1m',        '1m',        'last 30 days'],
    ['3m',        '3m',        'last 90 days'],
    ['total',     'Total',     'since the collector started'],
  ];
  function winHeaders(unit) {
    return WINS.map(([k, lbl, tip]) =>
      '<th class="num" title="' + esc(unit + ' ' + tip) + '">' + esc(lbl) + '</th>').join('');
  }
  // Render the windowed numeric cells for a row, reading `<prefix><key>` fields.
  function winCells(row, prefix) {
    return WINS.map(([k]) => {
      const v = row[prefix + k] || 0;
      const cls = (k === 'today' && v) ? 'num today-pos' : (v ? 'num' : 'num muted');
      return '<td class="' + cls + '">' + v + '</td>';
    }).join('');
  }

  // ── Interactive bar chart ───────────────────────────────────────────────
  // One shared tooltip element follows the cursor; each chart maps the mouse x
  // to a day index so hovering ANYWHERE in a column reveals that day's counts.
  let TT;
  function tt() {
    if (!TT) { TT = document.createElement('div'); TT.className = 'charttt'; document.body.appendChild(TT); }
    return TT;
  }
  function hideTT() { if (TT) TT.style.display = 'none'; }

  // host: container div.  series: [{day, ...}].  segs: [{key, cls, label}].
  // extra(d): optional array of extra [label, value] rows for the tooltip.
  function makeChart(host, series, segs, extra) {
    if (!host) return;
    if (!series || !series.length) { host.innerHTML = '<div class="empty">No data yet.</div>'; return; }
    const n = series.length, slot = 30, bw = 18, H = 120, padT = 12, padB = 22;
    const W = n * slot;
    const max = Math.max(1, ...series.map(d => segs.reduce((s, sg) => s + (d[sg.key] || 0), 0)));
    let bars = '';
    series.forEach((d, i) => {
      const x = i * slot + (slot - bw) / 2;
      let y = padT + H;
      segs.forEach(sg => {
        const v = d[sg.key] || 0; if (v <= 0) return;
        const h = Math.max(1, Math.round((v / max) * H));
        y -= h;
        bars += '<rect x="' + x + '" y="' + y + '" width="' + bw + '" height="' + h + '" class="' + sg.cls + '"></rect>';
      });
    });
    // x-axis date ticks: first, last, and a few evenly spaced inside.
    const baseY = padT + H;
    let ticks = '';
    const want = Math.min(n, 6);
    const seen = new Set();
    for (let k = 0; k < want; k++) {
      const i = Math.round(k * (n - 1) / Math.max(1, want - 1));
      if (seen.has(i)) continue; seen.add(i);
      const cx = i * slot + slot / 2;
      const lbl = (series[i].day || '').slice(5);     // MM-DD
      const anchor = i === 0 ? 'start' : (i === n - 1 ? 'end' : 'middle');
      const tx = i === 0 ? cx - slot / 2 : (i === n - 1 ? cx + slot / 2 : cx);
      ticks += '<text x="' + tx + '" y="' + (baseY + 14) + '" class="axlbl" text-anchor="' + anchor + '">' + esc(lbl) + '</text>';
    }
    const svg =
      '<svg class="chart" viewBox="0 0 ' + W + ' ' + (padT + H + padB) + '" preserveAspectRatio="none" role="img" aria-label="daily bar chart">' +
      '<rect class="hl" x="0" y="' + padT + '" width="' + slot + '" height="' + H + '" style="display:none"></rect>' +
      '<line class="grid" x1="0" y1="' + padT + '" x2="' + W + '" y2="' + padT + '"></line>' +
      '<text x="2" y="' + (padT - 3) + '" class="ymax">max ' + max + '</text>' +
      bars +
      '<line class="axis" x1="0" y1="' + baseY + '" x2="' + W + '" y2="' + baseY + '"></line>' +
      ticks +
      '</svg>';
    host.innerHTML = svg;
    const svgEl = host.querySelector('svg');
    const hl = svgEl.querySelector('rect.hl');
    function at(e) {
      const r = svgEl.getBoundingClientRect();
      let i = Math.floor(((e.clientX - r.left) / r.width) * n);
      i = Math.max(0, Math.min(n - 1, i));
      const d = series[i];
      hl.setAttribute('x', i * slot); hl.style.display = '';
      const rows = segs.map(sg => '<div class="row"><span>' + esc(sg.label) + '</span><span class="v">' + (d[sg.key] || 0) + '</span></div>');
      (extra ? extra(d) : []).forEach(([l, v]) => rows.push('<div class="row"><span>' + esc(l) + '</span><span class="v">' + v + '</span></div>'));
      const el = tt();
      el.innerHTML = '<div class="d">' + esc(fmtDay(d.day)) + '</div>' + rows.join('');
      el.style.display = 'block';
      let left = e.clientX + 14, top = e.clientY + 14;
      const tw = el.offsetWidth, th = el.offsetHeight;
      if (left + tw > window.innerWidth - 8) left = e.clientX - tw - 14;
      if (top + th > window.innerHeight - 8) top = e.clientY - th - 14;
      el.style.left = left + 'px'; el.style.top = top + 'px';
    }
    svgEl.addEventListener('mousemove', at);
    svgEl.addEventListener('mouseleave', () => { hl.style.display = 'none'; hideTT(); });
  }

  function renderCharts(data) {
    const s = data.series || {};
    makeChart(document.getElementById('chartCalls'), s.api_calls || [],
      [{key: 'calls', cls: 'bar-ok', label: 'successful'}, {key: 'errors', cls: 'bar-err', label: 'failed'}]);
    makeChart(document.getElementById('chartMcp'), s.mcp_calls || [],
      [{key: 'calls', cls: 'bar-mcp', label: 'successful'}, {key: 'errors', cls: 'bar-err', label: 'failed'}]);
    makeChart(document.getElementById('chartMcp2'), s.mcp_calls || [],
      [{key: 'calls', cls: 'bar-mcp', label: 'successful'}, {key: 'errors', cls: 'bar-err', label: 'failed'}]);
    makeChart(document.getElementById('chartVisits'), s.visits || [],
      [{key: 'requests', cls: 'bar-req', label: 'requests'}], d => [['visitors', d.uniques || 0]]);
    makeChart(document.getElementById('chartVisitors'), s.visits || [],
      [{key: 'uniques', cls: 'bar-vis', label: 'unique visitors'}], d => [['requests', d.requests || 0]]);
  }

  function spark(series, field) {
    const val = d => field ? (d[field] || 0) : ((d.requests != null ? d.requests : d.calls) || 0);
    const max = Math.max(1, ...series.map(val));
    return '<span class="spark" title="last ' + series.length + ' days">' +
      series.map((d, i) => {
        const v = val(d);
        const h = Math.round((v / max) * 26);
        const cls = (i === series.length - 1) ? 'bar today' : 'bar';
        const extra = (field !== 'uniques' && d.uniques != null) ? (', ' + d.uniques + ' visitors')
                    : (d.errors ? (', ' + d.errors + ' failed') : '');
        return '<span class="' + cls + '" style="height:' + Math.max(2, h) + 'px" title="' +
               esc(fmtDay(d.day)) + ': ' + v + extra + '"></span>';
      }).join('') + '</span>';
  }

  function searching() { return !!(document.getElementById('search').value || '').trim(); }

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
        winCells(p, 'calls_') +
        '<td class="num ' + (p.errors_total ? 'err' : 'muted') + '">' + (p.errors_total||0) + chips + '</td>' +
        '<td class="muted">' + ago(p.last_ts) + '</td></tr>';
    }).join('');
    wrap.innerHTML = '<table><thead><tr>' +
      '<th title="External API the apps call — LLM (watsonx), web search (tavily), finance (alpha_vantage), …">Provider</th>' +
      winHeaders('Successful calls') +
      '<th class="num" title="Failed calls (all-time), with the reason breakdown below (429 = rate limit reached, 404, timeout, …)">Errors</th>' +
      '<th title="Time since this provider\'s most recent call">Last seen</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';
  }

  // ── MCP servers & tools ─────────────────────────────────────────────────
  function renderMcp(servers) {
    const wrap = document.getElementById('mcpWrap');
    if (!servers.length) {
      wrap.innerHTML = '<div class="empty">' + (searching()
        ? 'No matching MCP servers or tools.'
        : 'No MCP tool calls recorded yet. Once apps invoke MCP tools they\'ll appear here, broken out per server and per tool.') + '</div>';
      return;
    }
    wrap.innerHTML = servers.map((s, idx) => {
      const toolRows = (s.tools || []).map(t =>
        '<tr><td class="app-name">' + esc(t.tool) + '</td>' +
        winCells(t, 'calls_') +
        '<td class="num ' + (t.errors_total ? 'err' : 'muted') + '">' + (t.errors_total||0) + '</td>' +
        '<td>' + spark(t.series || []) + '</td>' +
        '<td class="muted">' + ago(t.last_ts) + '</td></tr>').join('');
      return (
        '<details class="srv"' + (idx === 0 ? ' open' : '') + '>' +
          '<summary>' +
            '<span class="srv-name"><span class="caret">▶</span>' + esc(s.server) + '</span>' +
            '<span class="srv-metrics">' +
              '<span class="srv-metric"><div class="n ' + (s.calls_today ? '' : 'muted') + '">' + (s.calls_today||0) + '</div><div class="l">today</div></span>' +
              '<span class="srv-metric"><div class="n">' + (s.calls_total||0) + '</div><div class="l">total</div></span>' +
              '<span class="srv-metric"><div class="n ' + (s.errors_total ? 'err' : 'muted') + '">' + (s.errors_total||0) + '</div><div class="l">errors</div></span>' +
              '<span class="srv-metric"><div class="n muted">' + ago(s.last_ts) + '</div><div class="l">last seen</div></span>' +
            '</span>' +
          '</summary>' +
          '<div class="srv-body">' +
            '<div class="srv-sub">Daily status (last 14 days)</div>' +
            '<div class="srv-chart-wrap"><div class="chart-host"><div id="srvChart' + idx + '"></div></div>' +
              '<div class="chart-legend"><span class="key"><span class="sw mcp"></span>successful</span>' +
              '<span class="key"><span class="sw err"></span>failed</span></div></div>' +
            '<div class="srv-sub">Tools in this server</div>' +
            '<table><thead><tr>' +
              '<th title="MCP tool name as exposed by the server">Tool</th>' +
              winHeaders('Successful calls') +
              '<th class="num" title="Failed calls (all-time)">Errors</th>' +
              '<th title="Daily call volume; the last bar is today">Last 14 days</th>' +
              '<th title="Time since this tool\'s most recent call">Last seen</th>' +
            '</tr></thead><tbody>' + toolRows + '</tbody></table>' +
          '</div>' +
        '</details>');
    }).join('');
    // Draw each server's daily chart after the DOM exists.
    servers.forEach((s, idx) => {
      makeChart(document.getElementById('srvChart' + idx), s.series || [],
        [{key: 'calls', cls: 'bar-mcp', label: 'successful'}, {key: 'errors', cls: 'bar-err', label: 'failed'}]);
    });
  }

  function callChips(calls) {
    if (!calls) return '';
    const keys = Object.keys(calls).sort();
    if (!keys.length) return '';
    return '<span class="utt-calls">' + keys.map(k =>
      '<span class="callchip" title="' + esc(k) + ' calls triggered by this utterance">' +
      esc(k) + ' ×' + calls[k] + '</span>').join('') + '</span>';
  }

  let UTT_WINDOW = 'total';   // today|yesterday|7d|14d|1m|3m|total

  // Is a unix-seconds ts inside the given UTC window? Mirrors the backend's
  // day-set semantics (an N-day window includes today and the prior N-1 days).
  function uttInWindow(ts, win) {
    if (!win || win === 'total') return true;
    const now = new Date();
    const startToday = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) / 1000;
    const DAY = 86400;
    if (win === 'today') return ts >= startToday;
    if (win === 'yesterday') return ts >= startToday - DAY && ts < startToday;
    const n = {'7d': 7, '14d': 14, '1m': 30, '3m': 90}[win] || 0;
    return ts >= startToday - (n - 1) * DAY;
  }

  function renderUttChips(windows) {
    const bar = document.getElementById('uttFilter');
    bar.innerHTML = '<span class="flbl">Window</span>' + WINS.map(([k, lbl]) => {
      const label = k === 'total' ? 'All' : lbl;
      const c = (windows && windows[k]) || 0;
      return '<button class="fchip' + (k === UTT_WINDOW ? ' on' : '') + '" data-win="' + k + '">' +
        esc(label) + ' <span class="fc">' + c + '</span></button>';
    }).join('');
  }

  function renderUtterances(uttObj, q) {
    const windows = uttObj.windows || {};
    renderUttChips(windows);
    const wrap = document.getElementById('uttWrap');
    const note = document.getElementById('uttNote');
    let utts = (uttObj.recent || []).filter(u => uttInWindow(u.ts, UTT_WINDOW));
    if (q) utts = utts.filter(u => ((u.app || '') + ' ' + (u.text || '')).toLowerCase().includes(q));
    // The chip count is the exact total for the window; the visible list is only
    // the retained recent text, so flag when we're showing a subset.
    const wcount = (windows && windows[UTT_WINDOW]) || 0;
    note.textContent = (!q && utts.length < wcount)
      ? ('Showing ' + utts.length + ' of ' + wcount + ' — only recent utterance text is retained; the window counts above are exact.')
      : '';
    if (!utts.length) {
      wrap.innerHTML = '<div class="empty">' + (q ? 'No matching utterances.'
        : (wcount ? 'No retained utterance text for this window (count: ' + wcount + ').'
                  : 'No utterances recorded yet.')) + '</div>';
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
    ['MCP tool calls today',  'mcp_calls_today',  'MCP tool invocations today across all servers — see the MCP tab for the per-server/per-tool breakdown.'],
    ['Utterances today',      'utterances_today', 'Natural-language inputs users submitted today (secrets scrubbed, text truncated).'],
  ];

  let LAST = null;   // most recent /api/stats payload, re-filtered on search

  function renderSummary(t) {
    document.getElementById('summary').innerHTML = SUMMARY.map(([l,k,desc]) =>
      '<div class="stat" title="' + esc(desc) + '"><div class="num">' + (t[k]||0) + '</div>' +
      '<div class="lbl">' + l + '</div></div>').join('');
  }

  let APPS_METRIC = 'requests';   // 'requests' | 'uniques' — windowed columns

  function renderApps(apps) {
    const wrap = document.getElementById('tableWrap');
    if (!apps.length) {
      wrap.innerHTML = '<div class="empty">' + (searching()
        ? 'No matching apps.'
        : 'No usage recorded yet. Once apps receive traffic, they\'ll appear here.') + '</div>';
      return;
    }
    const prefix = APPS_METRIC + '_';      // requests_ | uniques_
    const unit = APPS_METRIC === 'uniques' ? 'Unique visitors' : 'Requests';
    const rows = apps.map(a =>
      '<tr>' +
        '<td class="app-name">' + esc(a.app) + '</td>' +
        winCells(a, prefix) +
        '<td>' + spark(a.series || [], APPS_METRIC === 'uniques' ? 'uniques' : null) + '</td>' +
        '<td class="muted">' + ago(a.last_ts) + '</td>' +
      '</tr>').join('');
    wrap.innerHTML =
      '<table><thead><tr>' +
        '<th title="App name (the app directory)">App</th>' +
        winHeaders(unit) +
        '<th title="Daily ' + (APPS_METRIC === 'uniques' ? 'visitor' : 'request') +
          ' volume; the green bar is today. Hover a bar for that day\'s counts.">Last 14 days</th>' +
        '<th title="Time since the app\'s most recent tracked request">Last seen</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';
  }

  function render(data) { LAST = data; draw(); }

  function draw() {
    const data = LAST || {};
    renderSummary(data.totals || {});
    renderCharts(data);
    const q = (document.getElementById('search').value || '').trim().toLowerCase();
    let apps  = data.apps || [];
    let provs = data.providers || [];
    let servers = ((data.mcp || {}).servers) || [];
    if (q) {
      apps  = apps.filter(a => (a.app || '').toLowerCase().includes(q));
      provs = provs.filter(p => (p.provider || '').toLowerCase().includes(q));
      servers = servers
        .map(s => {
          if ((s.server || '').toLowerCase().includes(q)) return s;
          const tools = (s.tools || []).filter(t => (t.tool || '').toLowerCase().includes(q));
          return tools.length ? Object.assign({}, s, {tools}) : null;
        })
        .filter(Boolean);
    }
    renderApps(apps);
    renderProviders(provs);
    renderMcp(servers);
    renderUtterances(data.utterances || {}, q);
    // Tab count badges (unfiltered totals).
    document.getElementById('cntApps').textContent = (data.apps || []).length || '';
    document.getElementById('cntProv').textContent = (data.providers || []).length || '';
    document.getElementById('cntMcp').textContent  = (((data.mcp || {}).servers) || []).length || '';
    document.getElementById('cntUtt').textContent  = ((data.utterances || {}).windows || {}).total || '';
  }

  // ── Tabs ────────────────────────────────────────────────────────────────
  document.getElementById('tabs').addEventListener('click', (e) => {
    const btn = e.target.closest('.tab'); if (!btn) return;
    const name = btn.dataset.tab;
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === btn));
    document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.dataset.panel === name));
    hideTT();
  });

  // Apps table metric toggle (Requests / Visitors) — re-render windowed columns.
  document.getElementById('appsMetric').addEventListener('click', (e) => {
    const btn = e.target.closest('button'); if (!btn) return;
    APPS_METRIC = btn.dataset.metric;
    document.querySelectorAll('#appsMetric button').forEach(b => b.classList.toggle('on', b === btn));
    draw();
  });

  // Utterances time-window filter chips.
  document.getElementById('uttFilter').addEventListener('click', (e) => {
    const btn = e.target.closest('.fchip'); if (!btn) return;
    UTT_WINDOW = btn.dataset.win;
    draw();
  });

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
