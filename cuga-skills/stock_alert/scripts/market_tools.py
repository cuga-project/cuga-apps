"""CLI helpers for the stock_alert skill — stdlib only.

The agent invokes this script as a subprocess and parses JSON from stdout:

    python scripts/market_tools.py get_crypto_price btc
    python scripts/market_tools.py get_crypto_price ethereum eur
    python scripts/market_tools.py get_stock_quote AAPL
    python scripts/market_tools.py get_stock_quote NVDA <api_key>

Crypto is keyless (CoinGecko). Stocks require ALPHA_VANTAGE_API_KEY in env,
or the agent can pass the key as the 3rd positional arg (per-user keys).

Exit codes: 0 = ok, 1 = runtime error, 2 = usage error.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

_UA = {"User-Agent": "stock-alert-skill/1.0 (https://skills.sh)"}
_COINGECKO = "https://api.coingecko.com/api/v3"
_ALPHAVANTAGE = "https://www.alphavantage.co/query"

_CRYPTO_ALIASES = {
    "btc": "bitcoin", "eth": "ethereum", "sol": "solana",
    "ada": "cardano", "doge": "dogecoin", "dot": "polkadot",
    "avax": "avalanche-2", "link": "chainlink",
    "matic": "matic-network", "polygon": "matic-network",
    "xrp": "ripple", "ltc": "litecoin", "bch": "bitcoin-cash",
    "atom": "cosmos", "near": "near", "ftm": "fantom",
    "algo": "algorand", "uni": "uniswap", "aave": "aave",
}


def _http_get_json(url: str, params: dict | None = None) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def get_crypto_price(symbol: str, vs_currency: str = "usd") -> dict:
    slug = _CRYPTO_ALIASES.get(symbol.lower().strip(), symbol.lower().strip())
    try:
        data = _http_get_json(f"{_COINGECKO}/simple/price", {
            "ids": slug, "vs_currencies": vs_currency,
            "include_24hr_change": "true", "include_market_cap": "true",
        })
    except Exception as e:
        return {"error": f"CoinGecko failed: {type(e).__name__}: {e}"}
    if slug not in data:
        return {"error": f"Unknown crypto symbol {symbol!r}. Try a CoinGecko slug like 'bitcoin', 'ethereum', 'solana'."}
    d = data[slug]
    return {
        "symbol": symbol,
        "coingecko_id": slug,
        "vs_currency": vs_currency,
        "price": d.get(vs_currency),
        "change_24h": d.get(f"{vs_currency}_24h_change"),
        "market_cap": d.get(f"{vs_currency}_market_cap"),
    }


def get_stock_quote(symbol: str, api_key: str | None = None) -> dict:
    api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        return {"error": "ALPHA_VANTAGE_API_KEY not set (free tier at alphavantage.co)"}
    try:
        data = _http_get_json(_ALPHAVANTAGE, {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol.upper(),
            "apikey": api_key,
        })
    except Exception as e:
        return {"error": f"Alpha Vantage failed: {type(e).__name__}: {e}"}
    if "Note" in data or "Information" in data:
        msg = data.get("Note") or data.get("Information")
        return {"error": f"Alpha Vantage rate limit / notice: {msg}"}
    quote = data.get("Global Quote") or {}
    if not quote or not quote.get("05. price"):
        return {"error": f"No quote returned for {symbol!r}"}
    return {
        "symbol": quote.get("01. symbol", symbol),
        "price": float(quote.get("05. price", 0)),
        "change": float(quote.get("09. change", 0)),
        "change_pct": quote.get("10. change percent", ""),
        "volume": int(quote.get("06. volume", 0)),
        "previous_close": float(quote.get("08. previous close", 0)),
        "latest_day": quote.get("07. latest trading day", ""),
    }


_USAGE = """\
usage:
  python scripts/market_tools.py get_crypto_price <symbol> [vs_currency=usd]
  python scripts/market_tools.py get_stock_quote <symbol> [api_key]

Crypto is keyless (CoinGecko).
Stocks require ALPHA_VANTAGE_API_KEY in env or as the 3rd positional arg.
"""


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_USAGE, file=sys.stderr); return 2
    cmd = argv[1]
    try:
        if cmd == "get_crypto_price":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            vs = argv[3] if len(argv) > 3 else "usd"
            result: object = get_crypto_price(argv[2], vs)
        elif cmd == "get_stock_quote":
            if len(argv) < 3: print(_USAGE, file=sys.stderr); return 2
            key = argv[3] if len(argv) > 3 else None
            result = get_stock_quote(argv[2], key)
        else:
            print(f"unknown command: {cmd!r}\n\n{_USAGE}", file=sys.stderr); return 2
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
