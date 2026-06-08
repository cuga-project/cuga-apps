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
  .utt-ago { white-space: nowrap; font-size: 0.6875rem; }

  .empty { color: var(--cds-text-secondary); padding: var(--cds-sp-07); text-align: center; }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--cds-support-success); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
  .status-badge { display: flex; align-items: center; gap: var(--cds-sp-03); }
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
  <div class="toolbar">
    <h2>Per-app usage</h2>
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

  function renderProviders(provs) {
    const wrap = document.getElementById('provWrap');
    if (!provs.length) { wrap.innerHTML = '<div class="empty">No provider calls recorded yet.</div>'; return; }
    const rows = provs.map(p =>
      '<tr><td class="app-name">' + esc(p.provider) + '</td>' +
      '<td class="num ' + (p.calls_today ? 'today-pos' : 'muted') + '">' + (p.calls_today||0) + '</td>' +
      '<td class="num">' + (p.calls_total||0) + '</td>' +
      '<td class="num ' + (p.errors_total ? 'err' : 'muted') + '">' + (p.errors_total||0) + '</td></tr>').join('');
    wrap.innerHTML = '<table><thead><tr><th>Provider</th><th class="num">Today</th>' +
      '<th class="num">Total</th><th class="num">Errors</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  function renderUtterances(utts) {
    const wrap = document.getElementById('uttWrap');
    if (!utts.length) { wrap.innerHTML = '<div class="empty">No utterances recorded yet.</div>'; return; }
    wrap.innerHTML = '<ul class="utts">' + utts.map(u =>
      '<li><span class="utt-app">' + esc(u.app) + '</span>' +
      '<span class="utt-text">' + esc(u.text) + '</span>' +
      '<span class="utt-ago muted">' + ago(u.ts) + '</span></li>').join('') + '</ul>';
  }

  function render(data) {
    const t = data.totals || {};
    document.getElementById('summary').innerHTML =
      [['Apps active', t.apps||0],['Requests today', t.requests_today||0],
       ['Unique visitors today', t.uniques_today||0],['API calls today', t.calls_today||0],
       ['Utterances today', t.utterances_today||0],['Requests all-time', t.requests_total||0]]
      .map(([l,n]) => '<div class="stat"><div class="num">' + n + '</div><div class="lbl">' + l + '</div></div>').join('');

    renderProviders(data.providers || []);
    renderUtterances((data.utterances || {}).recent || []);

    const apps = data.apps || [];
    const wrap = document.getElementById('tableWrap');
    if (apps.length === 0) {
      wrap.innerHTML = '<div class="empty">No usage recorded yet. Once apps receive traffic, they\'ll appear here.</div>';
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
        '<th>App</th><th class="num">Today</th><th class="num">Visitors</th>' +
        '<th class="num">7-day</th><th class="num">Total</th><th>Last 14 days</th><th>Last seen</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';
  }

  async function refresh() {
    try {
      const res = await fetch(statsUrl);
      if (res.ok) { render(await res.json()); document.getElementById('statusText').textContent = 'Live'; }
      else { document.getElementById('statusText').textContent = 'Unauthorized'; }
    } catch (_) { document.getElementById('statusText').textContent = 'Offline'; }
  }
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
