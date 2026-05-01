"""mcp-finance — crypto + stock price primitives.

Tools:
  - get_crypto_price(symbol)   CoinGecko (free)
  - get_stock_quote(symbol)    Alpha Vantage (ALPHA_VANTAGE_API_KEY)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SERVERS_ROOT = _HERE.parent
if str(_SERVERS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_SERVERS_ROOT.parent))

from mcp_servers._core import tool_error, tool_result, get_json
from mcp_servers._core.serve import make_server, run
from apps._ports import MCP_FINANCE_PORT  # noqa: E402

mcp = make_server("mcp-finance")

_COINGECKO = "https://api.coingecko.com/api/v3"
_ALPHAVANTAGE = "https://www.alphavantage.co/query"

# Common CoinGecko ID mappings — CoinGecko uses slugs, not tickers.
_CRYPTO_ALIASES = {
    "btc": "bitcoin",   "bitcoin": "bitcoin",
    "eth": "ethereum",  "ethereum": "ethereum",
    "sol": "solana",    "solana": "solana",
    "ada": "cardano",   "cardano": "cardano",
    "doge": "dogecoin", "dogecoin": "dogecoin",
    "dot": "polkadot",  "polkadot": "polkadot",
    "avax": "avalanche-2", "avalanche": "avalanche-2",
    "link": "chainlink", "chainlink": "chainlink",
    "matic": "matic-network", "polygon": "matic-network",
    "xrp": "ripple",    "ripple": "ripple",
}


@mcp.tool()
def get_crypto_price(symbol: str, vs_currency: str = "usd") -> str:
    """Fetch current price + 24h change for a cryptocurrency via CoinGecko.

    Accepts common tickers (btc, eth, sol) or CoinGecko slugs (bitcoin,
    ethereum, solana). No API key required.

    Args:
        symbol: Crypto ticker or CoinGecko slug.
        vs_currency: Quote currency (default "usd").
    """
    slug = _CRYPTO_ALIASES.get(symbol.lower().strip(), symbol.lower().strip())
    try:
        data = get_json(
            f"{_COINGECKO}/simple/price",
            params={
                "ids": slug,
                "vs_currencies": vs_currency,
                "include_24hr_change": "true",
                "include_market_cap": "true",
            },
        )
        if slug not in data:
            return tool_error(
                f"Unknown crypto symbol '{symbol}'. Try bitcoin, ethereum, solana, etc.",
                code="not_found",
            )
        d = data[slug]
        return tool_result({
            "symbol":       symbol,
            "coingecko_id": slug,
            "vs_currency":  vs_currency,
            "price":        d.get(vs_currency),
            "change_24h":   d.get(f"{vs_currency}_24h_change"),
            "market_cap":   d.get(f"{vs_currency}_market_cap"),
        })
    except Exception as exc:
        return tool_error(f"CoinGecko failed: {exc}", code="upstream")


@mcp.tool()
def get_stock_quote(symbol: str, api_key: str | None = None) -> str:
    """Fetch a real-time stock quote via Alpha Vantage.

    Args:
        symbol:  Stock ticker (e.g. "AAPL", "NVDA", "SPY").
        api_key: Optional caller-supplied Alpha Vantage key. When provided it
                 takes precedence over the server-side ALPHA_VANTAGE_API_KEY
                 env var — lets multi-user apps pass per-user keys instead of
                 sharing one quota.

    Env:
        ALPHA_VANTAGE_API_KEY (fallback when api_key is not provided).
        Free tier = 25 requests/day, so cache aggressively in the caller.
    """
    api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        return tool_error(
            "Alpha Vantage key not provided — pass api_key as a tool argument "
            "or set ALPHA_VANTAGE_API_KEY on the MCP server.",
            code="missing_key")
    try:
        data = get_json(_ALPHAVANTAGE, params={
            "function": "GLOBAL_QUOTE",
            "symbol": symbol.upper(),
            "apikey": api_key,
        })
    except Exception as exc:
        return tool_error(f"Alpha Vantage failed: {exc}", code="upstream")

    if "Note" in data or "Information" in data:
        msg = data.get("Note") or data.get("Information")
        return tool_error(f"Alpha Vantage rate limit or notice: {msg}", code="rate_limit")
    quote = data.get("Global Quote") or {}
    if not quote or not quote.get("05. price"):
        return tool_error(f"No quote returned for '{symbol}'.", code="not_found")
    return tool_result({
        "symbol":        quote.get("01. symbol", symbol),
        "price":         float(quote.get("05. price", 0)),
        "change":        float(quote.get("09. change", 0)),
        "change_pct":    quote.get("10. change percent", ""),
        "volume":        int(quote.get("06. volume", 0)),
        "previous_close":float(quote.get("08. previous close", 0)),
        "latest_day":    quote.get("07. latest trading day", ""),
    })


if __name__ == "__main__":
    run(mcp, MCP_FINANCE_PORT)
