"""HTML UI for the Code Engine Deployer. Self-contained — no external deps."""

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Code Engine Deployer</title>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    background:#0f1117;color:#e2e8f0;min-height:100vh}

  header{background:#1a1a2e;border-bottom:1px solid #2d2d4a;padding:14px 28px;
    display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}
  header h1{font-size:16px;font-weight:700;color:#fff}
  .badge{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
  .badge-blue{background:#1e3a5f;color:#60a5fa}
  .spacer{flex:1}
  .hdr-stat{font-size:11px;color:#4b5563}

  .layout{display:grid;grid-template-columns:1fr 1fr;gap:20px;
    max-width:1400px;margin:0 auto;padding:20px 24px}

  .card{background:#1a1a2e;border:1px solid #2d2d4a;border-radius:10px;
    overflow:hidden;margin-bottom:16px}
  .card-header{padding:12px 16px 10px;border-bottom:1px solid #2d2d4a;
    display:flex;align-items:center;gap:8px}
  .card-header h2{font-size:13px;font-weight:600;color:#c5cae9}
  .card-body{padding:16px}

  /* Compose path input */
  .row{display:flex;gap:8px;align-items:center}
  input[type=text]{flex:1;padding:8px 12px;border-radius:7px;font-size:13px;
    background:#0f1117;border:1px solid #374151;color:#e2e8f0;outline:none;
    font-family:'JetBrains Mono','Fira Code','Courier New',monospace}
  input[type=text]:focus{border-color:#7c3aed}
  .btn{padding:8px 16px;border-radius:7px;font-size:13px;cursor:pointer;
    border:none;background:#7c3aed;color:#fff;white-space:nowrap;
    font-weight:500;transition:background .15s}
  .btn:hover{background:#6d28d9}
  .btn:disabled{background:#374151;color:#6b7280;cursor:default}
  .btn-ghost{background:#1f2937;border:1px solid #374151;color:#9ca3af}
  .btn-ghost:hover{background:#374151;color:#e2e8f0}
  .btn-sm{padding:4px 12px;font-size:11px}

  /* Verdict table */
  table.verdict-table{width:100%;border-collapse:collapse;font-size:12px;
    margin-top:12px}
  table.verdict-table th,table.verdict-table td{padding:8px 10px;text-align:left;
    border-bottom:1px solid #2d2d4a;vertical-align:top}
  table.verdict-table th{font-size:11px;text-transform:uppercase;letter-spacing:0.05em;
    color:#9ca3af;font-weight:600}
  table.verdict-table tr:last-child td{border-bottom:none}
  .pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;
    font-weight:600;letter-spacing:0.02em}
  .pill-ready{background:#052e16;color:#4ade80}
  .pill-needs{background:#451a03;color:#fb923c}
  .pill-wont{background:#7f1d1d;color:#f87171}
  .reason-list{margin:0;padding-left:14px;color:#9ca3af}
  .reason-list li{margin-bottom:2px}

  .summary-row{display:flex;gap:14px;font-size:12px;color:#9ca3af;
    padding:6px 0 0}
  .summary-pill{display:inline-flex;align-items:center;gap:5px}
  .dot{width:8px;height:8px;border-radius:50%}
  .dot-ready{background:#4ade80}
  .dot-needs{background:#fb923c}
  .dot-wont{background:#f87171}

  .empty-state{font-size:13px;color:#4b5563;text-align:center;padding:40px 20px}
  .err-state{font-size:13px;color:#f87171;padding:14px;background:#2a0f0f;
    border:1px solid #7f1d1d;border-radius:7px;margin-top:10px}

  /* Chat */
  .chat-thread{height:380px;overflow-y:auto;padding:8px;background:#0a0a14;
    border:1px solid #2d2d4a;border-radius:7px;margin-bottom:10px}
  .msg{padding:10px 12px;border-radius:7px;margin-bottom:8px;font-size:13px;
    line-height:1.55;white-space:pre-wrap}
  .msg-user{background:#1e3a5f;color:#dbeafe;margin-left:30px}
  .msg-agent{background:#1a1a2e;border:1px solid #2d2d4a;color:#e2e8f0;
    margin-right:30px}
  .msg-agent code{background:#0a0a14;border:1px solid #374151;padding:1px 5px;
    border-radius:3px;font-family:'JetBrains Mono','Courier New',monospace;
    font-size:11px;color:#86efac}
  .msg-agent pre{background:#0a0a14;border:1px solid #374151;padding:8px 10px;
    border-radius:5px;overflow-x:auto;margin:6px 0;font-size:11px}
  .msg-agent strong{color:#e2e8f0}
  .msg-agent a{color:#60a5fa}
  .msg-agent table{border-collapse:collapse;font-size:11px;margin:6px 0}
  .msg-agent th,.msg-agent td{padding:4px 8px;border:1px solid #374151}
  .msg-agent th{background:#1f2937;color:#c5cae9}

  /* Quick prompts */
  .chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px}
  .chip{padding:4px 10px;border-radius:12px;font-size:11px;background:#1f2937;
    border:1px solid #374151;color:#9ca3af;cursor:pointer;transition:all .15s}
  .chip:hover{background:#7c3aed;border-color:#7c3aed;color:#fff}

  .spinner{display:none;align-items:center;gap:10px;color:#6b7280;
    padding:10px;font-size:12px}
  .spinner.vis{display:flex}
  .spin{width:14px;height:14px;border:2px solid #2d2d4a;border-top-color:#7c3aed;
    border-radius:50%;animation:spin .8s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>

<header>
  <h1>&#x1f680; Code Engine Deployer</h1>
  <span class="badge badge-blue" id="status-badge">Idle</span>
  <div class="spacer"></div>
  <span class="hdr-stat">CUGA agent &middot; deploys docker-compose stacks to IBM Cloud Code Engine</span>
</header>

<div class="layout">

  <!-- ── Left: Compose file + classification ────────────────── -->
  <div>

    <div class="card">
      <div class="card-header"><h2>&#x1f4c4; Compose File</h2></div>
      <div class="card-body">
        <div class="row">
          <input type="text" id="compose-path"
            placeholder="/path/to/docker-compose.yml"
            value="/home/amurthi/work/agent-apps/cuga-apps/docker-compose.yml"
            onkeydown="if(event.key==='Enter')classify()">
          <button class="btn" id="classify-btn" onclick="classify()">Classify</button>
        </div>
        <div class="summary-row" id="summary-row" style="display:none">
          <span class="summary-pill"><span class="dot dot-ready"></span>
            <span id="count-ready">0</span> ready</span>
          <span class="summary-pill"><span class="dot dot-needs"></span>
            <span id="count-needs">0</span> needs work</span>
          <span class="summary-pill"><span class="dot dot-wont"></span>
            <span id="count-wont">0</span> won't fit</span>
          <span style="margin-left:auto;color:#4b5563;font-size:11px"
            id="project-tag"></span>
        </div>
        <div id="verdict-area">
          <div class="empty-state">
            Enter a docker-compose.yml path and click <strong>Classify</strong>
            to see which services are ready for Code Engine.
          </div>
        </div>
      </div>
    </div>

  </div><!-- /left -->

  <!-- ── Right: Chat with agent ──────────────────────────────── -->
  <div>

    <div class="card">
      <div class="card-header">
        <h2>&#x1f4ac; Deploy with the Agent</h2>
        <button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="resetThread()">New thread</button>
      </div>
      <div class="card-body">
        <div class="chips">
          <span class="chip" onclick="quickAsk('Classify the compose file at the path above and show me the verdict table.')">Classify the compose file</span>
          <span class="chip" onclick="quickAsk('Check that ibmcloud and docker are installed and that I am logged in.')">Check prereqs</span>
          <span class="chip" onclick="quickAsk('List my Code Engine projects.')">List CE projects</span>
          <span class="chip" onclick="quickAsk('Deploy just the CE-ready services to my targeted project. Confirm scope before doing anything.')">Deploy CE-ready services</span>
          <span class="chip" onclick="quickAsk('My last deploy is failing — read the events and logs and tell me what is wrong.')">Diagnose a failure</span>
          <span class="chip" onclick="quickAsk('Walk me through a one-time setup: ICR namespace, registry secret, env secret from .env.')">First-time ICR setup</span>
        </div>

        <div class="chat-thread" id="chat-thread">
          <div class="msg msg-agent">
            <strong>Hello.</strong> Drop a docker-compose.yml path on the left and click
            Classify to see what fits Code Engine. Then ask me to deploy the
            ready set, walk through architectural mismatches, or diagnose a
            failed deploy. I shell out to <code>ibmcloud</code> and
            <code>docker</code> on this machine; you stay in the loop for
            every command.
          </div>
        </div>

        <div class="spinner" id="spinner"><div class="spin"></div>
          <span>Thinking&hellip;</span></div>

        <div class="row">
          <input type="text" id="chat-input"
            placeholder="Ask the agent to triage, deploy, or diagnose&hellip;"
            onkeydown="if(event.key==='Enter')quickAsk()">
          <button class="btn" id="send-btn" onclick="quickAsk()">Send</button>
        </div>
      </div>
    </div>

  </div><!-- /right -->

</div>

<script>
let _threadId = 'thread-' + Math.random().toString(36).slice(2, 10);

function setStatus(text, busy) {
  const b = document.getElementById('status-badge');
  b.textContent = text;
  b.style.background = busy ? '#451a03' : '#1e3a5f';
  b.style.color      = busy ? '#fb923c' : '#60a5fa';
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Markdown-ish renderer for agent replies ────────────────────────
function renderMarkdown(text) {
  if (!text) return '';
  let html = esc(text);
  // Code blocks
  html = html.replace(/```[\w]*\n([\s\S]*?)```/g, (_, code) =>
    '<pre><code>' + code + '</code></pre>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // ### headings
  html = html.replace(/^### (.+)$/gm, '<strong>$1</strong>');
  // **bold**
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // links [text](url)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // simple table support: header | header  with --- separator
  html = html.replace(
    /((?:^\|.+\|\n)+)/gm,
    function(block) {
      const rows = block.trim().split('\n').map(r =>
        r.replace(/^\||\|$/g, '').split('|').map(c => c.trim())
      );
      if (rows.length < 2 || !/^[\s\-|:]+$/.test(rows[1].join('|'))) return block;
      const head = '<tr>' + rows[0].map(c => '<th>'+c+'</th>').join('') + '</tr>';
      const body = rows.slice(2).map(r =>
        '<tr>' + r.map(c => '<td>'+c+'</td>').join('') + '</tr>').join('');
      return '<table>' + head + body + '</table>';
    });
  return html;
}

// ── Classify panel ─────────────────────────────────────────────────
async function classify() {
  const path = document.getElementById('compose-path').value.trim();
  const area = document.getElementById('verdict-area');
  if (!path) return;
  setStatus('Classifying', true);
  document.getElementById('classify-btn').disabled = true;
  try {
    const r = await fetch('/classify', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ path }),
    });
    if (!r.ok) {
      const e = await r.json();
      area.innerHTML = '<div class="err-state">' + esc(e.error || 'parse failed') + '</div>';
      document.getElementById('summary-row').style.display = 'none';
      setStatus('Idle', false);
      return;
    }
    const d = await r.json();
    renderVerdicts(d);
    setStatus('Classified', false);
  } catch (e) {
    area.innerHTML = '<div class="err-state">' + esc(e.message) + '</div>';
    setStatus('Idle', false);
  } finally {
    document.getElementById('classify-btn').disabled = false;
  }
}

function renderVerdicts(d) {
  const verdicts = d.verdicts || [];
  const counts = { ce_ready:0, needs_work:0, wont_fit:0 };
  verdicts.forEach(v => counts[v.verdict] = (counts[v.verdict]||0) + 1);
  document.getElementById('count-ready').textContent = counts.ce_ready;
  document.getElementById('count-needs').textContent = counts.needs_work;
  document.getElementById('count-wont').textContent  = counts.wont_fit;
  document.getElementById('project-tag').textContent =
    'project: ' + (d.project_name || '?') + ' · ' + verdicts.length + ' service(s)';
  document.getElementById('summary-row').style.display = 'flex';

  const pillFor = v => v === 'ce_ready'   ? '<span class="pill pill-ready">CE-ready</span>'
                     : v === 'needs_work' ? '<span class="pill pill-needs">needs work</span>'
                                          : '<span class="pill pill-wont">won\'t fit</span>';
  const html = `
    <table class="verdict-table">
      <thead>
        <tr><th>Service</th><th>Verdict</th><th>Notes</th></tr>
      </thead>
      <tbody>
        ${verdicts.map(v => `
          <tr>
            <td><strong>${esc(v.service_name)}</strong>
              <div style="font-size:10px;color:#4b5563;font-family:monospace">→ ${esc(v.ce_name)}</div>
            </td>
            <td>${pillFor(v.verdict)}</td>
            <td>
              ${v.blockers && v.blockers.length
                ? '<div style="color:#f87171;font-size:11px;margin-bottom:3px"><strong>Blockers:</strong></div>'
                  + '<ul class="reason-list" style="color:#fca5a5">'
                  + v.blockers.map(r => '<li>'+esc(r)+'</li>').join('') + '</ul>'
                : ''}
              ${v.todos && v.todos.length
                ? '<div style="color:#fb923c;font-size:11px;margin:4px 0 3px"><strong>Todos:</strong></div>'
                  + '<ul class="reason-list" style="color:#fcd34d">'
                  + v.todos.map(r => '<li>'+esc(r)+'</li>').join('') + '</ul>'
                : ''}
              ${v.reasons && v.reasons.length
                ? '<ul class="reason-list" style="margin-top:4px">'
                  + v.reasons.map(r => '<li>'+esc(r)+'</li>').join('') + '</ul>'
                : ''}
            </td>
          </tr>`).join('')}
      </tbody>
    </table>`;
  document.getElementById('verdict-area').innerHTML = html;
}

// ── Chat ────────────────────────────────────────────────────────────
function appendMsg(role, text) {
  const cls = role === 'user' ? 'msg msg-user' : 'msg msg-agent';
  const html = role === 'user' ? esc(text) : renderMarkdown(text);
  const node = document.createElement('div');
  node.className = cls;
  node.innerHTML = html;
  const thread = document.getElementById('chat-thread');
  thread.appendChild(node);
  thread.scrollTop = thread.scrollHeight;
}

async function quickAsk(preset) {
  const inp = document.getElementById('chat-input');
  const q   = preset || inp.value.trim();
  if (!q) return;
  inp.value = '';
  appendMsg('user', q);

  const composePath = document.getElementById('compose-path').value.trim();
  // Send the compose path along so the agent has it without re-asking.
  const fullQ = composePath
    ? q + '\n\n[context: compose file path = ' + composePath + ']'
    : q;

  const sendBtn = document.getElementById('send-btn');
  const spin = document.getElementById('spinner');
  sendBtn.disabled = true;
  spin.classList.add('vis');
  setStatus('Thinking', true);

  try {
    const r = await fetch('/ask', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ question: fullQ, thread_id: _threadId }),
    });
    const d = await r.json();
    if (d.error) {
      appendMsg('agent', '**Error:** ' + d.error);
    } else {
      appendMsg('agent', d.answer || '(no response)');
    }
  } catch (e) {
    appendMsg('agent', '**Network error:** ' + e.message);
  } finally {
    spin.classList.remove('vis');
    sendBtn.disabled = false;
    setStatus('Idle', false);
  }
}

function resetThread() {
  _threadId = 'thread-' + Math.random().toString(36).slice(2, 10);
  document.getElementById('chat-thread').innerHTML =
    '<div class="msg msg-agent">New thread started. The agent has no memory of the previous turns.</div>';
}
</script>
</body>
</html>"""
