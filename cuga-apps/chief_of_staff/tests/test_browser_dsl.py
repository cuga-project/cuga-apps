"""Tests for the browser-task DSL: validation, executor (mock), and the
adapter's browser-task dispatch path."""

import asyncio
import sys
import types
from pathlib import Path

import httpx
import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# Adapter imports cuga.sdk + langchain at module load — stub them.
for mod in ("_mcp_bridge", "_llm"):
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

from browser_runner.dsl import (  # noqa: E402
    needs_user_confirm, required_providers, validate_steps,
)
from browser_runner.executor import MockExecutor  # noqa: E402


# ─── DSL validation ──────────────────────────────────────────────────────

def test_validate_accepts_known_actions():
    steps = [
        {"go_to": "https://example.com"},
        {"wait_for_selector": "h1"},
        {"extract_text": {"selector": "h1", "as": "title"}},
    ]
    assert validate_steps(steps) == []


def test_validate_rejects_unknown_action():
    errs = validate_steps([{"frobnicate": "yes"}])
    assert len(errs) == 1
    assert "no recognized action" in errs[0]


def test_validate_rejects_multiple_actions_in_one_step():
    errs = validate_steps([{"go_to": "x", "click_text": "y"}])
    assert any("multiple actions" in e for e in errs)


def test_validate_rejects_non_dict_step():
    errs = validate_steps(["not a dict"])
    assert any("must be a non-empty dict" in e for e in errs)


def test_required_providers_picks_up_ensure_logged_in():
    steps = [
        {"go_to": "https://amazon.com"},
        {"ensure_logged_in": "amazon"},
        {"click_text": "Your Orders"},
    ]
    assert required_providers(steps) == ["amazon"]


def test_needs_user_confirm():
    assert needs_user_confirm([{"go_to": "x"}]) is False
    assert needs_user_confirm([{"go_to": "x"}, {"user_confirm": "review cart"}]) is True


# ─── MockExecutor ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_executor_runs_simple_steps():
    ex = MockExecutor()
    result = await ex.run([
        {"go_to": "https://example.com"},
        {"extract_text": {"selector": "h1", "as": "title"}},
    ])
    assert result["ok"]
    assert "title" in result["extracted"]
    assert any(c["action"] == "go_to" for c in ex.calls)


@pytest.mark.asyncio
async def test_mock_executor_rejects_invalid_steps():
    ex = MockExecutor()
    result = await ex.run([{"frobnicate": "yes"}])
    assert not result["ok"]
    assert "no recognized action" in result["reason"]


@pytest.mark.asyncio
async def test_mock_executor_user_confirm_denied_aborts():
    ex = MockExecutor()
    async def deny(_): return False
    result = await ex.run(
        [{"go_to": "x"}, {"user_confirm": "approve?"}, {"click_text": "ok"}],
        confirm_callback=deny,
    )
    assert not result["ok"]
    # Did not run the click after denial
    assert not any(c["action"] == "click_text" for c in ex.calls)


@pytest.mark.asyncio
async def test_mock_executor_probe_auto_approves():
    ex = MockExecutor()
    result = await ex.probe([{"user_confirm": "approve?"}])
    assert result["ok"]


# ─── Adapter dispatch (browser_task spec) ────────────────────────────────

@pytest.mark.asyncio
async def test_adapter_browser_task_dispatch(monkeypatch):
    """Adapter receives a kind=browser_task spec, builds a tool whose call
    posts to the browser-runner. Mock the runner."""
    sys.path.insert(0, str(_ROOT / "adapters" / "cuga"))
    from server import _build_extra_tool, set_secret_lookup

    posted_payloads = []

    class _R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"ok": True, "reason": "mock", "extracted": {"title": "Hello"}}

    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, json=None):
            posted_payloads.append({"url": url, "json": json})
            return _R()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    set_secret_lookup(lambda tool_id, key: None)

    spec = {
        "id": "browser__demo",
        "tool_name": "demo",
        "description": "Browser demo.",
        "kind": "browser_task",
        "invoke_params": {},
        "requires_secrets": [],
        "steps": [
            {"go_to": "https://example.com"},
            {"extract_text": {"selector": "h1", "as": "title"}},
        ],
    }
    tool = _build_extra_tool(spec)
    result = await tool.coroutine()
    assert result["ok"]
    assert result["extracted"]["title"] == "Hello"
    assert posted_payloads[0]["url"].endswith("/execute")
    assert posted_payloads[0]["json"]["steps"] == spec["steps"]


@pytest.mark.asyncio
async def test_adapter_browser_task_passes_secrets(monkeypatch):
    """When a browser task declares requires_secrets, the adapter pulls
    them from the vault and forwards them to /execute."""
    sys.path.insert(0, str(_ROOT / "adapters" / "cuga"))
    from server import _build_extra_tool, set_secret_lookup, _State

    captured = []

    class _R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"ok": True, "reason": "mock"}

    class _Client:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, json=None):
            captured.append(json)
            return _R()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    _State.secrets["browser__login_demo"] = {"username": "u", "password": "p"}
    set_secret_lookup(lambda tool_id, key: _State.secrets.get(tool_id, {}).get(key))

    spec = {
        "id": "browser__login_demo",
        "tool_name": "login_demo",
        "description": "Login demo.",
        "kind": "browser_task",
        "invoke_params": {},
        "requires_secrets": ["username", "password"],
        "steps": [{"go_to": "https://example.com/login"}],
    }
    tool = _build_extra_tool(spec)
    await tool.coroutine()
    assert captured[0]["secrets"] == {"username": "u", "password": "p"}
    _State.secrets.pop("browser__login_demo", None)
