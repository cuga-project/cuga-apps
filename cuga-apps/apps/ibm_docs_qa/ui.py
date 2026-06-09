"""
IBM Docs Q&A UI — self-contained HTML page served by FastAPI.

Carbonized: IBM Carbon Design System (White / g10 light theme) via the shared
`_carbon` foundation. Layout: left chat input + history column, right answer panel.
"""

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body { background: var(--cds-background); display: flex; flex-direction: column; }

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
    display: grid; grid-template-columns: 360px 1fr; gap: var(--cds-sp-06);
    max-width: 88rem; margin: 0 auto; width: 100%;
    padding: var(--cds-sp-06) var(--cds-sp-06);
    flex: 1; min-height: 0; overflow: hidden;
  }
  @media (max-width: 900px) { .layout { grid-template-columns: 1fr; flex: none; overflow: visible; } }

  .panel { display: flex; flex-direction: column; gap: var(--cds-sp-05); overflow: hidden; }

  .card {
    background: var(--cds-layer-01); border: 1px solid var(--cds-border-subtle);
    overflow: hidden; display: flex; flex-direction: column;
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
  .chat-row .send-btn { flex: none; min-width: 5rem; }

  /* Status */
  .status-msg {
    font-size: 0.75rem; color: var(--cds-text-helper); margin-top: var(--cds-sp-03);
    min-height: 18px; display: flex; align-items: center; gap: var(--cds-sp-03);
  }

  /* Chat history in left panel */
  .chat-history {
    flex: 1; overflow-y: auto; display: flex; flex-direction: column;
    gap: var(--cds-sp-04); padding-top: var(--cds-sp-02);
  }
  .msg { padding: var(--cds-sp-03) var(--cds-sp-04); font-size: 0.8125rem; line-height: 1.6; }
  .msg-user {
    background: var(--cds-support-info-bg); color: var(--cds-text-primary);
    align-self: flex-end; max-width: 95%;
    border-left: 2px solid var(--cds-interactive);
  }
  .msg-agent {
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    color: var(--cds-text-secondary); align-self: flex-start; max-width: 100%;
  }
  .history-placeholder {
    font-size: 0.75rem; color: var(--cds-text-placeholder);
    text-align: center; padding: var(--cds-sp-05) 0;
  }

  /* Right: answer panel */
  .answer-wrap { flex: 1; overflow-y: auto; padding: var(--cds-sp-05); }
  .answer-empty {
    padding: var(--cds-sp-09) var(--cds-sp-06); text-align: center;
    color: var(--cds-text-placeholder); font-size: 0.875rem; line-height: 1.8;
  }
  .answer-empty strong { display: block; color: var(--cds-text-secondary); font-size: 1rem; margin-bottom: var(--cds-sp-03); }
  .answer-empty em { color: var(--cds-text-secondary); font-style: normal; font-family: var(--cds-font-mono); }
  .answer-card {
    background: var(--cds-layer-02); border: 1px solid var(--cds-border-subtle);
    padding: var(--cds-sp-06); margin-bottom: var(--cds-sp-05);
  }
  .answer-q {
    font-size: 0.75rem; color: var(--cds-text-helper); font-style: italic;
    margin-bottom: var(--cds-sp-05); padding-bottom: var(--cds-sp-04);
    border-bottom: 1px solid var(--cds-border-subtle);
  }

  /* Markdown */
  .md h1, .md h2, .md h3 { color: var(--cds-text-primary); font-weight: 600; margin: var(--cds-sp-05) 0 var(--cds-sp-03); }
  .md h1 { font-size: 1rem; } .md h2 { font-size: 0.9375rem; } .md h3 { font-size: 0.875rem; color: var(--cds-link-primary); }
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
    margin: var(--cds-sp-03) 0; color: var(--cds-text-helper); font-size: 0.875rem;
  }
  .md table { width: 100%; border-collapse: collapse; margin: var(--cds-sp-04) 0; font-size: 0.75rem; }
  .md th {
    background: var(--cds-layer-accent); color: var(--cds-text-primary);
    padding: var(--cds-sp-03) var(--cds-sp-04); text-align: left;
    border: 1px solid var(--cds-border-subtle); font-weight: 600;
  }
  .md td { padding: var(--cds-sp-03) var(--cds-sp-04); border: 1px solid var(--cds-border-subtle); color: var(--cds-text-secondary); }
  .md tr:nth-child(even) td { background: var(--cds-layer-01); }

  /* Sources section */
  .sources { margin-top: var(--cds-sp-05); padding-top: var(--cds-sp-04); border-top: 1px solid var(--cds-border-subtle); }
  .sources-label {
    font-size: 0.75rem; font-weight: 600; color: var(--cds-text-helper);
    letter-spacing: 0.32px; text-transform: uppercase; margin-bottom: var(--cds-sp-03);
  }
  .source-item { display: flex; gap: var(--cds-sp-03); align-items: flex-start; margin-bottom: var(--cds-sp-02); }
  .source-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--cds-interactive); flex-shrink: 0; margin-top: 6px; }
  .source-link { font-size: 0.75rem; color: var(--cds-link-primary); text-decoration: none; line-height: 1.5; }
  .source-link:hover { color: var(--cds-link-hover); text-decoration: underline; }
</style>"""

_BODY = r"""
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Docs&nbsp;Q&amp;A</div>
  <span class="cds-tag cds-tag--blue">ibm.com · cloud.ibm.com</span>
  <div class="cds-header__actions">
    <span class="cds-helper-01">Searches real IBM docs · follow-up supported</span>
  </div>
</header>

<div class="app-intro">
  <div class="app-intro__blurb">
    <strong>IBM Docs Q&amp;A.</strong> Ask any IBM Cloud question in plain English — the agent searches real IBM documentation, fetches the relevant pages, and synthesises a precise answer with source links.
  </div>
  <div class="app-intro__tools">
    <span class="tools-label">Tools</span>
    <span class="tool-pill">🔎 Web search · Tavily</span>
    <span class="tool-pill">📄 Fetch IBM docs</span>
    <span class="tool-pill">🏷 site:ibm.com filter</span>
  </div>
</div>

<div class="layout">

  <!-- ── Left: Chat input + history ───────────────────────────── -->
  <div class="panel">
    <div class="card">
      <div class="card-header"><h2>💬 Ask IBM Docs</h2></div>
      <div class="card-body">
        <div class="chips">
          <span class="chip" onclick="ask(this.textContent)">How do I set up a private endpoint for Cloud Object Storage?</span>
          <span class="chip" onclick="ask(this.textContent)">What are the Lite plan limits for Watson Discovery?</span>
          <span class="chip" onclick="ask(this.textContent)">How does IBM Cloud IAM service ID authentication work?</span>
          <span class="chip" onclick="ask(this.textContent)">Code Engine: Dockerfile vs Buildpacks — which should I use?</span>
          <span class="chip" onclick="ask(this.textContent)">How do I connect IBM Databases for PostgreSQL to Code Engine?</span>
          <span class="chip" onclick="ask(this.textContent)">What regions support IBM Cloud Kubernetes Service?</span>
          <span class="chip" onclick="ask(this.textContent)">How does IBM Event Streams differ from Apache Kafka?</span>
          <span class="chip" onclick="ask(this.textContent)">What is IBM watsonx.ai and how do I get started?</span>
        </div>
        <div class="chat-row">
          <input class="cds-input chat-input" id="chat-input" type="text"
            placeholder="Ask any IBM Cloud question…"
            onkeydown="if(event.key==='Enter')ask()">
          <button class="cds-btn send-btn" id="send-btn" onclick="ask()">Ask</button>
        </div>
        <div class="status-msg" id="status-msg"></div>
      </div>
    </div>

    <div class="card" style="flex:1;overflow:hidden">
      <div class="card-header"><h2>🗂 Question History</h2></div>
      <div class="card-body" style="flex:1;overflow-y:auto;padding-top:10px">
        <div class="chat-history" id="chat-history">
          <div class="history-placeholder">
            Questions will appear here
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Right: Answer panel ───────────────────────────────────── -->
  <div class="panel">
    <div class="card" style="flex:1;overflow:hidden">
      <div class="card-header"><h2>📄 Answer from IBM Docs</h2></div>
      <div class="answer-wrap" id="answer-wrap">
        <div class="answer-empty" id="answer-empty">
          <strong>No answer yet</strong>
          Ask a question on the left — the agent will search IBM documentation,
          fetch the relevant pages, and synthesise a precise answer with source links.<br><br>
          Try: <em>"How do I set up a private endpoint for Cloud Object Storage?"</em>
        </div>
      </div>
    </div>
  </div>

</div>

<script>
const _history = [];

function esc(s){
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function mdToHtml(text) {
  let t = text;
  // code blocks
  t = t.replace(/```(\w*)\n?([\s\S]*?)```/g, (_,lang,code)=>{
    return `<pre><code class="lang-${esc(lang)}">${esc(code.trim())}</code></pre>`;
  });
  // headings
  t = t.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  t = t.replace(/^## (.+)$/gm,  '<h2>$1</h2>');
  t = t.replace(/^# (.+)$/gm,   '<h1>$1</h1>');
  // bold/italic
  t = t.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  t = t.replace(/\*\*(.+?)\*\*/g,     '<strong>$1</strong>');
  t = t.replace(/\*(.+?)\*/g,         '<em>$1</em>');
  // inline code
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
  // links
  t = t.replace(/\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // hr
  t = t.replace(/^---+$/gm, '<hr>');
  // blockquote
  t = t.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
  // tables (basic)
  t = t.replace(/((?:^\|.+\|\n?)+)/gm, block => {
    const rows = block.trim().split('\n').filter(r=>r.trim() && !r.match(/^\|[-| :]+\|$/));
    if(!rows.length) return block;
    const [hdr, ...body] = rows;
    const th = hdr.split('|').filter((_,i,a)=>i>0&&i<a.length-1)
                  .map(c=>`<th>${c.trim()}</th>`).join('');
    const trs = body.map(r=>{
      const tds = r.split('|').filter((_,i,a)=>i>0&&i<a.length-1)
                    .map(c=>`<td>${c.trim()}</td>`).join('');
      return `<tr>${tds}</tr>`;
    }).join('');
    return `<table><thead><tr>${th}</tr></thead><tbody>${trs}</tbody></table>`;
  });
  // lists
  t = t.replace(/((?:^[ \t]*\d+\. .+\n?)+)/gm, block => {
    const items = block.trim().split('\n').map(l=>
      `<li>${l.replace(/^[ \t]*\d+\. /,'')}</li>`
    ).join('');
    return `<ol>${items}</ol>`;
  });
  t = t.replace(/((?:^[ \t]*[-*] .+\n?)+)/gm, block => {
    const items = block.trim().split('\n').map(l=>
      `<li>${l.replace(/^[ \t]*[-*] /,'')}</li>`
    ).join('');
    return `<ul>${items}</ul>`;
  });
  // paragraphs
  t = t.split(/\n{2,}/).map(chunk=>{
    chunk = chunk.trim();
    if(!chunk) return '';
    if(/^<(h[1-6]|ul|ol|pre|hr|table|blockquote)/.test(chunk)) return chunk;
    return `<p>${chunk.replace(/\n/g,' ')}</p>`;
  }).join('\n');
  return t;
}

function extractSources(answer) {
  // Pull out markdown links that look like ibm.com URLs for the sources panel
  const re = /\[([^\]]+)\]\((https?:\/\/[^\)]*ibm\.com[^\)]*)\)/g;
  const seen = new Set();
  const sources = [];
  let m;
  while((m = re.exec(answer)) !== null) {
    if(!seen.has(m[2])) {
      seen.add(m[2]);
      sources.push({title: m[1], url: m[2]});
    }
  }
  return sources;
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
  stat.innerHTML = '<div class="cds-spinner cds-spinner--sm"></div> Searching IBM docs…';

  // Add to history immediately
  addHistoryItem(q, null);

  try {
    const r = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: q}),
    });
    const d = await r.json();
    const answer = d.answer || d.error || '(no response)';
    updateHistoryItem(q);
    renderAnswer(q, answer);
    stat.innerHTML = '';
  } catch(e) {
    stat.innerHTML = `<span style="color:var(--cds-support-error)">Error: ${esc(e.message)}</span>`;
  }
  btn.disabled = false;
  btn.textContent = 'Ask';
}

function addHistoryItem(q, status) {
  const hist = document.getElementById('chat-history');
  // Clear placeholder
  if(hist.children.length === 1 && hist.children[0].classList.contains('history-placeholder')) {
    hist.innerHTML = '';
  }
  const div = document.createElement('div');
  div.className = 'msg msg-user';
  div.dataset.q = q;
  div.textContent = q;
  hist.appendChild(div);
  hist.scrollTop = hist.scrollHeight;
}

function updateHistoryItem(q) {
  // no-op — could add checkmark indicator here
}

function renderAnswer(question, answer) {
  const wrap = document.getElementById('answer-wrap');
  const sources = extractSources(answer);
  const sourcesHtml = sources.length ? `
    <div class="sources">
      <div class="sources-label">Sources</div>
      ${sources.map(s=>`
        <div class="source-item">
          <div class="source-dot"></div>
          <a class="source-link" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>
        </div>`).join('')}
    </div>` : '';

  wrap.innerHTML = `
    <div class="answer-card">
      <div class="answer-q">Q: ${esc(question)}</div>
      <div class="md">${mdToHtml(answer)}</div>
      ${sourcesHtml}
    </div>`;
  wrap.scrollTop = 0;
}
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("IBM Docs Q&A")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)
