"""Smoke tests — every endpoint in the stack responds.

If any of these fail, the rest of the suite will fail too. They're cheap
(<5s total) and catch the most common breakage: a container crashed, a port
shifted, a service is wedged.
"""
from __future__ import annotations

import pytest

from .conftest import (
    APP_PORTS, MCP_PORTS, UI_PORT, TOOL_EXPLORER_PORT,
    DEFAULT_HOST, http_ok, mcp_url, app_url, explorer_url,
)


pytestmark = pytest.mark.smoke


# ── UI surfaces ─────────────────────────────────────────────────────────

def test_umbrella_ui_serves_root():
    code = http_ok(f"http://{DEFAULT_HOST}:{UI_PORT}/")
    assert code in (200, 304), f"umbrella UI returned {code}"


def test_tool_explorer_serves_root():
    code = http_ok(f"http://{DEFAULT_HOST}:{TOOL_EXPLORER_PORT}/")
    assert code == 200


def test_tool_explorer_lists_all_seven_servers(http):
    r = http.get(f"{explorer_url()}/api/servers", timeout=10)
    assert r.status_code == 200
    servers = r.json()
    names = {s["name"] for s in servers}
    assert names == set(MCP_PORTS), f"expected {set(MCP_PORTS)}, got {names}"
    offline = [s["name"] for s in servers if not s["online"]]
    assert not offline, f"servers offline: {offline}"


# Apps that are intentionally NOT started by docker compose (local-only).
# The smoke suite assumes the docker compose stack is up; these are skipped.
_LOCAL_ONLY_APPS = {"code_engine_deployer"}


# ── apps reachable ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "app",
    sorted(set(APP_PORTS.keys()) - _LOCAL_ONLY_APPS),
)
def test_app_serves_root(app):
    """Every app FastAPI serves a 2xx/3xx on `/`."""
    code = http_ok(app_url(app) + "/")
    # Some apps redirect (3xx), some serve HTML (200), some serve docs (200).
    assert 200 <= code < 400, f"{app} returned {code}"


# ── MCP servers reachable ───────────────────────────────────────────────

@pytest.mark.parametrize("server", sorted(MCP_PORTS.keys()))
def test_mcp_server_tcp_listening(server):
    """Every MCP server's TCP port accepts connections."""
    import socket
    with socket.create_connection((DEFAULT_HOST, MCP_PORTS[server]), timeout=2):
        pass


@pytest.mark.parametrize("server", sorted(MCP_PORTS.keys()))
def test_mcp_server_responds_to_mcp_handshake(http, server):
    """Tool explorer can introspect every server (validates the MCP protocol works)."""
    r = http.get(f"{explorer_url()}/api/servers/{server}/tools", timeout=15)
    assert r.status_code == 200, f"explorer {server} → {r.status_code}: {r.text[:200]}"
    tools = r.json().get("tools", [])
    assert isinstance(tools, list)
    assert tools, f"mcp-{server} returned an empty tool list"
