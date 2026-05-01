"""Tests for the adapter's real-exec path: code allowlist + secret injection."""

import asyncio
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_ADAPTER = _ROOT / "adapters" / "cuga"
sys.path.insert(0, str(_ADAPTER))

# Stub the heavy imports the adapter pulls in at module load so the test
# doesn't need cuga.sdk / langchain_mcp_adapters.
import types  # noqa: E402
for mod in ("_mcp_bridge", "_llm"):
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

# Now safe to import the bits we test.
from server import (  # noqa: E402
    _CodeSecurityError, _exec_artifact_code, _build_extra_tool, set_secret_lookup,
)


def test_exec_simple_code_returns_function():
    code = """
async def hello():
    return {'msg': 'hi'}
"""
    fn = _exec_artifact_code(code, "hello")
    assert asyncio.run(fn()) == {"msg": "hi"}


def test_exec_disallowed_top_import_rejected():
    code = """
import os
async def boom():
    return os.environ
"""
    with pytest.raises(_CodeSecurityError):
        _exec_artifact_code(code, "boom")


def test_exec_disallowed_from_import_rejected():
    code = """
from subprocess import call
async def boom():
    return call(['ls'])
"""
    with pytest.raises(_CodeSecurityError):
        _exec_artifact_code(code, "boom")


def test_exec_allowed_imports_ok():
    code = """
import json, re
async def use_stdlib():
    return json.dumps(re.findall(r'[a-z]+', 'a1b2c3'))
"""
    fn = _exec_artifact_code(code, "use_stdlib")
    assert asyncio.run(fn()) == '["a", "b", "c"]'


def test_exec_function_name_must_match():
    code = "async def actual_name(): return 1"
    with pytest.raises(ValueError):
        _exec_artifact_code(code, "wrong_name")


def test_build_extra_tool_with_code_path():
    """The adapter should use the exec path when 'code' is in the spec."""
    spec = {
        "id": "openapi__sum_two",
        "tool_name": "sum_two",
        "description": "Sum two numbers.",
        "invoke_params": {
            "a": {"type": "integer", "required": True},
            "b": {"type": "integer", "required": True},
        },
        "requires_secrets": [],
        "code": "async def sum_two(a, b):\n    return {'sum': a + b}\n",
        "entry_point_function": "sum_two",
    }
    tool = _build_extra_tool(spec)
    assert tool.name == "sum_two"
    result = asyncio.run(tool.coroutine(a=2, b=3))
    assert result == {"sum": 5}


def test_build_extra_tool_injects_secrets_at_call_time():
    """Code path: secret kwargs are looked up via _secret_lookup and added
    to the call. Cuga's args_schema must NOT include them."""
    spec = {
        "id": "openapi__github_search",
        "tool_name": "github_search",
        "description": "Search.",
        "invoke_params": {"q": {"type": "string", "required": True}},
        "requires_secrets": ["github_token"],
        "code": (
            "async def github_search(q, github_token):\n"
            "    return {'q': q, 'token_seen': github_token}\n"
        ),
        "entry_point_function": "github_search",
    }
    set_secret_lookup(lambda tool_id, key: "ghp_test_token" if key == "github_token" else None)
    tool = _build_extra_tool(spec)
    # github_token should NOT be in the LangChain args schema.
    schema_fields = tool.args_schema.model_fields if hasattr(tool.args_schema, "model_fields") else {}
    assert "github_token" not in schema_fields
    assert "q" in schema_fields

    result = asyncio.run(tool.coroutine(q="hello"))
    assert result == {"q": "hello", "token_seen": "ghp_test_token"}


def test_build_extra_tool_missing_secret_errors_at_call():
    spec = {
        "id": "openapi__needs_token",
        "tool_name": "needs_token",
        "description": "x.",
        "invoke_params": {},
        "requires_secrets": ["api_key"],
        "code": "async def needs_token(api_key): return {'ok': True}\n",
        "entry_point_function": "needs_token",
    }
    set_secret_lookup(lambda tool_id, key: None)
    tool = _build_extra_tool(spec)
    with pytest.raises(RuntimeError, match="missing secret"):
        asyncio.run(tool.coroutine())


def test_build_extra_tool_disallowed_import_returns_error_stub():
    """Spec with code that imports os should NOT crash adapter load —
    instead a stub tool is registered that raises on call."""
    spec = {
        "id": "bad",
        "tool_name": "bad_tool",
        "description": "x.",
        "invoke_params": {},
        "requires_secrets": [],
        "code": "import os\nasync def bad_tool(): return os.environ['HOME']\n",
        "entry_point_function": "bad_tool",
    }
    tool = _build_extra_tool(spec)
    # Tool registered but errors at call time.
    with pytest.raises(RuntimeError, match="disabled"):
        asyncio.run(tool.coroutine())


def test_build_extra_tool_fallback_path_no_code():
    """Specs without 'code' use the param-substitution fallback (catalog mounts)."""
    spec = {
        "tool_name": "fallback_tool",
        "description": "x",
        "invoke_url": "https://example.com/api",
        "invoke_method": "GET",
        "invoke_params": {"q": {"type": "string", "required": True}},
        "requires_secrets": [],
    }
    tool = _build_extra_tool(spec)
    assert tool.name == "fallback_tool"
    # We don't make a real HTTP call here; just confirm the wrapping chose
    # the fallback path (no exec happened).
