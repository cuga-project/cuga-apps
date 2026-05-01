# Stock Alert — Architecture

## Design principle

**The browser owns the schedule, state, and delivery. The server owns price
fetching and threshold judgment. Per-user isolation is structural — every
browser is its own world, no accounts, no shared state.**

The threshold check is not a simple `price > X` rule — the agent contextualizes
the move ("continuing a 4-day rally" vs. "spike on low volume") and the system
prompt instructs it to include a `PRICE ALERT` sentinel only when the
threshold is genuinely crossed. The server reads that sentinel and returns
`{ triggered: bool, message: str }`; the browser fires the notification.

---

## Component map

```
┌───────────────────────────────────────────────────────────────────┐
│ Browser (per-user — different browsers = different state)         │
│                                                                   │
│  ┌──────────────────────────────────────────┐                     │
│  │ localStorage                              │                    │
│  │   stock_alert.watches.v1   [...watches]  │                     │
│  │   stock_alert.alerts.v1    [...history]  │                     │
│  └──────────────────────────────────────────┘                     │
│                                                                   │
│  setInterval(5 min, async () => {                                 │
│    for each watch in localStorage:                                │
│      POST /check { symbol, threshold, direction, is_stock }       │
│      if triggered AND >30min since last fire:                     │
│        new Notification("Stock Alert — SYM", { body, tag })       │
│        appendAlert(...)                                           │
│  })                                                               │
└────────────────┬──────────────────────────────────────────────────┘
                 │  (stateless HTTP — no user identity)
                 ▼
┌───────────────────────────────────────────────────────────────────┐
│ Server (main.py — FastAPI)                                        │
│                                                                   │
│  POST /check  ─┐                                                  │
│  POST /ask    ─┤                                                  │
│                │                                                  │
│                ▼                                                  │
│         ┌──────────────────┐                                      │
│         │   CugaAgent      │  fresh thread per call (uuid)        │
│         │                  │                                      │
│         │ tools (mcp-      │                                      │
│         │  finance):       │                                      │
│         │  get_crypto_price│ ← CoinGecko API                      │
│         │  get_stock_quote │ ← Alpha Vantage API                  │
│         │                  │                                      │
│         │ system prompt:   │                                      │
│         │  inlined _SYSTEM │  emits "PRICE ALERT" on cross        │
│         │                  │                                      │
│         │ → response       │                                      │
│         └────┬─────────────┘                                      │
│              │                                                    │
│              ▼                                                    │
│   "PRICE ALERT" in response → triggered=true                      │
│   Return { symbol, triggered, message }                           │
└───────────────────────────────────────────────────────────────────┘
```

---

## What the browser owns

| Responsibility | How |
|---|---|
| Watch list per user | `localStorage['stock_alert.watches.v1']` |
| Alerts log per user | `localStorage['stock_alert.alerts.v1']` (capped at 50) |
| **Alpha Vantage key per user** | `localStorage['stock_alert.av_key.v1']` |
| Polling cadence | `setInterval(checkAll, 5 * 60 * 1000)` |
| Wake-from-sleep recovery | `visibilitychange` listener runs `checkAll()` if last poll is stale |
| Notification permission | `Notification.requestPermission()` once; status surfaced in UI |
| Notification dedup | per-symbol `tag` collapses repeats; 30-min cooldown per watch |
| Per-user isolation | localStorage is browser-profile-scoped; no server-side identity |
| UI gate on stocks | Stock-type queries / watches refuse to submit until a key is pasted |

## What the server owns

| Responsibility | How |
|---|---|
| Price fetching | mcp-finance tool calls — no HTTP code in this app |
| Threshold judgment | Agent decides — system prompt defines `PRICE ALERT` semantics |
| Sentinel detection | Server-side `"PRICE ALERT" in answer` substring check |
| Concurrent-user safety | Fresh `thread_id` per `/ask` and `/check` (uuid suffix) |
| Per-user-key forwarding | Browser-supplied `alpha_vantage_key` injected into the agent prompt; agent passes as `api_key` arg to `get_stock_quote` |
| Stock-without-key guard | `/ask` and `/check` return 400 on `is_stock=true` with no key (no silent env-var fallback) |
| API key scrubbing | `answer.replace(key, "[redacted]")` before returning, in case the agent leaks |
| Persistent state | None. The server holds no per-user data. |

---

## Agent configuration

```python
CugaAgent(
    model              = create_llm(...),
    tools              = load_tools(["finance"]),  # mcp-finance
    special_instructions = _SYSTEM,                # inlined in main.py
    cuga_folder        = "./.cuga",
)
```

## Agent tools

| Tool | Source | Key needed |
|---|---|---|
| `get_crypto_price(symbol)` | CoinGecko `/simple/price` (via mcp-finance) | No |
| `get_stock_quote(symbol)` | Alpha Vantage `GLOBAL_QUOTE` (via mcp-finance) | `ALPHA_VANTAGE_API_KEY` |

Both tools come from the shared `mcp-finance` server and return structured
data (price, 24h change %, volume, market cap where applicable).

---

## Check data flow

```
1.  Browser (every 5 min, per watch) — for stocks, includes the user's key:
      POST /check {
        symbol: "AAPL", threshold: 200, direction: "above", is_stock: true,
        alpha_vantage_key: "<from localStorage['stock_alert.av_key.v1']>"
      }

2.  Server: if is_stock=true and no key → 400. Else build prompt with a
    leading "Alpha Vantage API key: <k>" line and forward to the agent:
    agent.invoke(
      "Alpha Vantage API key: <k>\n(Use as get_stock_quote api_key, do not echo)\n"
      "Check AAPL (stock) price now. Alert threshold: $200.00 (above).",
      thread_id="check-aapl-<uuid>"
    )
      → agent calls get_stock_quote(symbol="AAPL", api_key="<k>")
        → mcp-finance hits Alpha Vantage with the per-user key
        → { price: 215.4, change_pct: "+1.2%" }
      → price > 200 → agent includes "PRICE ALERT" in response

3.  Server scrubs the key out of the answer (defense-in-depth) and returns:
      { symbol: "AAPL", triggered: true,
        message: "PRICE ALERT\nAAPL crossed above $200 at $215.40..." }

4.  Browser:
      if triggered AND (Date.now() - lastTriggeredAt) >= 30 min:
        new Notification("Stock Alert — BTC", { body: message, tag: "stock-alert-BTC" })
        appendAlert("BTC", message)  → localStorage
        update watch.lastTriggeredAt
      always: update watch.lastCheckedAt
```

## Market query data flow

```
1.  Browser: POST /ask { symbol: "ETH", question: "compare with SOL", is_stock: false }

2.  Server: agent.invoke(
      "Symbol: ETH (crypto)\nQuestion: compare with SOL",
      thread_id="query-eth-<uuid>"
    )
      → get_crypto_price("ETH") → { price: 3410, change_24h: +1.2% }
      → get_crypto_price("SOL") → { price: 142, change_24h: -0.4% }
      → "ETH $3,410 (+1.2%)  ·  SOL $142 (-0.4%)..."

3.  Browser renders the answer (no persistence — it's just a query).
```

---

## Per-user isolation: why this works without accounts

The server has no notion of user identity. Two users hitting `/check` from
different browsers send the same shape of request and get the same shape of
response — but the response goes back only to that one HTTP caller, who
appends it to that browser's localStorage. There's no server-side fan-out, no
shared state to leak, and no cross-user thread contamination (each call gets
its own uuid-suffixed agent thread).

The browser's localStorage is scoped by the browser to (origin, profile,
user), so:
- Different machines → different watches.
- Same machine, different browsers (Chrome vs Firefox) → different watches.
- Same browser, normal vs incognito → different watches.
- Same browser, different OS users → different watches.

This is the multi-user story for a "no signup, just open the link" demo. The
trade-off is documented: a watch only runs while a tab is open. Close the
tab → no notifications. To get notifications when the tab is closed, you'd
need either a server-side per-user store (with identity) or a transactional
email service (with verification). Both are bigger features than this app
intentionally takes on.

---

## Alert sentinel design

The system prompt instructs the agent to begin its response with `PRICE ALERT`
when and only when the threshold is crossed. The server checks for this exact
string and returns `triggered: bool` to the browser. This keeps the LLM-side
contract simple (one substring) while letting the agent contextualize the move
in the rest of the response. No JSON parsing, no structured output schema, no
function-calling for delivery — just one sentinel and the browser does
delivery.
