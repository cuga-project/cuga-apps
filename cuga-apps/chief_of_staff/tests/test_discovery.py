"""Tests for adapter→registry discovery sync."""

import sys
from pathlib import Path

import httpx
import pytest

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from registry.discovery import sync_from_adapter  # noqa: E402
from registry.store import ToolRegistry  # noqa: E402


@pytest.fixture
def registry(tmp_path):
    r = ToolRegistry(tmp_path / "t.sqlite")
    yield r
    r.close()


@pytest.mark.asyncio
async def test_sync_unreachable_adapter_returns_zero(registry, monkeypatch):
    n = await sync_from_adapter(registry, "http://127.0.0.1:1")  # nothing listens
    assert n == 0
    assert registry.all() == []


@pytest.mark.asyncio
async def test_sync_writes_tools(registry, monkeypatch):
    fake_payload = [
        {"name": "web_search", "description": "Search the web.", "kind": "mcp", "server": "web"},
        {"name": "get_weather", "description": "Weather lookup.", "kind": "mcp", "server": "geo"},
    ]

    class _FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return fake_payload

    class _FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url): return _FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    n = await sync_from_adapter(registry, "http://localhost:8000")
    assert n == 2
    names = sorted(r.name for r in registry.all())
    assert names == ["get_weather", "web_search"]
    sources = sorted(r.source for r in registry.all())
    assert sources == ["mcp:geo", "mcp:web"]
