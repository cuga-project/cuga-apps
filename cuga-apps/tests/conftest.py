"""
Shared test fixtures and helpers for the cuga-apps integration suite.

These tests are *real* integration tests — they hit the live stack started by
`docker compose up`. They never mock. If the stack isn't up, they skip the
whole session with a clear message rather than failing.

Run from repo root:
    pip install -r requirements.test.txt
    docker compose up -d        # start the stack first
    pytest                      # smoke + mcp + wiring (default)
    pytest -m llm               # add the slow LLM tier
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APPS_DIR = REPO_ROOT / "apps"
sys.path.insert(0, str(APPS_DIR))
sys.path.insert(0, str(REPO_ROOT))

from apps._ports import APP_PORTS, MCP_PORTS  # noqa: E402

UI_PORT = 3001
TOOL_EXPLORER_PORT = 28900
DEFAULT_HOST = os.getenv("CUGA_TEST_HOST", "localhost")


def _tcp_alive(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ── session-level guard ─────────────────────────────────────────────────────

def pytest_collection_modifyitems(config, items):
    """If the stack is clearly down, skip all tests with a clear message
    rather than letting hundreds of httpx errors scroll by."""
    if not _tcp_alive(DEFAULT_HOST, UI_PORT):
        skip = pytest.mark.skip(
            reason=(
                f"cuga-apps stack appears down on {DEFAULT_HOST} "
                f"(UI port {UI_PORT} not listening). "
                "Run `docker compose up -d` from cuga-apps/ first."
            )
        )
        for item in items:
            item.add_marker(skip)


# ── markers based on environment ────────────────────────────────────────────

def pytest_runtest_setup(item):
    """Skip tests that need an API key the host hasn't set."""
    for marker in item.iter_markers(name="needs_key"):
        for key_name in marker.args:
            if not os.getenv(key_name):
                pytest.skip(f"requires {key_name} env var (set it to run this test)")


# ── helpers ─────────────────────────────────────────────────────────────────

def app_url(app: str) -> str:
    return f"http://{DEFAULT_HOST}:{APP_PORTS[app]}"


def mcp_url(server: str) -> str:
    return f"http://{DEFAULT_HOST}:{MCP_PORTS[server]}/mcp"


def explorer_url() -> str:
    return f"http://{DEFAULT_HOST}:{TOOL_EXPLORER_PORT}"


@asynccontextmanager
async def mcp_session(server: str):
    """Open an MCP streamable-http session to the named server."""
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with streamablehttp_client(mcp_url(server)) as (read, write, _close):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def call_mcp_tool(server: str, tool: str, args: dict | None = None, timeout: float = 60.0):
    """Synchronous wrapper around an MCP tool call. Returns the parsed envelope.

    Returns the dict from `tool_result(...)`/`tool_error(...)` — i.e. one of:
        {"ok": True,  "data": ...}
        {"ok": False, "error": "...", "code": "..."}
    """
    async def _run():
        async with mcp_session(server) as s:
            result = await s.call_tool(tool, args or {})
            text = "".join(getattr(b, "text", "") for b in (result.content or []))
            return json.loads(text) if text else None
    return asyncio.run(asyncio.wait_for(_run(), timeout=timeout))


def http_ok(url: str, timeout: float = 10.0) -> int:
    r = httpx.get(url, timeout=timeout, follow_redirects=False)
    return r.status_code


@pytest.fixture(scope="session")
def http():
    """Shared httpx client with sensible timeout."""
    with httpx.Client(timeout=30.0, follow_redirects=False) as c:
        yield c
