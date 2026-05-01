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
        try:
            result = await agent.invoke(req.question, thread_id="chat")
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

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hiking Research</title>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    background:#0f1117;color:#e2e8f0;min-height:100vh}

  header{background:#1a1a2e;border-bottom:1px solid #2d2d4a;padding:14px 28px;
    display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}
  header h1{font-size:16px;font-weight:700;color:#fff}
  .badge{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
  .badge-green{background:#052e16;color:#4ade80}
  .badge-blue{background:#1e3a5f;color:#60a5fa}
  .spacer{flex:1}
  .hdr-hint{font-size:11px;color:#4b5563}

  .layout{display:grid;grid-template-columns:380px 1fr;gap:20px;
    max-width:1400px;margin:0 auto;padding:20px 24px}

  .card{background:#1a1a2e;border:1px solid #2d2d4a;border-radius:10px;
    overflow:hidden;margin-bottom:16px}
  .card-header{padding:12px 16px 10px;border-bottom:1px solid #2d2d4a;
    display:flex;align-items:center;gap:8px}
  .card-header h2{font-size:13px;font-weight:600;color:#c5cae9}
  .card-body{padding:16px}

  /* Chat */
  .chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:12px}
  .chip{padding:4px 10px;border-radius:12px;font-size:11px;background:#1f2937;
    border:1px solid #374151;color:#9ca3af;cursor:pointer;transition:all .15s}
  .chip:hover{background:#16a34a;border-color:#16a34a;color:#fff}
  .chat-row{display:flex;gap:8px}
  .chat-input{flex:1;padding:8px 12px;border-radius:7px;font-size:13px;
    background:#0f1117;border:1px solid #374151;color:#e2e8f0;outline:none}
  .chat-input:focus{border-color:#16a34a}
  .chat-send{padding:8px 16px;border-radius:7px;font-size:13px;cursor:pointer;
    border:none;background:#16a34a;color:#fff;white-space:nowrap}
  .chat-send:hover{background:#15803d}
  .chat-send:disabled{background:#374151;color:#6b7280;cursor:default}
  .chat-result{margin-top:12px;padding:12px;border-radius:7px;background:#0f1117;
    border:1px solid #2d2d4a;font-size:13px;line-height:1.6;color:#d1d5db;
    white-space:pre-wrap;display:none}
  .chat-result.vis{display:block}

  /* Hike cards */
  .hike-grid{display:flex;flex-direction:column;gap:10px}
  .hike-card{background:#0f1117;border:1px solid #2d2d4a;border-radius:8px;padding:14px}
  .hike-card:hover{border-color:#374151}
  .hike-top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:8px}
  .hike-name{font-size:14px;font-weight:600;color:#f1f5f9;line-height:1.3;text-decoration:none}
  .hike-name:hover{color:#4ade80;text-decoration:underline}
  .hike-badges{display:flex;gap:5px;flex-wrap:wrap;flex-shrink:0}
  .diff-easy{background:#052e16;color:#4ade80;padding:2px 8px;border-radius:8px;font-size:10px;font-weight:600}
  .diff-moderate{background:#431407;color:#fb923c;padding:2px 8px;border-radius:8px;font-size:10px;font-weight:600}
  .diff-hard{background:#450a0a;color:#f87171;padding:2px 8px;border-radius:8px;font-size:10px;font-weight:600}
  .diff-unknown{background:#1f2937;color:#9ca3af;padding:2px 8px;border-radius:8px;font-size:10px;font-weight:600}
  .kid-badge{background:#1e1b4b;color:#a5b4fc;padding:2px 8px;border-radius:8px;font-size:10px;font-weight:600}
  .hike-meta{display:flex;gap:14px;font-size:11px;color:#6b7280;margin-bottom:6px;flex-wrap:wrap}
  .hike-desc{font-size:12px;color:#9ca3af;line-height:1.5;margin-bottom:8px}
  .hike-review-btn{font-size:11px;padding:3px 10px;border-radius:6px;cursor:pointer;
    border:1px solid #374151;background:#1f2937;color:#9ca3af}
  .hike-review-btn:hover{background:#16a34a;border-color:#16a34a;color:#fff}

  .empty-state{font-size:13px;color:#4b5563;text-align:center;padding:48px 20px;line-height:1.8}
  .empty-state strong{color:#6b7280;display:block;font-size:15px;margin-bottom:4px}
</style>
</head>
<body>

<header>
  <h1>🥾 Hiking Research</h1>
  <span class="badge badge-green" id="count-badge">0 trails</span>
  <div class="spacer"></div>
  <span class="hdr-hint">OpenStreetMap trails · Tavily reviews</span>
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
          <input class="chat-input" id="chat-input" type="text"
            placeholder="Find hikes near… filter by difficulty…"
            onkeydown="if(event.key==='Enter')ask()">
          <button class="chat-send" id="chat-send" onclick="ask()">Send</button>
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
        <button class="badge badge-blue" style="margin-left:auto;cursor:pointer;border:none"
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
    .replace(/`(.+?)`/g,           '<code style="background:#1f2937;padding:1px 4px;border-radius:3px">$1</code>')
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
  } catch(e) { res.innerHTML = '<span style="color:#f87171">Error: ' + esc(e.message) + '</span>'; }
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
</body>
</html>"""


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
