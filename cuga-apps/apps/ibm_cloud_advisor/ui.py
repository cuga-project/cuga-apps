"""
IBM Cloud Architecture Advisor UI — self-contained HTML page served by FastAPI.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation. Layout: left use-case input column, right architecture
recommendation panel. Behavior, ids, fetch routes and copy are unchanged.
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { background: var(--cds-background); display: flex; flex-direction: column; min-height: 100vh; }

  /* App intro band: one-line blurb + the tools this app uses */
  .app-intro {
    display: flex; align-items: center; gap: var(--cds-sp-05);
    flex-wrap: wrap;
    padding: var(--cds-sp-04) var(--cds-sp-06);
    background: var(--cds-layer-01);
    border-bottom: 1px solid var(--cds-border-subtle);
  }
  .app-intro__blurb {
    font-size: 0.8125rem; color: var(--cds-text-secondary);
    line-height: 1.5; max-width: 48rem;
  }
  .app-intro__blurb strong { color: var(--cds-text-primary); font-weight: 600; }
  .app-intro__tools {
    margin-left: auto; display: flex; flex-wrap: wrap; gap: var(--cds-sp-03);
    align-items: center;
  }
  .app-intro__tools .tools-label {
    font-size: 0.625rem; text-transform: uppercase; letter-spacing: 0.32px;
    color: var(--cds-text-helper); margin-right: var(--cds-sp-02);
  }
  .tool-pill {
    font-size: 0.6875rem; color: var(--cds-text-secondary);
    background: var(--cds-layer-accent); border: 1px solid var(--cds-border-subtle);
    border-radius: 0.9375rem; padding: var(--cds-sp-01) var(--cds-sp-04);
    white-space: nowrap;
  }

  .layout {
    display: grid; grid-template-columns: 380px 1fr; gap: var(--cds-sp-06);
    max-width: 1400px; margin: 0 auto; width: 100%;
    padding: var(--cds-sp-06) var(--cds-sp-06);
    flex: 1; min-height: 0; overflow: hidden;
  }
  @media (max-width: 900px) { .layout { grid-template-columns: 1fr; flex: none; overflow: visible; } }

  .panel { display: flex; flex-direction: column; gap: var(--cds-sp-05); overflow: hidden; }

  .card {
    background: var(--cds-layer-01);
    border: 1px solid var(--cds-border-subtle);
    overflow: hidden;
  }
  .card-header {
    padding: var(--cds-sp-04) var(--cds-sp-05);
    border-bottom: 1px solid var(--cds-border-subtle);
    display: flex; align-items: center; gap: var(--cds-sp-03);
  }
  .card-header h2 {
    font-size: 0.75rem; font-weight: 600; color: var(--cds-text-secondary);
    letter-spacing: 0.32px; text-transform: uppercase;
  }
  .card-body { padding: var(--cds-sp-05); }

  /* Chips */
  .chips { display: flex; flex-wrap: wrap; gap: var(--cds-sp-03); margin-bottom: var(--cds-sp-04); }
  .chip {
    padding: var(--cds-sp-02) var(--cds-sp-04); border-radius: 0.9375rem;
    font-size: 0.75rem; background: var(--cds-layer-02);
    border: 1px solid var(--cds-border-subtle); color: var(--cds-text-secondary);
    cursor: pointer; line-height: 1.4;
    transition: all var(--cds-dur-mod) var(--cds-ease-productive);
  }
  .chip:hover { background: var(--cds-interactive); border-color: var(--cds-interactive); color: #fff; }

  /* Input row */
  .chat-row { display: flex; gap: 0; }
  .chat-input { flex: 1; border-bottom: 1px solid var(--cds-border-strong); }
  .send-btn { flex: none; min-width: 6rem; justify-content: center; text-align: center; }

  /* Status message */
  .status-msg {
    font-size: 0.75rem; color: var(--cds-text-helper); margin-top: var(--cds-sp-03);
    min-height: 18px; display: flex; align-items: center; gap: var(--cds-sp-03);
  }

  /* Right panel — architecture output */
  .result-wrap { flex: 1; overflow-y: auto; padding: 0; }
  .result-empty {
    padding: var(--cds-sp-09) var(--cds-sp-06); text-align: center;
    color: var(--cds-text-placeholder); font-size: 0.875rem; line-height: 1.8;
  }
  .result-empty strong { display: block; color: var(--cds-text-secondary); font-size: 0.9375rem; margin-bottom: var(--cds-sp-02); }
  .arch-card {
    background: var(--cds-layer-02);
    border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-06); margin: var(--cds-sp-05);
  }

  /* Markdown rendering */
  .md h1, .md h2, .md h3 { color: var(--cds-text-primary); font-weight: 600; margin: var(--cds-sp-05) 0 var(--cds-sp-03); }
  .md h1 { font-size: 1.125rem; }
  .md h2 { font-size: 1rem; }
  .md h3 { font-size: 0.875rem; color: var(--cds-link-primary); }
  .md p { color: var(--cds-text-secondary); font-size: 0.875rem; line-height: 1.7; margin-bottom: var(--cds-sp-04); }
  .md ul, .md ol { padding-left: var(--cds-sp-06); margin-bottom: var(--cds-sp-04); }
  .md li { color: var(--cds-text-secondary); font-size: 0.875rem; line-height: 1.7; margin-bottom: var(--cds-sp-02); }
  .md strong { color: var(--cds-text-primary); font-weight: 600; }
  .md em { color: var(--cds-text-secondary); }
  .md a { color: var(--cds-link-primary); text-decoration: none; }
  .md a:hover { color: var(--cds-link-hover); text-decoration: underline; }
  .md code {
    background: var(--cds-layer-accent); color: var(--cds-link-primary);
    padding: 1px 5px; font-size: 0.75rem; font-family: var(--cds-font-mono);
  }
  .md pre {
    background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-05); margin: var(--cds-sp-04) 0; overflow-x: auto;
  }
  .md pre code { background: none; color: var(--cds-text-primary); padding: 0; font-size: 0.75rem; line-height: 1.6; }
  .md hr { border: none; border-top: 1px solid var(--cds-border-subtle); margin: var(--cds-sp-05) 0; }
  .md blockquote {
    border-left: 3px solid var(--cds-interactive); padding-left: var(--cds-sp-04);
    margin: var(--cds-sp-03) 0; color: var(--cds-text-secondary); font-size: 0.875rem;
  }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Cloud&nbsp;Architecture&nbsp;Advisor</div>
  <span class="cds-tag cds-tag--blue">Global Catalog API</span>
  <div class="cds-header__actions">
    <span class="cds-helper-01">Real IBM services · ibmcloud CLI</span>
  </div>
</header>

<div class="app-intro">
  <div class="app-intro__blurb">
    <strong>IBM Cloud Architecture Advisor.</strong> Describe what you want to build
    and get a recommended IBM Cloud architecture — real services, how they connect,
    and ready-to-run ibmcloud CLI commands.
  </div>
  <div class="app-intro__tools">
    <span class="tools-label">Tools</span>
    <span class="tool-pill">📦 IBM Global Catalog API</span>
    <span class="tool-pill">🔎 Web search · Tavily</span>
    <span class="tool-pill">⌨ ibmcloud CLI commands</span>
  </div>
</div>

<div class="layout">

  <!-- ── Left: Chat ────────────────────────────────────────────── -->
  <div class="panel">
    <div class="card">
      <div class="card-header"><h2>💬 Describe Your Use Case</h2></div>
      <div class="card-body">
        <div class="chips">
          <span class="chip" onclick="ask(this.textContent)">IoT sensor pipeline with real-time processing and dashboards</span>
          <span class="chip" onclick="ask(this.textContent)">Serverless web app with auth and a managed database</span>
          <span class="chip" onclick="ask(this.textContent)">Event-driven microservices with a message queue</span>
          <span class="chip" onclick="ask(this.textContent)">ML model training and serving platform</span>
          <span class="chip" onclick="ask(this.textContent)">AWS equivalent: S3 + Lambda + DynamoDB on IBM Cloud</span>
          <span class="chip" onclick="ask(this.textContent)">High-availability web app with CDN and load balancing</span>
          <span class="chip" onclick="ask(this.textContent)">HIPAA-compliant data processing pipeline</span>
          <span class="chip" onclick="ask(this.textContent)">Show Terraform for a Kubernetes workload on IBM Cloud</span>
        </div>
        <div class="chat-row">
          <input class="cds-input chat-input" id="chat-input" type="text"
            placeholder="Describe what you want to build…"
            onkeydown="if(event.key==='Enter')ask()">
          <button class="cds-btn send-btn" id="send-btn" onclick="ask()">Ask</button>
        </div>
        <div class="status-msg" id="status-msg"></div>
      </div>
    </div>
  </div>

  <!-- ── Right: Architecture output ───────────────────────────── -->
  <div class="panel">
    <div class="card" style="flex:1;display:flex;flex-direction:column;overflow:hidden">
      <div class="card-header"><h2>🏗️ Architecture Recommendation</h2></div>
      <div class="result-wrap" id="result-wrap">
        <div class="result-empty" id="result-empty">
          <strong>No recommendation yet</strong>
          Describe your use case on the left — the agent will search the IBM Cloud
          catalog for real services, then design an architecture with CLI commands.<br><br>
          Try: <em>"Serverless web app with auth and a managed database"</em>
        </div>
      </div>
    </div>
  </div>

</div>

<script>
function esc(s){
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function mdToHtml(text) {
  let t = text;
  // code blocks first (before inline)
  t = t.replace(/```(\w*)\n?([\s\S]*?)```/g, (_,lang,code)=>{
    return `<pre><code class="lang-${esc(lang)}">${esc(code.trim())}</code></pre>`;
  });
  // headings
  t = t.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  t = t.replace(/^## (.+)$/gm,  '<h2>$1</h2>');
  t = t.replace(/^# (.+)$/gm,   '<h1>$1</h1>');
  // bold+italic
  t = t.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  t = t.replace(/\*\*(.+?)\*\*/g,     '<strong>$1</strong>');
  t = t.replace(/\*(.+?)\*/g,         '<em>$1</em>');
  // inline code
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
  // links
  t = t.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // hr
  t = t.replace(/^---+$/gm, '<hr>');
  // blockquote
  t = t.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
  // lists — collect consecutive bullet lines
  t = t.replace(/((?:^[ \t]*[-*] .+\n?)+)/gm, block => {
    const items = block.trim().split('\n').map(l=>
      `<li>${l.replace(/^[ \t]*[-*] /,'')}</li>`
    ).join('');
    return `<ul>${items}</ul>`;
  });
  // paragraphs (blank-line separated)
  t = t.split(/\n{2,}/).map(chunk=>{
    chunk = chunk.trim();
    if(!chunk) return '';
    if(/^<(h[1-6]|ul|ol|pre|hr|blockquote)/.test(chunk)) return chunk;
    return `<p>${chunk.replace(/\n/g,' ')}</p>`;
  }).join('\n');
  return t;
}

async function ask(question) {
  const inp  = document.getElementById('chat-input');
  const btn  = document.getElementById('send-btn');
  const stat = document.getElementById('status-msg');
  const q    = question || inp.value.trim();
  if (!q) return;
  inp.value = '';
  btn.disabled = true;
  btn.textContent = '…';
  stat.innerHTML = '<div class="cds-spinner cds-spinner--sm"></div> Searching IBM catalog…';

  try {
    const r = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: q}),
    });
    const d = await r.json();
    renderResult(q, d.answer || d.error || '(no response)');
    stat.innerHTML = '';
  } catch(e) {
    stat.innerHTML = `<span style="color:var(--cds-support-error)">Error: ${esc(e.message)}</span>`;
  }
  btn.disabled = false;
  btn.textContent = 'Ask';
}

function renderResult(question, answer) {
  const wrap = document.getElementById('result-wrap');
  wrap.innerHTML = `
    <div class="arch-card">
      <p style="font-size:0.75rem;color:var(--cds-text-helper);margin-bottom:12px;font-style:italic">
        Q: ${esc(question)}
      </p>
      <div class="md">${mdToHtml(answer)}</div>
    </div>`;
}
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("IBM Cloud Architecture Advisor")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
