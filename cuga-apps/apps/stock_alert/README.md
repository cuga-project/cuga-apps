# Stock Alert

<!-- BEGIN: MCP usage (auto-generated, do not edit by hand) -->
## MCP usage

Crypto + stock price queries and threshold alerts.

**MCP servers consumed:**
- **mcp-finance** — `get_crypto_price` · `get_stock_quote`

**Inline `@tool` defs:** none — every tool comes from MCP.

<!-- END: MCP usage -->

Monitor crypto and stock prices in a browser UI. Ask market questions on demand,
or set a threshold alert that fires a **browser notification** when a price is
crossed.

**Everything per-user lives in the user's own browser:**
- Watch list (`localStorage['stock_alert.watches.v1']`)
- Alert history (`localStorage['stock_alert.alerts.v1']`)
- Alpha Vantage API key for stocks (`localStorage['stock_alert.av_key.v1']`)

The key is sent on each `/ask` and `/check` request, forwarded to mcp-finance
as a tool argument, and scrubbed from the agent's reply before returning to
the client. **The server never persists the key.** Per-user isolation is
automatic — different browsers see different watches and use their own
Alpha Vantage quotas (the free tier is only 25 requests/day, so a shared key
would be blown by a single user with one stock watch).

**Port:** 28801

---

## Division of Responsibilities

### The Browser (single-page UI)

- **Owns the watch list** — every watch lives in `localStorage` (key `stock_alert.watches.v1`). Different users on different browsers have completely separate state.
- **Runs the watch loop** — `setInterval` polls `POST /check` for each watch every 5 minutes, plus an immediate check on `visibilitychange` if the tab woke from sleep.
- **Decides to notify** — when `/check` returns `triggered: true`, fires `new Notification(...)` (deduped per-symbol via `tag`) and appends to a `localStorage` alerts log capped at 50.
- **Cooldown** — same watch suppresses re-notification for 30 minutes so a price camped past threshold doesn't spam every poll.

### The Server (main.py)

- **Stateless** w.r.t. watches, users, and Alpha Vantage keys — it never sees who is watching what, and it never persists keys.
- **`POST /ask`** — free-form market query. Fresh agent thread per call (uuid-suffixed) so concurrent users do not share conversation state. Optional `alpha_vantage_key` field forwarded to the agent as part of the prompt; refused with 400 for stock requests when missing.
- **`POST /check`** — one threshold check for one symbol. Builds the agent prompt, returns `{ triggered: bool, message: str }`. Triggered is the literal substring `"PRICE ALERT"` in the agent's reply. Optional `alpha_vantage_key` forwarded; refused for stocks when missing.
- **No `/api/config` or `.store.json`** — the per-user key model removes any need for server-side config.

### Defense-in-depth on the API key

Three layers prevent leak / accidental shared-key fallback:
1. **UI gate** — stock-type queries and watches refuse to submit until a key is pasted.
2. **Server guard** — `/ask` and `/check` return 400 on `is_stock=true` with no key. We never silently fall back to the operator's `ALPHA_VANTAGE_API_KEY` env var for users who didn't paste their own key.
3. **Reply scrubbing** — the system prompt instructs the agent never to echo the key, AND the server runs `answer.replace(key, "[redacted]")` before returning, so an agent slip-up doesn't leak the secret to the network.

### CugaAgent

The agent fetches live prices using tools, checks whether a threshold is crossed,
and responds in natural language. It earns its place by contextualizing price
moves — not just reporting a number.

| Invocation | Input | Output |
|---|---|---|
| Browser /check tick | Symbol + threshold + direction | Price + whether threshold crossed (with `PRICE ALERT` prefix when crossed) |
| User market query | Symbol + free-form question | Natural-language answer with prices |

### Agent Tools

| Tool | What it does | API / Key required |
|---|---|---|
| `get_crypto_price` | Current price, 24h change, market cap | CoinGecko public API — no key |
| `get_stock_quote` | Current quote, change %, volume | Alpha Vantage — `ALPHA_VANTAGE_API_KEY` |

Provided by `mcp-finance`.

### Agent Instructions

Tool usage, alert format (`PRICE ALERT` sentinel), and query format are inlined as `special_instructions` in `make_agent()` inside `main.py`.

---

## Quick Start

```bash
pip install -r requirements.txt
python main.py
# open http://127.0.0.1:28801
# click "Enable browser alerts" once to grant Notification permission
```

For stock quotes, each user pastes their own free Alpha Vantage key into the
UI's "Alpha Vantage Key" field. It's saved to that browser's localStorage and
sent on every request — never persisted on the server.

(The MCP server still respects `ALPHA_VANTAGE_API_KEY` as an env-var fallback
for non-stock_alert callers, but stock_alert itself does NOT use that
fallback — see "Defense-in-depth" above.)

---

## How the Watch Loop Works (browser-driven)

```
Browser: addWatch(BTC, above, $90,000)  →  localStorage
       │
       └── setInterval(5 min, async () => {
              for each watch in localStorage:
                  POST /check { symbol, threshold, direction, is_stock }
                                  │
                                  ▼
              ┌──────────────────────────────────────────────┐
              │ Server: agent.invoke(                          │
              │   "Check BTC price. Threshold: $90,000 above.")│
              │                                                │
              │ Agent: get_crypto_price("BTC")                 │
              │ price > $90,000? → "PRICE ALERT — BTC ..."     │
              │                                                │
              │ Server: { triggered: "PRICE ALERT" in answer,  │
              │           message: answer }                    │
              └──────────────────────────────────────────────┘
                                  │
                                  ▼
              if triggered AND >30min since last fired:
                  new Notification("Stock Alert — BTC", { body, tag })
                  appendAlert(symbol, message)   → localStorage cap 50
           })

When the tab is closed, the loop stops. When it reopens, watches resume from
localStorage and visibility-change runs an immediate check if the last poll
was stale.
```

---

## Per-user isolation: how it works without accounts

There is no user identity on the server. The watch list, the alerts log, and
the Notification permission grant all live in the browser's localStorage,
which is scoped to **origin × profile × user** by the browser itself. Two
different users on two different machines (or two different browsers, or
incognito vs normal) see entirely separate watches.

The server's `/check` and `/ask` endpoints accept symbols and thresholds at
face value — they do not know who is asking, and they do not need to. Each
request opens a fresh agent thread (uuid-suffixed), so two users querying BTC
at the same time do not interleave conversation history.

Trade-off: a watch only runs while the user has a tab open to the app. Close
the tab → no notifications. This is the documented tradeoff for "no accounts,
no email, no shared state."

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `rits` \| `anthropic` \| `openai` \| `watsonx` \| `litellm` \| `ollama` |
| `LLM_MODEL` | Model name override |
| `ALPHA_VANTAGE_API_KEY` | Read by mcp-finance as a fallback for non-stock_alert callers. **Not consulted by stock_alert** — per-user keys come from the browser. |

---

## Files

| File | Purpose |
|---|---|
| `main.py` | Stateless FastAPI server: `/ask`, `/check`, `/api/*`. Inline single-page UI with localStorage watches + browser notifications. |
| `_SYSTEM` in `main.py` | Agent instructions — alert format (`PRICE ALERT` sentinel), query format, tool usage (inlined) |
| `requirements.txt` | Python dependencies |
| `.store.json` | (no longer used — server holds no state) |

Per-user state lives in browser localStorage under keys
`stock_alert.watches.v1`, `stock_alert.alerts.v1`, and `stock_alert.av_key.v1`.
