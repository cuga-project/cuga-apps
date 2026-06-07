"""HTML UI for the Code Engine Deployer.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation. Layout: left compose/classification column, right agent chat.
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { background: var(--cds-background); }

  .layout {
    display: grid; grid-template-columns: 1fr 1fr; gap: var(--cds-sp-06);
    max-width: 90rem; margin: 0 auto; padding: var(--cds-sp-06) var(--cds-sp-06);
  }
  @media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }

  .card {
    background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    overflow: hidden; margin-bottom: var(--cds-sp-05);
  }
  .card-header {
    padding: var(--cds-sp-04) var(--cds-sp-05); border-bottom: 1px solid var(--cds-border-subtle);
    display: flex; align-items: center; gap: var(--cds-sp-03);
  }
  .card-header h2 {
    font-size: 0.875rem; font-weight: 600; color: var(--cds-text-primary);
    letter-spacing: 0.16px;
  }
  .card-body { padding: var(--cds-sp-05); }

  /* Compose path input */
  .row { display: flex; gap: var(--cds-sp-03); align-items: stretch; }
  .row .cds-input { min-height: 2.5rem; font-family: var(--cds-font-mono); font-size: 0.8125rem; }
  .row .cds-btn { flex: none; min-height: 2.5rem; }

  /* Verdict table */
  table.verdict-table { width: 100%; border-collapse: collapse; font-size: 0.75rem; margin-top: var(--cds-sp-05); }
  table.verdict-table th, table.verdict-table td {
    padding: var(--cds-sp-03) var(--cds-sp-04); text-align: left;
    border-bottom: 1px solid var(--cds-border-subtle); vertical-align: top;
  }
  table.verdict-table th {
    font-size: 0.6875rem; text-transform: uppercase; letter-spacing: 0.05em;
    color: var(--cds-text-secondary); font-weight: 600;
    background: var(--cds-layer-accent);
  }
  table.verdict-table tr:last-child td { border-bottom: none; }

  .pill {
    display: inline-flex; align-items: center; height: 1.25rem; padding: 0 var(--cds-sp-03);
    border-radius: 0.9375rem; font-size: 0.625rem; font-weight: 600; letter-spacing: 0.02em;
  }
  .pill-ready { background: var(--cds-support-success-bg); color: var(--cds-support-success); }
  .pill-needs { background: var(--cds-support-warning-bg); color: var(--cds-text-primary); }
  .pill-wont  { background: var(--cds-support-error-bg);   color: var(--cds-support-error); }
  .reason-list { margin: 0; padding-left: var(--cds-sp-05); color: var(--cds-text-secondary); }
  .reason-list li { margin-bottom: var(--cds-sp-01); }

  .summary-row { display: flex; gap: var(--cds-sp-05); font-size: 0.75rem; color: var(--cds-text-secondary); padding: var(--cds-sp-04) 0 0; }
  .summary-pill { display: inline-flex; align-items: center; gap: var(--cds-sp-02); }
  .dot { width: 8px; height: 8px; border-radius: 50%; }
  .dot-ready { background: var(--cds-support-success); }
  .dot-needs { background: var(--cds-support-warning); }
  .dot-wont  { background: var(--cds-support-error); }

  .empty-state { font-size: 0.875rem; color: var(--cds-text-placeholder); text-align: center; padding: var(--cds-sp-08) var(--cds-sp-05); }
  .empty-state strong { color: var(--cds-text-secondary); }
  .err-state {
    font-size: 0.875rem; color: var(--cds-text-primary); padding: var(--cds-sp-04) var(--cds-sp-05);
    background: var(--cds-support-error-bg); border-left: 3px solid var(--cds-support-error);
    margin-top: var(--cds-sp-04);
  }

  /* Chat */
  .chat-thread {
    height: 380px; overflow-y: auto; padding: var(--cds-sp-03);
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    margin-bottom: var(--cds-sp-04);
  }
  .msg { padding: var(--cds-sp-04) var(--cds-sp-04); margin-bottom: var(--cds-sp-03); font-size: 0.875rem; line-height: 1.55; white-space: pre-wrap; }
  .msg-user { background: var(--cds-support-info-bg); color: var(--cds-text-primary); margin-left: 2rem; border-left: 3px solid var(--cds-interactive); }
  .msg-agent { background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle); color: var(--cds-text-primary); margin-right: 2rem; }
  .msg-agent code {
    background: var(--cds-layer-accent); border: 1px solid var(--cds-border-subtle); padding: 1px 5px;
    font-family: var(--cds-font-mono); font-size: 0.6875rem; color: var(--cds-link-primary);
  }
  .msg-agent pre {
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle); padding: var(--cds-sp-03) var(--cds-sp-04);
    overflow-x: auto; margin: var(--cds-sp-03) 0; font-size: 0.6875rem; font-family: var(--cds-font-mono);
  }
  .msg-agent pre code { background: none; border: none; padding: 0; color: var(--cds-text-primary); }
  .msg-agent strong { color: var(--cds-text-primary); font-weight: 600; }
  .msg-agent a { color: var(--cds-link-primary); }
  .msg-agent a:hover { color: var(--cds-link-hover); text-decoration: underline; }
  .msg-agent table { border-collapse: collapse; font-size: 0.6875rem; margin: var(--cds-sp-03) 0; }
  .msg-agent th, .msg-agent td { padding: var(--cds-sp-02) var(--cds-sp-03); border: 1px solid var(--cds-border-subtle); }
  .msg-agent th { background: var(--cds-layer-accent); color: var(--cds-text-primary); }

  /* Quick prompts */
  .chips { display: flex; flex-wrap: wrap; gap: var(--cds-sp-02); margin-bottom: var(--cds-sp-04); }
  .chip {
    padding: var(--cds-sp-02) var(--cds-sp-04); border-radius: 0.9375rem; font-size: 0.75rem;
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle); color: var(--cds-text-secondary);
    cursor: pointer; transition: all var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .chip:hover { background: var(--cds-interactive); border-color: var(--cds-interactive); color: #fff; }

  .spinner { display: none; align-items: center; gap: var(--cds-sp-04); color: var(--cds-text-secondary); padding: var(--cds-sp-04); font-size: 0.75rem; }
  .spinner.vis { display: flex; }
  .spin { width: 14px; height: 14px; border: 2px solid var(--cds-layer-accent); border-top-color: var(--cds-interactive); border-radius: 50%; animation: spin .8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Code&nbsp;Engine&nbsp;Deployer</div>
  <span class="cds-tag cds-tag--blue" id="status-badge">Idle</span>
  <div class="cds-header__actions">
    <span class="cds-helper-01">CUGA agent &middot; deploys docker-compose stacks to IBM Cloud Code Engine</span>
  </div>
</header>

<div class="layout">

  <!-- ── Left: Compose file + classification ────────────────── -->
  <div>

    <div class="card">
      <div class="card-header"><h2>&#x1f4c4; Compose File</h2></div>
      <div class="card-body">
        <div class="row">
          <input type="text" class="cds-input" id="compose-path"
            placeholder="/path/to/docker-compose.yml"
            value="/home/amurthi/work/agent-apps/cuga-apps/docker-compose.yml"
            onkeydown="if(event.key==='Enter')classify()">
          <button class="cds-btn" id="classify-btn" onclick="classify()" style="min-width:7rem">Classify</button>
        </div>
        <div class="summary-row" id="summary-row" style="display:none">
          <span class="summary-pill"><span class="dot dot-ready"></span>
            <span id="count-ready">0</span> ready</span>
          <span class="summary-pill"><span class="dot dot-needs"></span>
            <span id="count-needs">0</span> needs work</span>
          <span class="summary-pill"><span class="dot dot-wont"></span>
            <span id="count-wont">0</span> won't fit</span>
          <span style="margin-left:auto;color:var(--cds-text-placeholder);font-size:0.6875rem"
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
        <button class="cds-btn cds-btn--ghost cds-btn--sm" style="margin-left:auto" onclick="resetThread()">New thread</button>
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
          <input type="text" class="cds-input" id="chat-input"
            placeholder="Ask the agent to triage, deploy, or diagnose&hellip;"
            onkeydown="if(event.key==='Enter')quickAsk()">
          <button class="cds-btn" id="send-btn" onclick="quickAsk()" style="min-width:6rem">Send</button>
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
  b.className = busy ? 'cds-tag cds-tag--yellow' : 'cds-tag cds-tag--blue';
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
              <div style="font-size:0.625rem;color:var(--cds-text-placeholder);font-family:var(--cds-font-mono)">→ ${esc(v.ce_name)}</div>
            </td>
            <td>${pillFor(v.verdict)}</td>
            <td>
              ${v.blockers && v.blockers.length
                ? '<div style="color:var(--cds-support-error);font-size:0.6875rem;margin-bottom:3px"><strong>Blockers:</strong></div>'
                  + '<ul class="reason-list" style="color:var(--cds-support-error)">'
                  + v.blockers.map(r => '<li>'+esc(r)+'</li>').join('') + '</ul>'
                : ''}
              ${v.todos && v.todos.length
                ? '<div style="color:var(--cds-support-warning);font-size:0.6875rem;margin:4px 0 3px"><strong>Todos:</strong></div>'
                  + '<ul class="reason-list">'
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
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("Code Engine Deployer")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
