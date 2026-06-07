"""
IBM What's New Monitor UI — self-contained HTML page served by FastAPI.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation. Layout: left config column (services, schedule, email),
right column (ask chat + recent digests). All ids, fetch() URLs, POST body
shapes, JS function names and routes are preserved — restyle only.
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { background: var(--cds-background); padding: 0 0 var(--cds-sp-09); }

  .sub { font-size: 0.8125rem; color: var(--cds-text-helper); }
  .sub span { color: var(--cds-link-primary); font-weight: 500; }

  .layout {
    display: grid; grid-template-columns: 300px 1fr; gap: var(--cds-sp-06);
    max-width: 72rem; margin: 0 auto; padding: var(--cds-sp-06) var(--cds-sp-05);
    align-items: start;
  }
  @media (max-width: 740px) { .layout { grid-template-columns: 1fr; } }

  .card { margin-bottom: var(--cds-sp-05); }
  .card:last-child { margin-bottom: 0; }

  .card-title {
    font-size: 0.75rem; font-weight: 600; color: var(--cds-text-secondary);
    letter-spacing: 0.32px; text-transform: uppercase; margin-bottom: var(--cds-sp-05);
  }
  .sect {
    font-size: 0.75rem; font-weight: 600; color: var(--cds-text-helper);
    letter-spacing: 0.32px; text-transform: uppercase;
    margin: var(--cds-sp-05) 0 var(--cds-sp-04);
    padding-top: var(--cds-sp-05); border-top: 1px solid var(--cds-border-subtle);
  }
  .sect:first-child { margin-top: 0; padding-top: 0; border-top: none; }

  .field { margin-bottom: var(--cds-sp-04); }

  /* Compact inputs/buttons for the dense config column */
  .row-add { display: flex; gap: var(--cds-sp-03); align-items: stretch; }
  .row-add .cds-input { min-height: 2.5rem; }
  .row-add .cds-btn { min-height: 2.5rem; }

  .svc-item {
    display: flex; align-items: center; justify-content: space-between;
    padding: var(--cds-sp-03) 0; border-bottom: 1px solid var(--cds-border-subtle); gap: var(--cds-sp-03);
  }
  .svc-item:last-child { border-bottom: none; }
  .svc-name { font-size: 0.875rem; color: var(--cds-text-primary); flex: 1; }

  .empty-note { font-size: 0.75rem; color: var(--cds-text-placeholder); padding: var(--cds-sp-02) 0; }

  .status-row {
    display: flex; align-items: center; gap: var(--cds-sp-03);
    margin-top: var(--cds-sp-04); padding: var(--cds-sp-03) var(--cds-sp-04);
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    font-size: 0.75rem;
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .dot.on { background: var(--cds-support-success); }
  .dot.off { background: var(--cds-border-strong); }
  .status-text { color: var(--cds-text-secondary); flex: 1; }
  .status-text strong { color: var(--cds-text-primary); font-weight: 600; }

  .chips { display: flex; flex-wrap: wrap; gap: var(--cds-sp-03); margin-top: var(--cds-sp-04); }
  .chip {
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    border-radius: 0.9375rem; padding: var(--cds-sp-02) var(--cds-sp-04);
    font-size: 0.75rem; color: var(--cds-text-secondary); cursor: pointer;
    transition: all var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .chip:hover { background: var(--cds-interactive); border-color: var(--cds-interactive); color: #fff; }

  .ask-row { display: flex; gap: var(--cds-sp-03); }
  .ask-row .cds-input { flex: 1; }
  .ask-row .cds-btn { flex: none; }

  .result {
    margin-top: var(--cds-sp-05); padding: var(--cds-sp-05);
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    font-size: 0.875rem; line-height: 1.7; color: var(--cds-text-primary);
    display: none;
  }
  .result.visible { display: block; }
  .result a { color: var(--cds-link-primary); }
  .result a:hover { color: var(--cds-link-hover); text-decoration: underline; }
  .result strong { color: var(--cds-text-primary); font-weight: 600; }

  .thinking { color: var(--cds-text-secondary); font-size: 0.875rem; display: inline-flex; align-items: center; gap: var(--cds-sp-03); }
  .spinner { display: inline-block; width: 1rem; height: 1rem; border: 1.5px solid var(--cds-layer-accent); border-top-color: var(--cds-interactive); border-radius: 50%; animation: spin .7s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes fadein { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
  .fadein { animation: fadein .2s ease; }

  .digest-entry {
    padding: var(--cds-sp-04); background: var(--cds-layer-02);
    border: 1px solid var(--cds-border-subtle); margin-bottom: var(--cds-sp-03); font-size: 0.75rem;
  }
  .digest-meta { color: var(--cds-text-secondary); margin-bottom: var(--cds-sp-03); display: flex; align-items: center; gap: var(--cds-sp-03); flex-wrap: wrap; }
  .digest-summary { color: var(--cds-text-secondary); line-height: 1.5; }
  .badge-update {
    font-size: 0.6875rem; padding: 2px 8px; border-radius: 0.9375rem; font-weight: 600;
    letter-spacing: 0.16px; text-transform: uppercase;
    background: var(--cds-support-info-bg); color: var(--cds-link-primary);
  }
  .badge-none {
    font-size: 0.6875rem; padding: 2px 8px; border-radius: 0.9375rem; font-weight: 600;
    letter-spacing: 0.16px; text-transform: uppercase;
    background: var(--cds-layer-accent); color: var(--cds-text-helper);
  }
  .digest-updates { margin-top: var(--cds-sp-03); }
  .update-block {
    padding: var(--cds-sp-03); background: var(--cds-layer-01);
    border-left: 2px solid var(--cds-interactive); margin-top: var(--cds-sp-03);
    white-space: pre-wrap; word-break: break-word; color: var(--cds-text-primary);
    font-size: 0.75rem; line-height: 1.6;
  }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;What's&nbsp;New&nbsp;Monitor</div>
  <div class="cds-header__actions">
    <span class="cds-helper-01 sub">Powered by <span>CugaAgent</span> · IBM Cloud release notes</span>
  </div>
</header>

<div class="layout">

  <!-- ══ Left panel ══ -->
  <div>
    <div class="cds-tile card">

      <div class="sect">Tracked Services</div>
      <div class="row-add">
        <input id="svcInput" class="cds-input" type="text" placeholder="e.g. Event Streams"
               onkeydown="if(event.key==='Enter')addService()" />
        <button class="cds-btn cds-btn--sm" onclick="addService()" style="width:auto;white-space:nowrap">+ Add</button>
      </div>
      <div id="svcList" style="margin-top:var(--cds-sp-04);min-height:20px"></div>

      <div class="sect">Digest Schedule</div>
      <div class="field">
        <select id="scheduleSelect" class="cds-select" onchange="setSchedule(this.value)">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="off">Off</option>
        </select>
      </div>
      <button onclick="runDigest()" id="digestBtn" class="cds-btn cds-btn--secondary cds-btn--full">Run Digest Now</button>

      <div class="sect">Email Settings</div>
      <div class="field">
        <label class="cds-label">SMTP Host</label>
        <input id="eHost" class="cds-input" type="text" placeholder="smtp.gmail.com" value="smtp.gmail.com" />
      </div>
      <div class="field">
        <label class="cds-label">Username</label>
        <input id="eUser" class="cds-input" type="text" placeholder="you@example.com" />
      </div>
      <div class="field">
        <label class="cds-label">Password</label>
        <input id="ePassword" class="cds-input" type="password" placeholder="app password" />
      </div>
      <div class="field">
        <label class="cds-label">Send digests to</label>
        <input id="eTo" class="cds-input" type="text" placeholder="recipient@example.com" />
      </div>
      <button id="emailSaveBtn" onclick="saveEmail()" class="cds-btn cds-btn--full">Save email settings</button>
      <div class="status-row">
        <span class="dot off" id="emailDot"></span>
        <span class="status-text" id="emailLabel">Not configured</span>
      </div>

    </div>
  </div>

  <!-- ══ Right panel ══ -->
  <div>

    <!-- Chat -->
    <div class="cds-tile card">
      <div class="card-title">Ask about IBM Cloud Updates</div>
      <div class="ask-row">
        <input id="qInput" class="cds-input" type="text" placeholder="What changed in Code Engine this month?"
               onkeydown="if(event.key==='Enter')ask()" />
        <button onclick="ask()" id="askBtn" class="cds-btn" style="width:auto">Ask</button>
      </div>
      <div class="chips">
        <span class="chip" onclick="qa('What is new in IBM Code Engine in 2026?')">Code Engine</span>
        <span class="chip" onclick="qa('What is new in watsonx.ai recently?')">watsonx.ai</span>
        <span class="chip" onclick="qa('Latest changes to IBM Cloud Object Storage')">Cloud Object Storage</span>
        <span class="chip" onclick="qa('Recent IBM Kubernetes Service release notes')">Kubernetes Service</span>
        <span class="chip" onclick="qa('What changed in IBM Event Streams recently?')">Event Streams</span>
        <span class="chip" onclick="qa('IBM Databases for PostgreSQL recent updates')">Databases for PostgreSQL</span>
        <span class="chip" onclick="qa('Any new IBM Cloud security or IAM features?')">IAM &amp; Security</span>
        <span class="chip" onclick="qa('What IBM Cloud services had breaking changes recently?')">Breaking changes</span>
        <span class="chip" onclick="qa('Summarize IBM Cloud announcements from the past month')">Monthly summary</span>
      </div>
      <div class="result fadein" id="askResult"></div>
      <div id="emailNowRow" style="display:none;margin-top:var(--cds-sp-04);text-align:right">
        <button class="cds-btn cds-btn--tertiary cds-btn--sm" onclick="emailNow()" style="width:auto">Email this</button>
      </div>
    </div>

    <!-- Digest log -->
    <div class="cds-tile card">
      <div class="card-title">Recent Digests</div>
      <div id="digestLog"></div>
    </div>

  </div>
</div>

<script>
let _lastAnswer = '', _lastQuestion = ''

// ── Services ──────────────────────────────────────────────────────────────

async function loadServices() {
  const res  = await fetch('/services')
  const data = await res.json()
  renderServices(data.services)
  document.getElementById('scheduleSelect').value = data.schedule || 'daily'
}

function renderServices(svcs) {
  const el = document.getElementById('svcList')
  if (!svcs.length) {
    el.innerHTML = '<div class="empty-note">No services tracked yet</div>'
    return
  }
  el.innerHTML = svcs.map(s => {
    const esc = s.replace(/'/g, "\\'")
    return `<div class="svc-item">
      <span class="svc-name">${s}</span>
      <button class="cds-btn cds-btn--danger cds-btn--sm" onclick="removeService('${esc}')" style="width:auto;padding:0 var(--cds-sp-04)">×</button>
    </div>`
  }).join('')
}

async function addService() {
  const name = document.getElementById('svcInput').value.trim()
  if (!name) return
  const res  = await fetch('/services/add', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name})
  })
  const data = await res.json()
  document.getElementById('svcInput').value = ''
  renderServices(data.services)
}

async function removeService(name) {
  const res  = await fetch('/services/remove', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name})
  })
  const data = await res.json()
  renderServices(data.services)
}

async function setSchedule(schedule) {
  await fetch('/schedule', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({schedule})
  })
}

// ── Chat ──────────────────────────────────────────────────────────────────

function qa(q) {
  document.getElementById('qInput').value = q
  ask()
}

async function ask() {
  const q = document.getElementById('qInput').value.trim()
  if (!q) return
  const btn    = document.getElementById('askBtn')
  const result = document.getElementById('askResult')
  document.getElementById('emailNowRow').style.display = 'none'
  btn.disabled = true
  result.className = 'result visible fadein'
  result.innerHTML = '<span class="thinking"><span class="spinner"></span> Searching IBM docs…</span>'

  try {
    const res = await fetch('/ask', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({question: q})
    })
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    _lastAnswer   = data.answer
    _lastQuestion = q
    result.innerHTML = renderMd(data.answer)
    document.getElementById('emailNowRow').style.display = ''
  } catch (err) {
    result.innerHTML = '<span style="color:var(--cds-support-error)">Error: ' + err.message + '</span>'
  } finally {
    btn.disabled = false
  }
}

async function emailNow() {
  if (!_lastAnswer) return
  await fetch('/email/send', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({subject: 'IBM Updates — ' + _lastQuestion.slice(0, 60), body: _lastAnswer})
  })
}

function renderMd(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\\*\\*(.*?)\\*\\*/g,'<strong>$1</strong>')
    .replace(/\\[(.*?)\\]\\((.*?)\\)/g,'<a href="$2" target="_blank">$1</a>')
    .replace(/\\n/g,'<br>')
}

// ── Digest ────────────────────────────────────────────────────────────────

async function runDigest() {
  const btn = document.getElementById('digestBtn')
  btn.disabled = true
  btn.textContent = 'Running digest…'
  try {
    await fetch('/digest/run', {method:'POST'})
  } catch(e) {}
  await loadDigestLog()
  btn.disabled = false
  btn.textContent = 'Run Digest Now'
}

async function loadDigestLog() {
  const res  = await fetch('/digest/recent')
  const data = await res.json()
  renderDigestLog(data.log)
}

function renderDigestLog(entries) {
  const el = document.getElementById('digestLog')
  if (!entries.length) {
    el.innerHTML = '<div class="empty-note">No digests run yet — click "Run Digest Now" or wait for schedule</div>'
    return
  }
  el.innerHTML = entries.map(e => {
    const ts      = new Date(e.timestamp).toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})
    const hasUpd  = e.updates && e.updates.length > 0
    const badge   = hasUpd
      ? `<span class="badge-update">${e.updates.length} update${e.updates.length > 1 ? 's' : ''}</span>`
      : '<span class="badge-none">no changes</span>'
    const sentTag = e.sent ? ' · <span style="color:var(--cds-support-success)">emailed</span>' : ''
    const updBlocks = hasUpd
      ? '<div class="digest-updates">' + e.updates.map(u => `<div class="update-block">${u.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>`).join('') + '</div>'
      : ''
    return `<div class="digest-entry">
      <div class="digest-meta">${ts} ${badge}${sentTag}</div>
      <div class="digest-summary">${e.summary}</div>
      ${updBlocks}
    </div>`
  }).join('')
}

// ── Email ─────────────────────────────────────────────────────────────────

async function saveEmail() {
  const host     = document.getElementById('eHost').value.trim()
  const user     = document.getElementById('eUser').value.trim()
  const password = document.getElementById('ePassword').value
  const to       = document.getElementById('eTo').value.trim()
  if (!user || !password || !to) return
  const btn = document.getElementById('emailSaveBtn')
  btn.disabled = true; btn.textContent = 'Saving…'
  try {
    const res = await fetch('/email/config', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({host, user, password, to})
    })
    const data = await res.json()
    setEmailUI(true, data)
  } catch(e) { alert('Failed: ' + e.message) }
  finally { btn.disabled = false; btn.textContent = 'Save email settings' }
}

function setEmailUI(configured, cfg) {
  document.getElementById('emailDot').className = 'dot ' + (configured ? 'on' : 'off')
  const label = document.getElementById('emailLabel')
  label.innerHTML = configured && cfg
    ? `Digests → <strong>${cfg.to}</strong>`
    : 'Not configured'
}

// ── Init ──────────────────────────────────────────────────────────────────

fetch('/email/status').then(r => r.json()).then(s => {
  if (s.configured) {
    document.getElementById('eHost').value = s.host || 'smtp.gmail.com'
    document.getElementById('eUser').value = s.user || ''
    document.getElementById('eTo').value   = s.to   || ''
    setEmailUI(true, s)
  }
})

loadServices()
loadDigestLog()
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("IBM What's New Monitor")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
