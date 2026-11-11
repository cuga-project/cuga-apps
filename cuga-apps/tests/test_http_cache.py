"""
Unit tests for the GET response cache in mcp_servers._core.http (#50).

These run in-process with a stubbed httpx client — no stack, no network.
"""
from __future__ import annotations

import httpx
import pytest

from mcp_servers._core import http as core_http

pytestmark = pytest.mark.unit


class _StubClient:
    """Stands in for httpx.Client: serves canned responses and counts calls."""

    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None, headers=None):
        self.calls.append((url, params))
        status, payload = self._responses[len(self.calls) - 1]
        return httpx.Response(
            status, json=payload, request=httpx.Request("GET", url)
        )


@pytest.fixture(autouse=True)
def _empty_cache():
    core_http._cache.clear()
    yield
    core_http._cache.clear()


def _serve(monkeypatch, responses) -> _StubClient:
    stub = _StubClient(responses)
    monkeypatch.setattr(core_http, "_client", lambda: stub)
    return stub


def test_repeat_get_is_served_from_cache(monkeypatch):
    # Second response would be a 429; the cache means it is never requested.
    stub = _serve(monkeypatch, [(200, {"bitcoin": {"usd": 1}}), (429, {})])
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "bitcoin", "vs_currencies": "usd"}

    first = core_http.get_json(url, params=params, cache_ttl=60)
    second = core_http.get_json(url, params=params, cache_ttl=60)

    assert first == second == {"bitcoin": {"usd": 1}}
    assert len(stub.calls) == 1


def test_cache_ttl_zero_bypasses_cache(monkeypatch):
    stub = _serve(monkeypatch, [(200, {"n": 1}), (200, {"n": 2})])

    first = core_http.get_json("https://example.org/live", cache_ttl=0)
    second = core_http.get_json("https://example.org/live", cache_ttl=0)

    assert (first, second) == ({"n": 1}, {"n": 2})
    assert len(stub.calls) == 2


def test_different_params_are_cached_separately(monkeypatch):
    stub = _serve(monkeypatch, [(200, {"q": "a"}), (200, {"q": "b"})])
    url = "https://example.org/search"

    a = core_http.get_json(url, params={"q": "a"}, cache_ttl=60)
    b = core_http.get_json(url, params={"q": "b"}, cache_ttl=60)

    assert a != b
    assert len(stub.calls) == 2


def test_expired_entry_is_refetched(monkeypatch):
    stub = _serve(monkeypatch, [(200, {"n": 1}), (200, {"n": 2})])
    clock = iter([100.0, 300.0, 300.0])
    monkeypatch.setattr(core_http.time, "monotonic", lambda: next(clock))

    first = core_http.get_json("https://example.org/a", cache_ttl=60)
    second = core_http.get_json("https://example.org/a", cache_ttl=60)

    assert (first, second) == ({"n": 1}, {"n": 2})
    assert len(stub.calls) == 2


def test_error_responses_are_not_cached(monkeypatch):
    stub = _serve(monkeypatch, [(404, {}), (200, {"ok": True})])

    with pytest.raises(httpx.HTTPStatusError):
        core_http.get_json("https://example.org/missing", cache_ttl=60)
    recovered = core_http.get_json("https://example.org/missing", cache_ttl=60)

    assert recovered == {"ok": True}
    assert len(stub.calls) == 2


def test_lru_eviction_past_cache_max(monkeypatch):
    monkeypatch.setattr(core_http, "_CACHE_MAX", 2)
    stub = _serve(
        monkeypatch,
        [(200, {"n": 1}), (200, {"n": 2}), (200, {"n": 3}), (200, {"n": 4})],
    )

    core_http.get_json("https://example.org/1", cache_ttl=60)
    core_http.get_json("https://example.org/2", cache_ttl=60)
    core_http.get_json("https://example.org/3", cache_ttl=60)  # evicts /1
    refetched = core_http.get_json("https://example.org/1", cache_ttl=60)

    assert refetched == {"n": 4}
    assert len(stub.calls) == 4
