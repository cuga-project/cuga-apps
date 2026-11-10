"""Shared FastMCP bootstrap so each server's entrypoint is two lines."""
from __future__ import annotations

import logging
import os

try:
    # Standalone FastMCP (>= 4) — what cuga >= 0.4.5 installs alongside mcp 2.x,
    # which no longer bundles mcp.server.fastmcp.
    from fastmcp import FastMCP
    _STANDALONE = True
except ImportError:  # older stack: mcp 1.x with its bundled FastMCP
    from mcp.server.fastmcp import FastMCP  # type: ignore[no-redef]
    _STANDALONE = False


def make_server(name: str) -> FastMCP:
    """Create a FastMCP instance with standard logging + settings."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  [" + name + "]  %(message)s",
        datefmt="%H:%M:%S",
    )
    return FastMCP(name)


def run(server: FastMCP, port: int) -> None:
    """Run the server as streamable-HTTP on <host>:<port>/mcp, binding all ifaces."""
    host = os.getenv("MCP_BIND_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT_OVERRIDE", str(port)))
    if _STANDALONE:
        # FastMCP 4 validates the Host header only for loopback binds ("auto"
        # mode), so a 0.0.0.0 bind stays reachable by compose service DNS and
        # by Code Engine's public hostname without extra settings.
        server.run(transport="http", host=host, port=port, path="/mcp", show_banner=False)
        return
    server.settings.host = host
    server.settings.port = port
    # mcp 1.x FastMCP turns on a localhost-only Host allow-list when it sees the
    # default host at construction time; turn it off for non-loopback binds.
    if host not in ("127.0.0.1", "localhost", "::1"):
        server.settings.transport_security.enable_dns_rebinding_protection = False
    server.run(transport="streamable-http")
