"""
Hiking Research Agent — discover and compare hikes with AI
==========================================================

Find hikes near any location, filter by difficulty and kid-friendliness,
and get AI-synthesised summaries of user reviews from the web.

Run:
    python main.py
    python main.py --port 28805
    python main.py --provider anthropic

Then open: http://127.0.0.1:28805

Environment variables:
    LLM_PROVIDER      rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL         model override
    TAVILY_API_KEY    Tavily search API key (for review summaries)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent

for _p in [str(_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state — last hike search results (demo: single shared session)
# ---------------------------------------------------------------------------

_last_hikes: list[dict] = []
_last_location: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAC_DIFFICULTY = {
    "hiking":                    "easy",
    "mountain_hiking":           "moderate",
    "demanding_mountain_hiking": "hard",
    "alpine_hiking":             "hard",
    "demanding_alpine_hiking":   "hard",
    "difficult_alpine_hiking":   "hard",
}


def _infer_difficulty(tags: dict) -> str:
    sac = tags.get("sac_scale", "")
    if sac in _SAC_DIFFICULTY:
        return _SAC_DIFFICULTY[sac]
    # fall back to distance heuristic
    dist = _parse_distance_km(tags)
    if dist is None:
        return "unknown"
    if dist < 6:
        return "easy"
    if dist < 15:
        return "moderate"
    return "hard"


def _parse_distance_km(tags: dict) -> float | None:
    for key in ("distance", "length"):
        val = tags.get(key, "")
        if not val:
            continue
        try:
            return float(str(val).replace("km", "").replace("mi", "").strip())
        except ValueError:
            pass
    return None


def _is_kid_friendly(tags: dict, difficulty: str) -> bool:
    if tags.get("child") == "yes":
        return True
    if difficulty == "hard":
        return False
    dist = _parse_distance_km(tags)
    if dist is not None and dist > 10:
        return False
    return difficulty == "easy"


def _http_get(url: str, headers: dict | None = None) -> dict | list:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def _overpass_post(query: str) -> dict:
    data = urllib.parse.urlencode({"data": query}).encode()
    req  = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def _make_tools():
    # Delegated to MCP server(s): geo, web.
    from _mcp_bridge import load_tools
    return load_tools(["geo", "web"])


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
# Hiking Research Assistant

You help users discover, filter, and evaluate hiking trails near any location.

## Workflow

**Discovering hikes**
1. When the user names a place, call `geocode` to get lat/lon.
2. Call `find_hikes` with those coordinates.
   - Pass `difficulty` if the user specifies easy/moderate/hard.
   - Pass `kid_friendly=true` if they mention children, kids, or family.
   - Default radius is 25 km; increase to 40-50 if the user says "wider area" or results are sparse.
3. Summarise the top 5–8 results: name, difficulty, distance, and a one-sentence description.
   Group by difficulty when presenting mixed results.

**Reviewing a specific trail**
- When the user asks for reviews, opinions, or more detail on a named trail, call `web_search`.
- Synthesise the sources into 3–5 key points hikers mention (scenery, difficulty notes, parking, best season, warnings).
- Cite sources by name where possible.

**Filtering**
- If the user asks to filter after results are shown, re-call `find_hikes` with the new difficulty/kid_friendly flags rather than filtering mentally.

## Tone
- Be concise. One sentence per trail when listing results.
- Flag trails with no distance data as "distance unknown".
- If no results are found, suggest adjusting the radius or trying a nearby town.
- Never fabricate trail details. Only report what the tools return.
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

def make_agent():
    # CUGA reads AGENT_SETTING_CONFIG to pick its internal LLM settings TOML.
    # Without this it defaults to settings.openai.toml and crashes when
    # OPENAI_API_KEY is not set.  Map provider → TOML filename.
    _provider_toml = {
        "rits":      "settings.rits.toml",
        "watsonx":   "settings.watsonx.toml",
        "openai":    "settings.openai.toml",
        "anthropic": "settings.openai.toml",  # anthropic uses openai-compat internally
        "litellm":   "settings.litellm.toml",
        "ollama":    "settings.openai.toml",
    }
    provider = (os.getenv("LLM_PROVIDER") or "").lower()
    toml = _provider_toml.get(provider, "settings.rits.toml")
    os.environ.setdefault("AGENT_SETTING_CONFIG", toml)

    from cuga import CugaAgent
    from _llm import create_llm

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class AskReq(BaseModel):
    question: str


# ---------------------------------------------------------------------------
# Web app
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn

    agent = make_agent()
    app   = FastAPI(title="Hiking Research")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    @app.post("/ask")
    async def api_ask(req: AskReq):
        from _usage import track_utterance; track_utterance(req.question)
        try:
            result = await agent.invoke(req.question, thread_id=uuid.uuid4().hex)
            return {"answer": result.answer}
        except Exception as exc:
            log.exception("Agent error")
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.get("/hikes")
    async def api_hikes():
        return {"hikes": _last_hikes, "location": _last_location}

    @app.get("/", response_class=HTMLResponse)
    async def ui():
        return HTMLResponse(_HTML)

    # Public deployment: layered, in-memory rate limiting on POST.
    from _ratelimit import install_rate_limit
    install_rate_limit(app)
    from _usage import install_usage
    install_usage(app)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------

from _carbon import carbon_head, carbon_css

_APP_CSS = """<style>
  body{background:var(--cds-background);color:var(--cds-text-primary);min-height:100vh}

  .hdr-hint{font-size:0.75rem;color:#c6c6c6}

  .layout{display:grid;grid-template-columns:380px 1fr;gap:var(--cds-sp-06);
    max-width:1400px;margin:0 auto;padding:var(--cds-sp-06) var(--cds-sp-06)}
  @media (max-width:820px){.layout{grid-template-columns:1fr}}

  .card{background:var(--cds-layer-01);border:1px solid var(--cds-border-subtle);
    overflow:hidden;margin-bottom:var(--cds-sp-05)}
  .card-header{padding:var(--cds-sp-04) var(--cds-sp-05);border-bottom:1px solid var(--cds-border-subtle);
    display:flex;align-items:center;gap:var(--cds-sp-03)}
  .card-header h2{font-size:0.875rem;font-weight:600;color:var(--cds-text-primary)}
  .card-body{padding:var(--cds-sp-05)}

  /* Chat */
  .chips{display:flex;flex-wrap:wrap;gap:var(--cds-sp-03);margin-bottom:var(--cds-sp-04)}
  .chip{padding:var(--cds-sp-02) var(--cds-sp-04);border-radius:0.9375rem;font-size:0.75rem;
    background:var(--cds-layer-02);border:1px solid var(--cds-border-subtle);
    color:var(--cds-text-secondary);cursor:pointer;
    transition:all var(--cds-dur-mod) var(--cds-ease-productive)}
  .chip:hover{background:var(--cds-interactive);border-color:var(--cds-interactive);color:#fff}
  .chat-row{display:flex;gap:0}
  .chat-input{flex:1}
  .chat-send{flex:none;white-space:nowrap;min-width:8rem}
  .chat-result{margin-top:var(--cds-sp-04);padding:var(--cds-sp-05);
    background:var(--cds-layer-02);border:1px solid var(--cds-border-subtle);
    font-size:0.875rem;line-height:1.6;color:var(--cds-text-primary);
    white-space:pre-wrap;display:none}
  .chat-result.vis{display:block}
  .chat-result a{color:var(--cds-link-primary)}
  .chat-result a:hover{color:var(--cds-link-hover);text-decoration:underline}

  /* Hike cards */
  .hike-grid{display:flex;flex-direction:column;gap:var(--cds-sp-04)}
  .hike-card{background:var(--cds-layer-02);border:1px solid var(--cds-border-subtle);
    padding:var(--cds-sp-05);transition:background var(--cds-dur-mod) var(--cds-ease-productive)}
  .hike-card:hover{background:var(--cds-layer-hover)}
  .hike-top{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--cds-sp-03);margin-bottom:var(--cds-sp-03)}
  .hike-name{font-size:0.875rem;font-weight:600;color:var(--cds-text-primary);line-height:1.3;text-decoration:none}
  .hike-name:hover{color:var(--cds-link-primary);text-decoration:underline}
  .hike-badges{display:flex;gap:var(--cds-sp-02);flex-wrap:wrap;flex-shrink:0}
  .diff-easy,.diff-moderate,.diff-hard,.diff-unknown,.kid-badge{
    display:inline-flex;align-items:center;height:1.5rem;padding:0 var(--cds-sp-03);
    border-radius:0.9375rem;font-size:0.75rem;font-weight:400;white-space:nowrap}
  .diff-easy{background:var(--cds-support-success-bg);color:var(--cds-support-success)}
  .diff-moderate{background:var(--cds-support-warning-bg);color:var(--cds-text-primary)}
  .diff-hard{background:var(--cds-support-error-bg);color:var(--cds-support-error)}
  .diff-unknown{background:var(--cds-layer-accent);color:var(--cds-text-secondary)}
  .kid-badge{background:var(--cds-support-info-bg);color:var(--cds-link-primary)}
  .hike-meta{display:flex;gap:var(--cds-sp-05);font-size:0.75rem;color:var(--cds-text-secondary);margin-bottom:var(--cds-sp-03);flex-wrap:wrap}
  .hike-desc{font-size:0.8125rem;color:var(--cds-text-secondary);line-height:1.5;margin-bottom:var(--cds-sp-03)}
  .hike-review-btn{font-size:0.75rem;padding:var(--cds-sp-02) var(--cds-sp-04);cursor:pointer;
    border:1px solid var(--cds-interactive);background:transparent;color:var(--cds-interactive);
    transition:all var(--cds-dur-mod) var(--cds-ease-productive)}
  .hike-review-btn:hover{background:var(--cds-interactive);color:#fff}
  .hike-review-btn:focus-visible{outline:2px solid var(--cds-focus);outline-offset:-2px}

  .refresh-btn{margin-left:auto;cursor:pointer}

  .empty-state{font-size:0.875rem;color:var(--cds-text-placeholder);text-align:center;padding:var(--cds-sp-09) var(--cds-sp-05);line-height:1.8}
  .empty-state strong{color:var(--cds-text-secondary);display:block;font-size:1rem;margin-bottom:var(--cds-sp-02)}
</style>"""

_BODY = """
<header class="cds-header">
  <div class="cds-header__name"><span class="cds-header__prefix">IBM</span>&nbsp;Hiking&nbsp;Research</div>
  <span class="cds-tag cds-tag--green" id="count-badge">0 trails</span>
  <div class="cds-header__actions">
    <span class="hdr-hint">OpenStreetMap trails · Tavily reviews</span>
  </div>
</header>

<div class="layout">

  <!-- ── Left: Chat ───────────────────────────────────────── -->
  <div>
    <div class="card">
      <div class="card-header"><h2>💬 Ask the Hiking Agent</h2></div>
      <div class="card-body">
        <div class="chips">
          <span class="chip" onclick="ask(this.textContent)">Easy hikes near Yosemite, CA</span>
          <span class="chip" onclick="ask(this.textContent)">Kid-friendly trails near Boulder, CO</span>
          <span class="chip" onclick="ask(this.textContent)">Moderate hikes near Asheville, NC</span>
          <span class="chip" onclick="ask(this.textContent)">Hard hikes near Denver, CO</span>
          <span class="chip" onclick="ask(this.textContent)">Best hikes near Sedona, AZ</span>
          <span class="chip" onclick="ask(this.textContent)">Hikes near Zion National Park</span>
          <span class="chip" onclick="ask(this.textContent)">Family hikes near Lake Tahoe</span>
          <span class="chip" onclick="ask(this.textContent)">Show hikes within 40 km of Edinburgh</span>
        </div>
        <div class="chat-row">
          <input class="cds-input chat-input" id="chat-input" type="text"
            placeholder="Find hikes near… filter by difficulty…"
            onkeydown="if(event.key==='Enter')ask()">
          <button class="cds-btn chat-send" id="chat-send" onclick="ask()">Send</button>
        </div>
        <div class="chat-result" id="chat-result"></div>
      </div>
    </div>
  </div>

  <!-- ── Right: Hike results ──────────────────────────────── -->
  <div>
    <div class="card">
      <div class="card-header">
        <h2>🗺️ Trails Found</h2>
        <button class="cds-btn cds-btn--tertiary cds-btn--sm refresh-btn"
          onclick="loadHikes()">↺ Refresh</button>
      </div>
      <div class="card-body">
        <div class="hike-grid" id="hike-grid">
          <div class="empty-state">
            <strong>No results yet</strong>
            Ask the agent to find hikes near a location.<br>
            Try: <em>"Easy hikes near Yosemite, CA"</em>
          </div>
        </div>
      </div>
    </div>
  </div>

</div>

<script>
// ── Minimal markdown renderer ─────────────────────────────────
function mdToHtml(text) {
  return esc(text)
    .replace(/[*][*](.+?)[*][*]/g, '<strong>$1</strong>')
    .replace(/[*](.+?)[*]/g,       '<em>$1</em>')
    .replace(/`(.+?)`/g,           '<code style="background:var(--cds-layer-accent);color:var(--cds-link-primary);padding:1px 5px;font-family:var(--cds-font-mono);font-size:0.75rem">$1</code>')
    .replace(/^#{1,3} (.+)$/gm,    '<strong>$1</strong>')
    .replace(/^[ \\t]*[-*] (.+)$/gm, '&nbsp;&nbsp;• $1')
    .replace(/\\n/g, '<br>');
}

// ── Chat ─────────────────────────────────────────────────────
async function ask(question) {
  const inp = document.getElementById('chat-input');
  const res = document.getElementById('chat-result');
  const btn = document.getElementById('chat-send');
  const q   = question || inp.value.trim();
  if (!q) return;
  inp.value = '';
  btn.disabled = true; btn.textContent = 'Searching…';
  res.className = 'chat-result vis';
  res.innerHTML = '<em style="color:#6b7280">Thinking…</em>';
  try {
    const r = await fetch('/ask', { method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ question: q }) });
    const d = await r.json();
    res.innerHTML = mdToHtml(d.answer || d.error || '(no response)');
    await loadHikes();
    // second refresh after a short delay in case the agent's tool ran late
    setTimeout(loadHikes, 1200);
  } catch(e) { res.innerHTML = '<span style="color:var(--cds-support-error)">Error: ' + esc(e.message) + '</span>'; }
  btn.disabled = false; btn.textContent = 'Send';
}

// ── Hike cards ───────────────────────────────────────────────
async function loadHikes() {
  try {
    const d = await fetch('/hikes').then(r => r.json());
    renderHikes(d.hikes || []);
  } catch(e) {}
}

function renderHikes(hikes) {
  const grid  = document.getElementById('hike-grid');
  const badge = document.getElementById('count-badge');
  badge.textContent = hikes.length + ' trail' + (hikes.length === 1 ? '' : 's');

  if (!hikes.length) {
    grid.innerHTML = '<div class="empty-state"><strong>No results yet</strong>Ask the agent to find hikes near a location.<br>Try: <em>"Easy hikes near Yosemite, CA"</em></div>';
    return;
  }
  grid.innerHTML = hikes.map(h => renderCard(h)).join('');
}

function renderCard(h) {
  const diffClass = 'diff-' + (h.difficulty || 'unknown');
  const diffLabel = (h.difficulty || 'unknown').charAt(0).toUpperCase() + (h.difficulty || 'unknown').slice(1);
  const dist      = h.distance_km ? '📏 ' + h.distance_km + ' km' : '📏 distance unknown';
  const route     = (h.from_place && h.to_place) ? '📍 ' + esc(h.from_place) + ' → ' + esc(h.to_place) : '';
  const kidBadge  = h.kid_friendly ? '<span class="kid-badge">👨‍👩‍👧 Kid-friendly</span>' : '';
  const desc      = h.description ? '<div class="hike-desc">' + esc(h.description) + '</div>' : '';
  const op        = h.operator ? '<span>' + esc(h.operator) + '</span>' : '';
  const mapUrl    = h.osm_id
    ? 'https://www.openstreetmap.org/relation/' + h.osm_id
    : 'https://www.openstreetmap.org/search?query=' + encodeURIComponent(h.name);
  return `
    <div class="hike-card">
      <div class="hike-top">
        <a class="hike-name" href="${mapUrl}" target="_blank" rel="noopener"
           title="View on OpenStreetMap">${esc(h.name)} <span style="font-size:10px;opacity:.6">↗</span></a>
        <div class="hike-badges">
          <span class="${diffClass}">${diffLabel}</span>
          ${kidBadge}
        </div>
      </div>
      <div class="hike-meta">
        <span>${dist}</span>
        ${route ? '<span>' + route + '</span>' : ''}
        ${op}
      </div>
      ${desc}
      <button class="hike-review-btn" data-name="${esc(h.name)}" onclick="askReviews(this.dataset.name)">Get Reviews ↗</button>
    </div>`;
}

function askReviews(hikeName) {
  const inp = document.getElementById('chat-input');
  inp.value = 'Tell me about user reviews for: ' + hikeName;
  ask();
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Auto-refresh every 15s
setInterval(loadHikes, 15000);
loadHikes();
</script>
"""

_HTML = (
    "<!DOCTYPE html><html lang=\"en\"><head>"
    + carbon_head("Hiking Research")
    + carbon_css("light")
    + _APP_CSS
    + "</head><body>"
    + _BODY
    + "</body></html>"
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hiking Research Agent — web UI")
    parser.add_argument("--port",     type=int, default=28805)
    parser.add_argument("--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model",    "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    print(f"\n  Hiking Research  →  http://127.0.0.1:{args.port}\n")
    _web(args.port)
