_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IBM What's New Monitor · CugaAgent</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0f1117;color:#e2e2e8;min-height:100vh;padding:36px 24px 80px}
header{text-align:center;margin-bottom:28px}
h1{font-size:22px;font-weight:700;color:#fff;margin-bottom:4px}
.sub{font-size:13px;color:#6b6b7e}.sub span{color:#60a5fa;font-weight:500}
.layout{display:grid;grid-template-columns:280px 1fr;gap:18px;max-width:1080px;margin:0 auto;align-items:start}
@media(max-width:740px){.layout{grid-template-columns:1fr}}
.card{background:#1a1a2e;border:1px solid #2d2d4a;border-radius:12px;padding:18px;margin-bottom:16px}
.card:last-child{margin-bottom:0}
.card-title{font-size:11px;font-weight:700;color:#6b6b7e;letter-spacing:.08em;text-transform:uppercase;margin-bottom:14px}
.sect{font-size:11px;font-weight:600;color:#4a4a60;letter-spacing:.06em;text-transform:uppercase;margin:16px 0 10px;padding-top:16px;border-top:1px solid #1e1e2e}
.sect:first-child{margin-top:0;padding-top:0;border-top:none}
label{display:block;font-size:11px;color:#6b6b7e;margin-bottom:4px;font-weight:500;text-transform:uppercase;letter-spacing:.05em}
input[type=text],input[type=password],select{width:100%;background:#0f1117;border:1px solid #2d2d4a;border-radius:7px;padding:8px 12px;font-size:13px;color:#e2e2e8;outline:none;transition:border-color .15s}
input:focus,select:focus{border-color:#60a5fa;box-shadow:0 0 0 3px rgba(96,165,250,.12)}
input::placeholder{color:#4a4a60}
.field{margin-bottom:10px}
button{background:#2563eb;color:#fff;border:none;border-radius:7px;padding:8px 16px;font-size:13px;font-weight:600;cursor:pointer;transition:background .15s;white-space:nowrap;width:100%;margin-top:10px}
button:hover{background:#1d4ed8}button:disabled{opacity:.45;cursor:default}
button.secondary{background:#1e1e2e;border:1px solid #2d2d4a;color:#94a3b8}
button.secondary:hover{background:#252535}
button.danger-sm{background:transparent;border:1px solid #7f1d1d;color:#f87171;width:auto;margin:0;padding:3px 8px;font-size:12px;border-radius:5px}
button.danger-sm:hover{background:#7f1d1d}
button.btn-sm{background:#1e1e2e;border:1px solid #2d2d4a;color:#94a3b8;width:auto;margin:0;padding:3px 10px;font-size:12px;border-radius:5px}
button.btn-sm:hover{background:#252535}
.status-row{display:flex;align-items:center;gap:7px;margin-top:10px;padding:8px 12px;background:#0f1117;border:1px solid #1e1e2e;border-radius:7px;font-size:12px}
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.dot.on{background:#10b981;box-shadow:0 0 5px #10b981}.dot.off{background:#374151}
.status-text{color:#6b6b7e;flex:1}.status-text strong{color:#e2e2e8}
.svc-item{display:flex;align-items:center;justify-content:space-between;padding:5px 0;border-bottom:1px solid #1e1e2e;gap:8px}
.svc-item:last-child{border-bottom:none}
.svc-name{font-size:13px;color:#e2e2e8;flex:1}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{background:#111827;border:1px solid #1e293b;border-radius:6px;padding:5px 10px;font-size:12px;color:#94a3b8;cursor:pointer;transition:background .1s}
.chip:hover{background:#1e293b;color:#e2e8f0}
.result{margin-top:14px;padding:14px;background:#111827;border:1px solid #1e293b;border-radius:9px;font-size:14px;line-height:1.7;color:#e2e8f0;display:none}
.result.visible{display:block}
.thinking{color:#6b6b7e;font-style:italic;font-size:13px}
.spinner{display:inline-block;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.fadein{animation:fadein .2s ease}
.digest-entry{padding:10px 12px;background:#0f1117;border:1px solid #1e1e2e;border-radius:8px;margin-bottom:8px;font-size:12px}
.digest-meta{color:#6b6b7e;margin-bottom:6px;display:flex;align-items:center;gap:8px}
.digest-summary{color:#94a3b8;line-height:1.5}
.badge-update{font-size:10px;padding:2px 7px;border-radius:4px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;background:#1e3a5f;color:#60a5fa}
.badge-none{font-size:10px;padding:2px 7px;border-radius:4px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;background:#1e1e2e;color:#6b6b7e}
.digest-updates{margin-top:8px}
.update-block{padding:8px;background:#111827;border-left:2px solid #2563eb;border-radius:0 6px 6px 0;margin-top:6px;white-space:pre-wrap;word-break:break-word;color:#c7d2fe;font-size:12px;line-height:1.6}
</style>
</head>
<body>
<header>
  <h1>IBM What's New Monitor</h1>
  <p class="sub">Powered by <span>CugaAgent</span> · IBM Cloud release notes</p>
</header>

<div class="layout">

  <!-- ══ Left panel ══ -->
  <div>
    <div class="card">

      <div class="sect">Tracked Services</div>
      <div style="display:flex;gap:8px;align-items:center">
        <input id="svcInput" type="text" placeholder="e.g. Event Streams" style="margin:0"
               onkeydown="if(event.key==='Enter')addService()" />
        <button onclick="addService()" style="width:auto;margin:0;padding:8px 12px">+ Add</button>
      </div>
      <div id="svcList" style="margin-top:10px;min-height:20px"></div>

      <div class="sect">Digest Schedule</div>
      <div class="field">
        <select id="scheduleSelect" onchange="setSchedule(this.value)">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="off">Off</option>
        </select>
      </div>
      <button onclick="runDigest()" id="digestBtn" class="secondary">Run Digest Now</button>

      <div class="sect">Email Settings</div>
      <div class="field">
        <label>SMTP Host</label>
        <input id="eHost" type="text" placeholder="smtp.gmail.com" value="smtp.gmail.com" />
      </div>
      <div class="field">
        <label>Username</label>
        <input id="eUser" type="text" placeholder="you@example.com" />
      </div>
      <div class="field">
        <label>Password</label>
        <input id="ePassword" type="password" placeholder="app password" />
      </div>
      <div class="field">
        <label>Send digests to</label>
        <input id="eTo" type="text" placeholder="recipient@example.com" />
      </div>
      <button id="emailSaveBtn" onclick="saveEmail()">Save email settings</button>
      <div class="status-row">
        <span class="dot off" id="emailDot"></span>
        <span class="status-text" id="emailLabel">Not configured</span>
      </div>

    </div>
  </div>

  <!-- ══ Right panel ══ -->
  <div>

    <!-- Chat -->
    <div class="card">
      <div class="card-title">Ask about IBM Cloud Updates</div>
      <div style="display:flex;gap:8px">
        <input id="qInput" type="text" placeholder="What changed in Code Engine this month?"
               onkeydown="if(event.key==='Enter')ask()" style="margin:0" />
        <button onclick="ask()" id="askBtn" style="width:auto;margin:0">Ask</button>
      </div>
      <div class="chips">
        <span class="chip" onclick="qa('What is new in IBM Code Engine in 2026?')">Code Engine</span>
        <span class="chip" onclick="qa('What is new in watsonx.ai recently?')">watsonx.ai</span>
        <span class="chip" onclick="qa('Latest changes to IBM Cloud Object Storage')">Cloud Object Storage</span>
        <span class="chip" onclick="qa('Recent IBM Kubernetes Service release notes')">Kubernetes Service</span>
        <span class="chip" onclick="qa('What changed in IBM Event Streams recently?')">Event Streams</span>
        <span class="chip" onclick="qa('IBM Databases for PostgreSQL recent updates')">Databases for PostgreSQL</span>
        <span class="chip" onclick="qa('Any new IBM Cloud security or IAM features?')">IAM & Security</span>
        <span class="chip" onclick="qa('What IBM Cloud services had breaking changes recently?')">Breaking changes</span>
        <span class="chip" onclick="qa('Summarize IBM Cloud announcements from the past month')">Monthly summary</span>
      </div>
      <div class="result fadein" id="askResult"></div>
      <div id="emailNowRow" style="display:none;margin-top:8px;text-align:right">
        <button class="btn-sm" onclick="emailNow()">Email this</button>
      </div>
    </div>

    <!-- Digest log -->
    <div class="card">
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
    el.innerHTML = '<div style="font-size:12px;color:#4a4a60;padding:4px 0">No services tracked yet</div>'
    return
  }
  el.innerHTML = svcs.map(s => {
    const esc = s.replace(/'/g, "\\'")
    return `<div class="svc-item">
      <span class="svc-name">${s}</span>
      <button class="danger-sm" onclick="removeService('${esc}')">×</button>
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
  result.innerHTML = '<span class="thinking"><span class="spinner">⟳</span> Searching IBM docs…</span>'

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
    result.innerHTML = '<span style="color:#f87171">Error: ' + err.message + '</span>'
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
    .replace(/\\[(.*?)\\]\\((.*?)\\)/g,'<a href="$2" target="_blank" style="color:#60a5fa">$1</a>')
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
    el.innerHTML = '<div style="font-size:12px;color:#4a4a60;padding:4px 0">No digests run yet — click "Run Digest Now" or wait for schedule</div>'
    return
  }
  el.innerHTML = entries.map(e => {
    const ts      = new Date(e.timestamp).toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})
    const hasUpd  = e.updates && e.updates.length > 0
    const badge   = hasUpd
      ? `<span class="badge-update">${e.updates.length} update${e.updates.length > 1 ? 's' : ''}</span>`
      : '<span class="badge-none">no changes</span>'
    const sentTag = e.sent ? ' · <span style="color:#10b981">emailed</span>' : ''
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
</body>
</html>"""
