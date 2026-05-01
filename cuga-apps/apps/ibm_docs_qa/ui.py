"""
IBM Docs Q&A UI — self-contained HTML page served by FastAPI.
"""

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IBM Docs Q&A</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#0f1117;color:#e2e8f0;min-height:100vh}

header{background:#1a1a2e;border-bottom:1px solid #2d2d4a;padding:14px 28px;
  display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}
header h1{font-size:16px;font-weight:700;color:#fff}
.ibm-logo{font-size:13px;font-weight:800;color:#1d4ed8;letter-spacing:.04em}
.badge{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
.badge-blue{background:#1e3a5f;color:#60a5fa}
.spacer{flex:1}
.hdr-hint{font-size:11px;color:#4b5563}

.layout{display:grid;grid-template-columns:360px 1fr;gap:20px;
  max-width:1400px;margin:0 auto;padding:20px 24px;
  height:calc(100vh - 57px);overflow:hidden}
@media(max-width:900px){.layout{grid-template-columns:1fr;height:auto;overflow:visible}}

.panel{display:flex;flex-direction:column;gap:16px;overflow:hidden}

.card{background:#1a1a2e;border:1px solid #2d2d4a;border-radius:10px;overflow:hidden}
.card-header{padding:12px 16px;border-bottom:1px solid #2d2d4a;
  display:flex;align-items:center;gap:8px}
.card-header h2{font-size:12px;font-weight:700;color:#94a3b8;letter-spacing:.06em;
  text-transform:uppercase}
.card-body{padding:16px}

/* Chips */
.chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:12px}
.chip{padding:4px 10px;border-radius:12px;font-size:11px;background:#111827;
  border:1px solid #1e293b;color:#94a3b8;cursor:pointer;transition:all .15s;
  line-height:1.4}
.chip:hover{background:#1d4ed8;border-color:#1d4ed8;color:#fff}

/* Input row */
.chat-row{display:flex;gap:8px}
.chat-input{flex:1;padding:9px 13px;border-radius:7px;font-size:13px;
  background:#0f1117;border:1px solid #374151;color:#e2e8f0;outline:none;
  transition:border-color .15s}
.chat-input:focus{border-color:#1d4ed8;box-shadow:0 0 0 3px rgba(29,78,216,.15)}
.chat-input::placeholder{color:#4b5563}
.send-btn{padding:9px 18px;border-radius:7px;font-size:13px;font-weight:600;
  cursor:pointer;border:none;background:#1d4ed8;color:#fff;white-space:nowrap;
  transition:background .15s}
.send-btn:hover{background:#1e40af}
.send-btn:disabled{background:#374151;color:#6b7280;cursor:default}

/* Status */
.status-msg{font-size:12px;color:#6b7280;margin-top:8px;min-height:18px;
  display:flex;align-items:center;gap:6px}
.spinner{width:12px;height:12px;border:2px solid #374151;border-top-color:#60a5fa;
  border-radius:50%;animation:spin .7s linear infinite;flex-shrink:0}
@keyframes spin{to{transform:rotate(360deg)}}

/* Chat history in left panel */
.chat-history{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:10px;
  padding-top:4px}
.msg{border-radius:8px;padding:10px 13px;font-size:13px;line-height:1.6}
.msg-user{background:#1e3a5f;color:#bfdbfe;align-self:flex-end;max-width:95%;
  border-bottom-right-radius:2px}
.msg-agent{background:#1a1a2e;border:1px solid #2d2d4a;color:#cbd5e1;
  align-self:flex-start;max-width:100%;border-bottom-left-radius:2px}

/* Right: answer panel */
.answer-wrap{flex:1;overflow-y:auto}
.answer-empty{padding:48px 24px;text-align:center;color:#4b5563;font-size:13px;
  line-height:1.8}
.answer-empty strong{display:block;color:#6b7280;font-size:15px;margin-bottom:6px}
.answer-card{background:#1a1a2e;border:1px solid #2d2d4a;border-radius:10px;
  padding:20px;margin-bottom:16px}
.answer-q{font-size:11px;color:#4b5563;font-style:italic;margin-bottom:14px;
  padding-bottom:10px;border-bottom:1px solid #1e293b}

/* Markdown */
.md h1,.md h2,.md h3{color:#f1f5f9;font-weight:700;margin:14px 0 6px}
.md h1{font-size:16px}.md h2{font-size:14px}.md h3{font-size:13px}
.md p{color:#cbd5e1;font-size:13px;line-height:1.7;margin-bottom:10px}
.md ul,.md ol{padding-left:18px;margin-bottom:10px}
.md li{color:#cbd5e1;font-size:13px;line-height:1.7;margin-bottom:4px}
.md strong{color:#e2e8f0;font-weight:600}
.md em{color:#94a3b8}
.md a{color:#60a5fa;text-decoration:none}
.md a:hover{text-decoration:underline}
.md code{background:#0f1117;color:#93c5fd;padding:1px 5px;border-radius:4px;
  font-size:12px;font-family:"JetBrains Mono","Fira Code",monospace}
.md pre{background:#0a0a14;border:1px solid #1e293b;border-radius:8px;
  padding:14px 16px;margin:10px 0;overflow-x:auto}
.md pre code{background:none;color:#e2e8f0;padding:0;font-size:12px;line-height:1.6}
.md hr{border:none;border-top:1px solid #2d2d4a;margin:14px 0}
.md blockquote{border-left:3px solid #1d4ed8;padding-left:12px;margin:8px 0;
  color:#94a3b8;font-size:13px}
.md table{width:100%;border-collapse:collapse;margin:10px 0;font-size:12px}
.md th{background:#0f1117;color:#94a3b8;padding:7px 10px;text-align:left;
  border:1px solid #2d2d4a;font-weight:600}
.md td{padding:7px 10px;border:1px solid #1e293b;color:#cbd5e1}
.md tr:nth-child(even) td{background:#111827}

/* Sources section */
.sources{margin-top:14px;padding-top:12px;border-top:1px solid #1e293b}
.sources-label{font-size:11px;font-weight:700;color:#4b5563;letter-spacing:.06em;
  text-transform:uppercase;margin-bottom:6px}
.source-item{display:flex;gap:6px;align-items:flex-start;margin-bottom:5px}
.source-dot{width:5px;height:5px;border-radius:50%;background:#1d4ed8;
  flex-shrink:0;margin-top:5px}
.source-link{font-size:12px;color:#60a5fa;text-decoration:none;line-height:1.5}
.source-link:hover{text-decoration:underline}
</style>
</head>
<body>

<header>
  <span class="ibm-logo">IBM</span>
  <h1>Docs Q&A</h1>
  <span class="badge badge-blue">ibm.com · cloud.ibm.com</span>
  <div class="spacer"></div>
  <span class="hdr-hint">Searches real IBM docs · follow-up supported</span>
</header>

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
          <input class="chat-input" id="chat-input" type="text"
            placeholder="Ask any IBM Cloud question…"
            onkeydown="if(event.key==='Enter')ask()">
          <button class="send-btn" id="send-btn" onclick="ask()">Ask</button>
        </div>
        <div class="status-msg" id="status-msg"></div>
      </div>
    </div>

    <div class="card" style="flex:1;display:flex;flex-direction:column;overflow:hidden">
      <div class="card-header"><h2>🗂 Question History</h2></div>
      <div class="card-body" style="flex:1;overflow-y:auto;padding-top:10px">
        <div class="chat-history" id="chat-history">
          <div style="font-size:12px;color:#4b5563;text-align:center;padding:16px 0">
            Questions will appear here
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Right: Answer panel ───────────────────────────────────── -->
  <div class="panel">
    <div class="card" style="flex:1;display:flex;flex-direction:column;overflow:hidden">
      <div class="card-header"><h2>📄 Answer from IBM Docs</h2></div>
      <div class="answer-wrap" id="answer-wrap" style="padding:0 0 0 0">
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
  stat.innerHTML = '<div class="spinner"></div> Searching IBM docs…';

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
    stat.innerHTML = `<span style="color:#f87171">Error: ${esc(e.message)}</span>`;
  }
  btn.disabled = false;
  btn.textContent = 'Ask';
}

function addHistoryItem(q, status) {
  const hist = document.getElementById('chat-history');
  // Clear placeholder
  if(hist.children.length === 1 && hist.children[0].style.textAlign === 'center') {
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
</body>
</html>"""
