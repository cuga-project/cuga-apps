"""
Stock Alert Agent — web UI powered by cuga++
=============================================

Starts a browser UI with two panels:

  Market Query  — ask any price question (BTC price, compare ETH/SOL, AAPL quote)
  Price Watch   — configure a threshold alert; fires a *browser notification*
                  when crossed. Watches and alert history live in the user's
                  own browser (localStorage); nothing is sent by email.

Per-user isolation is structural at every layer:
  - watches + alert history → browser localStorage (per browser-profile)
  - Alpha Vantage API key   → browser localStorage (per browser-profile);
    sent on each /ask and /check, forwarded to mcp-finance as a tool arg, and
    scrubbed from the agent's reply before returning to the client. The server
    NEVER persists the key.

The server is stateless: every /ask and /check opens a fresh agent thread
(uuid-suffixed) so concurrent users do not share conversation state.

Run:
    python main.py
    python main.py --port 8080
    python main.py --provider anthropic

Then open: http://127.0.0.1:28801

Prerequisites:
    Crypto (no key needed — CoinGecko public API):
        No setup required.

    Stocks (per-user Alpha Vantage key):
        Each user pastes their own free key from alphavantage.co into the UI.
        The key is saved to the browser's localStorage and sent on every
        request — never persisted on the server.

Environment variables:
    LLM_PROVIDER    rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL       model override
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from pathlib import Path

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
# Agent
# ---------------------------------------------------------------------------

_SYSTEM = """\
# Stock Alert

You are a market monitoring assistant. You watch prices and surface alerts that are actually worth attention.

## Tools available

| Tool | When to use |
|---|---|
| `get_crypto_price` | Fetch current price and 24h change for a cryptocurrency (BTC, ETH, SOL, etc.) |
| `get_stock_quote` | Fetch current price and change for a stock ticker (AAPL, TSLA, NVDA, etc.) |

Always call the appropriate tool before answering. Never guess a price.

## API key handling — important

If the user's request includes an `Alpha Vantage API key:` line, you MUST:
- Pass it to `get_stock_quote` as the `api_key` parameter on every call.
- NEVER include the key (or any substring of it) in your reply text. Treat it
  as a secret. If you mention "your key" at all, refer to it abstractly.
- If the user's request does NOT include a key and they're asking about a
  stock, say "Stock quotes need an Alpha Vantage key — paste yours into the
  Alpha Vantage field on the left." Do not try to fetch.

For crypto questions, no key is required — `get_crypto_price` is keyless.

## Watch mode — threshold alerts

When given a symbol and a threshold:

1. Fetch the current price with the appropriate tool
2. Compare against the threshold

**If the threshold is crossed:**
- Lead with `PRICE ALERT` on its own line
- State the symbol, current price, and which direction (crossed above / dropped below)
- Include the 24h change %
- One sentence of context: is this a big move? is it continuing a trend?
- Keep it under 5 lines total

**If the threshold is NOT crossed:**
- One line: `{SYMBOL} at ${price} — {direction} alert at ${threshold}. No action needed.`
- Nothing else

## Watch mode — no threshold

When given a symbol with no threshold, report a concise status:
`{SYMBOL} ${price} ({change%} 24h)`

## Query mode — on-demand questions

When a user asks a free-form market question:
1. Identify the symbol(s) from the query
2. Call the appropriate tool(s)
3. Answer directly with price, change, and any directly relevant data the tool returns
4. Be concise — one to three lines

For comparisons ("compare ETH and SOL"), call both tools then summarise side by side.

## Format rules

- Always include the 24h change % when available
- Dollar amounts: use commas for thousands (`$84,200`)
- Change %: always include sign (`+2.4%`, `-1.1%`)
- Never include disclaimers, "not financial advice", or hedging language
- Never fabricate data — if a tool call fails, say so clearly
"""


def make_agent():
    from cuga import CugaAgent
    from _mcp_bridge import load_tools
    from _llm import create_llm

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=load_tools(["finance"]),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class AskReq(BaseModel):
    symbol: str
    question: str
    is_stock: bool = False
    alpha_vantage_key: str | None = None   # forwarded to mcp-finance per call


class CheckReq(BaseModel):
    symbol: str
    threshold: float
    direction: str        # "above" | "below"
    is_stock: bool = False
    alpha_vantage_key: str | None = None   # forwarded to mcp-finance per call


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse

    app = FastAPI(title="Stock Alert · CugaAgent", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    _agent = make_agent()

    def _key_block(key: str | None) -> str:
        """Render a single line for the agent prompt — only when present.

        We tell the agent both the key and the explicit instruction not to
        echo it. The system prompt also forbids leaking; we still scrub
        server-side as defense in depth.
        """
        if not key:
            return ""
        return (
            f"Alpha Vantage API key: {key}\n"
            f"(Use this as the api_key parameter on get_stock_quote calls. "
            f"Do not include the key in your reply text.)\n"
        )

    def _scrub(answer: str, key: str | None) -> str:
        """Defensive: strip the key from the agent's reply if it leaked."""
        if not key or not answer:
            return answer
        return answer.replace(key, "[redacted]")

    @app.post("/ask")
    async def ask(req: AskReq):
        from _usage import track_utterance; track_utterance(req.question)
        symbol = req.symbol.strip().upper()
        asset  = "stock" if req.is_stock else "crypto"
        # Defense-in-depth: never silently fall back to the MCP server's env
        # key for stock queries — keys are per-user by policy.
        if req.is_stock and not req.alpha_vantage_key:
            raise HTTPException(status_code=400,
                detail="Stock quotes require a per-user Alpha Vantage key. "
                       "Paste yours in the left panel.")
        prompt = (
            _key_block(req.alpha_vantage_key)
            + f"Symbol: {symbol} ({asset})\nQuestion: {req.question}"
        )
        # Unique thread per call: many concurrent users querying the same symbol
        # must not share an agent thread (their messages would interleave).
        thread = f"query-{symbol.lower()}-{uuid.uuid4().hex[:8]}"
        try:
            result = await _agent.invoke(prompt, thread_id=thread)
            return {"answer": _scrub(result.answer, req.alpha_vantage_key)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/check")
    async def check(req: CheckReq):
        """One threshold check for a single symbol — the browser polls this."""
        symbol = req.symbol.strip().upper()
        asset  = "stock" if req.is_stock else "crypto"
        if req.is_stock and not req.alpha_vantage_key:
            raise HTTPException(status_code=400,
                detail="Stock watches require a per-user Alpha Vantage key.")
        prompt = (
            _key_block(req.alpha_vantage_key)
            + f"Check {symbol} ({asset}) price now.\n"
            + f"Alert threshold: ${req.threshold:,.2f} ({req.direction})."
        )
        thread = f"check-{symbol.lower()}-{uuid.uuid4().hex[:8]}"
        try:
            result = await _agent.invoke(prompt, thread_id=thread)
            answer = _scrub(result.answer, req.alpha_vantage_key)
            triggered = "PRICE ALERT" in answer
            log.info("[CHECK] %s %s $%.2f triggered=%s key=%s",
                     symbol, req.direction, req.threshold, triggered,
                     "yes" if req.alpha_vantage_key else "no")
            return {"symbol": symbol, "triggered": triggered, "message": answer}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/", response_class=HTMLResponse)
    def ui():
        return _WEB_HTML

    print(f"\n  Stock Alert · CugaAgent  →  http://127.0.0.1:{port}\n")
    # Public deployment: layered, in-memory rate limiting on POST.
    from _ratelimit import install_rate_limit
    install_rate_limit(app)
    from _usage import install_usage
    install_usage(app)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_WEB_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IBM Stock Alert</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  /* Carbon Gray 100 (dark) tokens */
  --bg:#161616; --layer:#262626; --layer-02:#393939; --field:#262626;
  --border:#393939; --border-strong:#6f6f6f;
  --text:#f4f4f4; --text-sec:#c6c6c6; --muted:#8d8d8d; --placeholder:#6f6f6f;
  --blue:#0f62fe; --blue-hover:#0353e9; --blue-active:#002d9c;
  --link:#78a9ff; --accent:#4589ff;
  --danger:#fa4d56; --success:#42be65; --warn:#f1c21b;
  --font-sans:'IBM Plex Sans',system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --font-mono:'IBM Plex Mono',ui-monospace,"SFMono-Regular",Menlo,monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font-sans);background:var(--bg);color:var(--text);min-height:100vh;padding:40px 24px 80px;-webkit-font-smoothing:antialiased;letter-spacing:.16px}
header{text-align:center;margin-bottom:32px}
h1{font-size:28px;font-weight:600;color:#fff;margin-bottom:4px;letter-spacing:0}
.sub{font-size:13px;color:var(--muted)}.sub span{color:var(--accent);font-weight:500}
.layout{display:grid;grid-template-columns:280px 1fr;gap:20px;max-width:1020px;margin:0 auto;align-items:start}
@media(max-width:720px){.layout{grid-template-columns:1fr}}
.card{background:var(--layer);border:1px solid var(--border);border-radius:0;padding:18px;margin-bottom:16px}
.card:last-child{margin-bottom:0}
.card-title{font-size:11px;font-weight:600;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;margin-bottom:14px}
.section-label{font-size:11px;font-weight:600;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;margin:16px 0 10px;padding-top:16px;border-top:1px solid var(--border)}
.section-label:first-child{margin-top:0;padding-top:0;border-top:none}
label{display:block;font-size:11px;color:var(--muted);margin-bottom:4px;font-weight:400;text-transform:uppercase;letter-spacing:.32px}
input[type=text],input[type=number],input[type=password],select{width:100%;background:var(--field);border:none;border-bottom:1px solid var(--border-strong);border-radius:0;padding:10px 12px;font-size:13px;font-family:var(--font-sans);color:var(--text);outline:none;transition:outline .11s,background .11s}
input:focus,select:focus{outline:2px solid var(--blue);outline-offset:-2px}
input::placeholder{color:var(--placeholder)}
.field{margin-bottom:10px}
.field:last-of-type{margin-bottom:0}
.row{display:flex;gap:8px;margin-top:10px}.row>*{flex:1}
.row-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:10px}
button{background:var(--blue);color:#fff;border:1px solid transparent;border-radius:0;padding:11px 16px;font-size:13px;font-weight:400;font-family:var(--font-sans);letter-spacing:.16px;cursor:pointer;transition:background .15s cubic-bezier(.2,0,.38,.9);white-space:nowrap;width:100%;margin-top:10px}
button:hover{background:var(--blue-hover)}
button:active{background:var(--blue-active)}
button:focus-visible,button:focus{outline:2px solid var(--blue);outline-offset:-2px;box-shadow:inset 0 0 0 1px #fff}
button:disabled{opacity:.45;cursor:default}
button.danger{background:var(--danger);color:#fff;margin-top:0}
button.danger:hover{background:#ba1b23}
button.ghost{background:transparent;border:1px solid var(--border-strong);color:var(--text-sec)}
button.ghost:hover{background:var(--layer-02);color:var(--text)}
.status-row{display:flex;align-items:center;gap:7px;margin-top:10px;padding:9px 12px;background:var(--bg);border:1px solid var(--border);border-radius:0;font-size:12px}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot.on{background:var(--success);box-shadow:0 0 5px var(--success)}
.dot.off{background:var(--border-strong)}
.dot.warn{background:var(--warn);box-shadow:0 0 5px var(--warn)}
.dot.alert{background:var(--danger);box-shadow:0 0 5px var(--danger)}
.status-text{color:var(--muted);flex:1}.status-text strong{color:var(--text)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{background:var(--bg);border:1px solid var(--border);border-radius:15px;padding:5px 11px;font-size:12px;color:var(--text-sec);cursor:pointer;transition:border-color .1s,background .1s}
.chip:hover{border-color:var(--accent);color:var(--text)}
.result{margin-top:14px;padding:14px;background:var(--bg);border:1px solid var(--border);border-radius:0;font-size:14px;line-height:1.7;color:var(--text);display:none}
.result.visible{display:block}
.thinking{color:var(--muted);font-style:normal;font-size:13px}
.spinner{display:inline-block;animation:spin .7s linear infinite;color:var(--accent)}
.alert-row{display:flex;flex-direction:column;gap:4px;padding:10px 12px;background:var(--bg);border:1px solid var(--border);border-left:3px solid var(--danger);border-radius:0;margin-bottom:6px;font-size:12px}
.alert-row.fired{border-color:var(--border);border-left-color:var(--danger);background:rgba(250,77,86,.08)}
.alert-row .ts{font-size:10px;color:var(--muted);font-family:var(--font-mono)}
.alert-row .body{color:var(--text);line-height:1.5;white-space:pre-wrap}
.muted{font-size:11px;color:var(--muted);margin-top:6px;line-height:1.5}
.muted a{color:var(--link);text-decoration:none}.muted a:hover{text-decoration:underline;color:#a6c8ff}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.fadein{animation:fadein .2s ease}
</style>
</head>
<body>
<header>
  <h1>Stock Alert</h1>
  <p class="sub">Powered by <span>CugaAgent</span> · live market data · browser-only alerts</p>
</header>

<div class="layout">

  <!-- ══ Left panel — settings ══ -->
  <div>

    <div class="card">

      <div class="section-label">Alpha Vantage Key <span style="font-weight:400;text-transform:none;letter-spacing:0;color:var(--muted)">— per-user, stays in this browser</span></div>
      <div class="field">
        <input id="avKey" type="password" placeholder="get free key at alphavantage.co" />
      </div>
      <button id="apiSaveBtn" onclick="saveApi()">Save in this browser</button>
      <div class="status-row">
        <span class="dot off" id="apiDot"></span>
        <span class="status-text" id="apiLabel">Not set — paste your key</span>
      </div>
      <div class="muted">Your key never leaves this browser's localStorage
        except when sent on individual price requests, and is never persisted
        on the server. Crypto works without a key. <a
        href="https://www.alphavantage.co/support/#api-key"
        target="_blank" style="color:var(--link)">Get a free key →</a></div>

      <div class="muted" style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border)">
        Watches and alert history live only in this browser. A different user
        on a different browser sees their own watches.
      </div>

    </div>

  </div>

  <!-- ══ Right panel — query + watch + alerts ══ -->
  <div>

    <!-- Market Query -->
    <div class="card">
      <div class="card-title">Market Query</div>
      <div class="row" style="margin-top:0">
        <div>
          <label>Symbol</label>
          <input id="qSymbol" type="text" placeholder="BTC  ETH  AAPL  TSLA …" style="text-transform:uppercase" />
        </div>
        <div style="flex:0 0 auto;width:110px">
          <label>Type</label>
          <select id="qType">
            <option value="crypto">Crypto</option>
            <option value="stock">Stock</option>
          </select>
        </div>
      </div>
      <div class="field" style="margin-top:10px">
        <label>Question</label>
        <div class="row" style="margin-top:0">
          <input id="qQuestion" type="text" placeholder="What is the current price?" onkeydown="if(event.key==='Enter')ask()" />
          <button id="askBtn" onclick="ask()" style="width:auto;margin-top:0">Ask</button>
        </div>
      </div>
      <div class="chips">
        <span class="chip" onclick="quickAsk('What is the current price and 24h change?')">Price + 24h change</span>
        <span class="chip" onclick="quickAsk('What is the 24h trading volume? Is it high or low?')">Volume</span>
        <span class="chip" onclick="quickAsk('What is the market cap?')">Market cap</span>
        <span class="chip" onclick="quickAsk('Is this price move notable or just normal volatility?')">Notable move?</span>
        <span class="chip" onclick="quickAsk('Give me a quick bull or bear read on this asset right now.')">Bull / bear?</span>
        <span class="chip" onclick="quickAsk('Is this a good entry point or should I wait?')">Entry signal?</span>
        <span class="chip" onclick="quickAsk('What would a 5% swing from the current price look like in dollars?')">5% swing in $</span>
        <span class="chip" onclick="quickAsk('Compare BTC and ETH — which is performing better today?')">BTC vs ETH</span>
        <span class="chip" onclick="quickAsk('Summarise the current market conditions for this asset.')">Market summary</span>
      </div>
      <div class="result" id="askResult"></div>
    </div>

    <!-- Price Watch -->
    <div class="card">
      <div class="card-title">Price Watch <span style="float:right;font-size:10px;color:#8d8d8d" id="watchSummary"></span></div>
      <div class="row-3">
        <div>
          <label>Symbol</label>
          <input id="wSymbol" type="text" placeholder="BTC" style="text-transform:uppercase" />
        </div>
        <div>
          <label>Type</label>
          <select id="wType">
            <option value="crypto">Crypto</option>
            <option value="stock">Stock</option>
          </select>
        </div>
        <div>
          <label>Direction</label>
          <select id="wDirection">
            <option value="above">Above</option>
            <option value="below">Below</option>
          </select>
        </div>
      </div>
      <div class="field" style="margin-top:10px">
        <label>Threshold ($)</label>
        <input id="wThreshold" type="number" placeholder="90000" min="0" step="any" />
      </div>
      <div class="row" style="margin-top:10px">
        <button onclick="addWatch()">Add Watch</button>
      </div>
      <div id="watchList" style="margin-top:12px"></div>
    </div>

    <!-- Recent alerts log -->
    <div class="card">
      <div class="card-title">Recent Alerts
        <span style="float:right">
          <button class="ghost" onclick="clearAlerts()" style="width:auto;margin:0;padding:4px 10px;font-size:11px">Clear</button>
        </span>
      </div>
      <div id="alertList"></div>
    </div>

  </div>
</div>

<script>
// ═════════════════════════════════════════════════════════════════════════
// Client-side per-user state — every browser keeps its own watches + alerts
// in localStorage. The server never sees them.
// ═════════════════════════════════════════════════════════════════════════

const WATCHES_KEY = 'stock_alert.watches.v1'
const ALERTS_KEY  = 'stock_alert.alerts.v1'
const AVKEY_KEY   = 'stock_alert.av_key.v1'  // per-browser Alpha Vantage key
const POLL_MS         = 5 * 60 * 1000    // 5 min between automatic checks
const ALERT_COOLDOWN  = 30 * 60 * 1000   // suppress duplicate alerts for 30 min
const MAX_ALERTS      = 50               // alerts log cap

function loadAvKey()      { return localStorage.getItem(AVKEY_KEY) || '' }
function saveAvKey(k)     { if (k) localStorage.setItem(AVKEY_KEY, k); else localStorage.removeItem(AVKEY_KEY) }

function loadWatches() {
  try { return JSON.parse(localStorage.getItem(WATCHES_KEY) || '[]') }
  catch { return [] }
}
function saveWatches(ws) { localStorage.setItem(WATCHES_KEY, JSON.stringify(ws)) }

function loadAlerts() {
  try { return JSON.parse(localStorage.getItem(ALERTS_KEY) || '[]') }
  catch { return [] }
}
function saveAlerts(as) { localStorage.setItem(ALERTS_KEY, JSON.stringify(as)) }

function watchKey(w) { return `${w.symbol}|${w.direction}|${w.threshold}|${w.isStock?'s':'c'}` }

// ═════════════════════════════════════════════════════════════════════════
// Market Query
// ═════════════════════════════════════════════════════════════════════════

function quickAsk(q) {
  document.getElementById('qQuestion').value = q
  ask()
}

async function ask() {
  const symbol = document.getElementById('qSymbol').value.trim().toUpperCase()
  const q      = document.getElementById('qQuestion').value.trim()
  if (!symbol || !q) return
  const isStock = document.getElementById('qType').value === 'stock'
  const avKey   = loadAvKey()

  const btn    = document.getElementById('askBtn')
  const result = document.getElementById('askResult')

  if (isStock && !avKey) {
    result.className = 'result visible fadein'
    result.style.color = '#f1c21b'
    result.textContent = 'Stock quotes need an Alpha Vantage key. Paste yours in the left panel and click Save.'
    return
  }
  result.style.color = ''
  btn.disabled = true
  result.className = 'result visible fadein'
  result.innerHTML = '<span class="thinking"><span class="spinner">⟳</span> Thinking…</span>'

  try {
    const res = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({symbol, question: q, is_stock: isStock,
                            alpha_vantage_key: avKey || null})
    })
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    result.innerHTML = renderAnswer(data.answer)
  } catch (err) {
    result.style.color = '#fa4d56'
    result.textContent = 'Error: ' + err.message
  } finally {
    btn.disabled = false
  }
}

function renderAnswer(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\\*\\*(.*?)\\*\\*/g,'<strong>$1</strong>')
    .replace(/\\b(\\+?-?\\d+\\.?\\d*%)\\b/g, s => `<span style="color:${s.startsWith('-')?'#fa4d56':'#42be65'};font-weight:600">${s}</span>`)
    .replace(/\\$[\\d,]+(?:\\.\\d+)?/g, s => `<span style="color:#4589ff;font-weight:600">${s}</span>`)
    .replace(/\\n/g,'<br>')
}

// ═════════════════════════════════════════════════════════════════════════
// Watches — owned entirely by the browser
// ═════════════════════════════════════════════════════════════════════════

function addWatch() {
  const symbol    = document.getElementById('wSymbol').value.trim().toUpperCase()
  const threshold = parseFloat(document.getElementById('wThreshold').value)
  const direction = document.getElementById('wDirection').value
  const isStock   = document.getElementById('wType').value === 'stock'
  if (!symbol || isNaN(threshold) || threshold <= 0) return

  if (isStock && !loadAvKey()) {
    alert('Stock watches need an Alpha Vantage key. Paste yours in the left panel first.')
    return
  }

  const ws = loadWatches()
  // dedup: same symbol+direction+threshold replaces the existing entry.
  const idx = ws.findIndex(w => watchKey(w) === watchKey({symbol, threshold, direction, isStock}))
  const entry = {symbol, threshold, direction, isStock,
                 addedAt: Date.now(), lastCheckedAt: 0, lastTriggeredAt: 0,
                 lastMessage: ''}
  if (idx >= 0) ws[idx] = entry; else ws.push(entry)
  saveWatches(ws)

  document.getElementById('wSymbol').value    = ''
  document.getElementById('wThreshold').value = ''
  renderWatches()
  // Run an immediate check for the new watch — gives the user instant feedback.
  checkOne(entry).then(renderWatches)
}

function removeWatch(key) {
  saveWatches(loadWatches().filter(w => watchKey(w) !== key))
  renderWatches()
}

function renderWatches() {
  const el  = document.getElementById('watchList')
  const ws  = loadWatches()
  document.getElementById('watchSummary').textContent =
    ws.length ? `${ws.length} active · checks every 5 min` : ''
  if (!ws.length) {
    el.innerHTML = '<div class="status-row"><span class="dot off"></span><span class="status-text">No active watches — add one above</span></div>'
    return
  }
  el.innerHTML = ws.map(w => {
    const dir   = w.direction === 'above' ? '↑' : '↓'
    const last  = w.lastCheckedAt
      ? `last checked ${fmtAgo(w.lastCheckedAt)}`
      : 'not yet checked'
    const fired = w.lastTriggeredAt
      ? ` · <span style="color:#fa4d56">fired ${fmtAgo(w.lastTriggeredAt)}</span>`
      : ''
    const dotCls = w.lastTriggeredAt ? 'alert' : (w.lastCheckedAt ? 'on' : 'warn')
    const key   = watchKey(w)
    return `<div class="status-row" style="margin-bottom:6px;align-items:flex-start;flex-wrap:wrap">
      <span class="dot ${dotCls}" style="margin-top:4px"></span>
      <span class="status-text" style="line-height:1.5">
        <strong>${w.symbol}</strong> ${dir} $${Number(w.threshold).toLocaleString()}
        <span style="color:#8d8d8d">(${w.isStock?'stock':'crypto'})</span><br>
        <span style="font-size:11px;color:#8d8d8d">${last}${fired}</span>
      </span>
      <span style="display:flex;gap:6px;flex-shrink:0">
        <button class="ghost" onclick="manualCheck('${key}')" style="width:auto;margin:0;padding:4px 10px;font-size:11px">Check now</button>
        <button class="danger" onclick="removeWatch('${key}')" style="width:auto;margin:0;padding:4px 10px;font-size:11px">Remove</button>
      </span>
    </div>`
  }).join('')
}

async function manualCheck(key) {
  const ws = loadWatches()
  const w  = ws.find(x => watchKey(x) === key)
  if (!w) return
  await checkOne(w)
  renderWatches()
}

async function checkOne(watch) {
  try {
    const res = await fetch('/check', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        symbol: watch.symbol, threshold: watch.threshold,
        direction: watch.direction, is_stock: watch.isStock,
        alpha_vantage_key: loadAvKey() || null,
      })
    })
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()

    // Persist the result on the watch entry.
    const ws = loadWatches()
    const idx = ws.findIndex(x => watchKey(x) === watchKey(watch))
    if (idx < 0) return  // watch was removed mid-flight
    ws[idx].lastCheckedAt = Date.now()
    ws[idx].lastMessage   = data.message

    if (data.triggered) {
      const since = Date.now() - (ws[idx].lastTriggeredAt || 0)
      // Cooldown: avoid re-logging every 5 min while the price stays past threshold.
      if (since >= ALERT_COOLDOWN) {
        ws[idx].lastTriggeredAt = Date.now()
        appendAlert(watch.symbol, data.message)
      }
    }
    saveWatches(ws)
  } catch (err) {
    console.warn('check failed for', watch.symbol, err)
  }
}

async function checkAll() {
  const ws = loadWatches()
  if (!ws.length) return
  // Run sequentially so we don't fan-out N concurrent agent invocations.
  for (const w of ws) {
    await checkOne(w)
  }
  renderWatches()
}

// ═════════════════════════════════════════════════════════════════════════
// Alerts log
// ═════════════════════════════════════════════════════════════════════════

function appendAlert(symbol, message) {
  const list = loadAlerts()
  list.unshift({symbol, message, ts: Date.now()})
  if (list.length > MAX_ALERTS) list.length = MAX_ALERTS
  saveAlerts(list)
  renderAlerts()
}

function clearAlerts() {
  if (!confirm('Clear all alerts on this browser?')) return
  saveAlerts([])
  renderAlerts()
}

function renderAlerts() {
  const el   = document.getElementById('alertList')
  const list = loadAlerts()
  if (!list.length) {
    el.innerHTML = '<div class="status-row"><span class="dot off"></span><span class="status-text">No alerts yet</span></div>'
    return
  }
  el.innerHTML = list.map(a => `
    <div class="alert-row fired fadein">
      <div class="ts">${new Date(a.ts).toLocaleString()} · ${escapeHtml(a.symbol)}</div>
      <div class="body">${escapeHtml(a.message)}</div>
    </div>`).join('')
}

// ═════════════════════════════════════════════════════════════════════════
// Alpha Vantage key — per-user, lives in this browser's localStorage only.
// Sent on every /ask and /check; never stored on the server.
// ═════════════════════════════════════════════════════════════════════════

function saveApi() {
  const key = document.getElementById('avKey').value.trim()
  saveAvKey(key)
  // Don't echo the saved key back into the input — leave it on whatever the
  // user typed; the masked field still hides it on subsequent loads.
  setApiUI(!!key)
}

function setApiUI(configured) {
  document.getElementById('apiDot').className = 'dot ' + (configured ? 'on' : 'off')
  document.getElementById('apiLabel').innerHTML = configured
    ? '<strong>Saved in this browser</strong>'
    : 'Not set — paste your key'
}

// ═════════════════════════════════════════════════════════════════════════
// Helpers + boot
// ═════════════════════════════════════════════════════════════════════════

function escapeHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

function fmtAgo(ts) {
  const s = Math.round((Date.now() - ts) / 1000)
  if (s < 60)  return `${s}s ago`
  const m = Math.round(s/60)
  if (m < 60)  return `${m}m ago`
  const h = Math.round(m/60)
  if (h < 24)  return `${h}h ago`
  return new Date(ts).toLocaleString()
}

// Boot — read the key (if any) from this browser's localStorage.
{
  const k = loadAvKey()
  if (k) document.getElementById('avKey').value = k    // pre-fill (still masked)
  setApiUI(!!k)
}
renderWatches()
renderAlerts()

// Polling: run every POLL_MS while the tab is open. Re-render countdown text
// every 30s so "last checked" stays fresh.
setInterval(checkAll, POLL_MS)
setInterval(renderWatches, 30 * 1000)

// When the tab becomes visible again after being hidden, run a check
// immediately if the last poll was a while ago — covers laptop-sleep cases.
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState !== 'visible') return
  const ws = loadWatches()
  const stale = ws.some(w => Date.now() - (w.lastCheckedAt || 0) > POLL_MS)
  if (stale) checkAll()
})
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Stock Alert Agent — web UI")
    parser.add_argument("--port",     type=int, default=28801)
    parser.add_argument("--provider", "-p", default=None,
                        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model",    "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    _web(args.port)


if __name__ == "__main__":
    main()
