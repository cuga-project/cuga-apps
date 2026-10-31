"""
Unit tests for the quote-currency handling in mcp-finance's get_crypto_price.
CoinGecko accepts any case in the vs_currencies parameter but always answers
with lowercase keys, so a caller passing "USD" got a successful-looking result
whose price, change_24h and market_cap were all null.
"""
from __future__ import annotations

import json

import pytest

from mcp_servers.finance import server as finance_server

pytestmark = pytest.mark.unit


def _coingecko_reply(url, params=None):
    # What the real API returns for vs_currencies in any case: lowercase keys.
    return {
        "bitcoin": {
            "usd": 50000.0,
            "usd_24h_change": 1.25,
            "usd_market_cap": 1.0e12,
        }
    }


def test_uppercase_quote_currency_still_yields_values(monkeypatch):
    monkeypatch.setattr(finance_server, "get_json", _coingecko_reply)
    out = json.loads(finance_server.get_crypto_price("btc", "USD"))

    assert out["ok"] is True
    assert out["data"]["price"] == 50000.0
    assert out["data"]["change_24h"] == 1.25
    assert out["data"]["market_cap"] == 1.0e12
    assert out["data"]["vs_currency"] == "usd"


def test_quote_currency_is_sent_lowercase(monkeypatch):
    seen = {}

    def capture(url, params=None):
        seen.update(params or {})
        return _coingecko_reply(url, params)

    monkeypatch.setattr(finance_server, "get_json", capture)
    json.loads(finance_server.get_crypto_price("btc", " Usd "))

    assert seen["vs_currencies"] == "usd"


def test_lowercase_quote_currency_unchanged(monkeypatch):
    monkeypatch.setattr(finance_server, "get_json", _coingecko_reply)
    out = json.loads(finance_server.get_crypto_price("btc", "usd"))

    assert out["ok"] is True
    assert out["data"]["price"] == 50000.0
