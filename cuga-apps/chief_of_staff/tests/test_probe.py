"""Tests for the probe harness — the autoresearch keep/discard gate."""

import sys
from pathlib import Path

import httpx
import pytest

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from acquisition.probe import _format_url, probe_realized_tool  # noqa: E402
from acquisition.sources.base import RealizedTool  # noqa: E402


def _tool(**overrides) -> RealizedTool:
    base = RealizedTool(
        proposal_id="openapi:test",
        tool_name="get_test",
        description="Test tool",
        invoke_url="https://example.com/api/test",
        invoke_method="GET",
        invoke_params={},
        sample_input={},
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_format_url_path_param_substitution():
    t = _tool(invoke_url="https://x.test/{name}/info", sample_input={"name": "France", "fields": "capital"})
    url, params, body = _format_url(t)
    assert url == "https://x.test/France/info"
    assert params == {"fields": "capital"}
    assert body == {}


def test_format_url_post_uses_body():
    t = _tool(invoke_method="POST", sample_input={"a": 1, "b": 2})
    _, params, body = _format_url(t)
    assert params == {}
    assert body == {"a": 1, "b": 2}


def test_format_url_missing_path_param_raises():
    t = _tool(invoke_url="https://x.test/{name}", sample_input={})
    with pytest.raises(ValueError):
        _format_url(t)


@pytest.mark.asyncio
async def test_probe_unreachable_returns_not_ok(monkeypatch):
    t = _tool(invoke_url="https://127.0.0.1:1/")
    result = await probe_realized_tool(t, timeout=1.0)
    assert result["ok"] is False
    assert "network error" in result["reason"]


@pytest.mark.asyncio
async def test_probe_404_returns_not_ok(monkeypatch):
    class _R:
        status_code = 404
        text = "Not Found"
        def json(self): raise ValueError()
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def request(self, *a, **kw): return _R()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    result = await probe_realized_tool(_tool())
    assert result["ok"] is False
    assert "http 404" in result["reason"]


@pytest.mark.asyncio
async def test_probe_empty_payload_rejected(monkeypatch):
    class _R:
        status_code = 200
        text = "[]"
        def json(self): return []
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def request(self, *a, **kw): return _R()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    result = await probe_realized_tool(_tool())
    assert result["ok"] is False
    assert "empty" in result["reason"]


@pytest.mark.asyncio
async def test_probe_non_json_rejected(monkeypatch):
    class _R:
        status_code = 200
        text = "<html>not json</html>"
        def json(self): raise ValueError("bad json")
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def request(self, *a, **kw): return _R()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    result = await probe_realized_tool(_tool())
    assert result["ok"] is False
    assert "non-JSON" in result["reason"]


@pytest.mark.asyncio
async def test_probe_valid_payload_accepted(monkeypatch):
    payload = {"name": "France", "capital": "Paris"}
    class _R:
        status_code = 200
        text = '{"name": "France"}'
        def json(self): return payload
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def request(self, *a, **kw): return _R()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    result = await probe_realized_tool(_tool())
    assert result["ok"] is True
    assert result["status_code"] == 200
    assert result["response"] == payload


@pytest.mark.asyncio
async def test_probe_judge_can_reject(monkeypatch):
    """Even a structurally-valid response should be rejected if the LLM
    judge says it doesn't look like real data."""
    class _R:
        status_code = 200
        text = '{"placeholder": "fake"}'
        def json(self): return {"placeholder": "fake"}
    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def request(self, *a, **kw): return _R()
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    class _Resp:
        content = '{"plausible": false, "reason": "obviously placeholder data"}'

    class _LLM:
        async def ainvoke(self, msgs):
            return _Resp()

    result = await probe_realized_tool(_tool(), llm=_LLM())
    assert result["ok"] is False
    assert "judge" in result["reason"]
