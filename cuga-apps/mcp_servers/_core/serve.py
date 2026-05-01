"""Shared FastMCP bootstrap so each server's entrypoint is two lines."""
from __future__ import annotations

import logging
import os

from mcp.server.fastmcp import FastMCP


def make_server(name: str) -> FastMCP:
    """Create a FastMCP instance with standard logging + settings."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  [" + name + "]  %(message)s",
        datefmt="%H:%M:%S",
    )
    # FastMCP derives the HTTP mount path (default "/mcp") from its settings.
    return FastMCP(name)


def run(server: FastMCP, port: int) -> None:
    """Run the server as streamable-HTTP on the given port, binding all ifaces."""
    server.settings.host = os.getenv("MCP_BIND_HOST", "0.0.0.0")
    server.settings.port = int(os.getenv("MCP_PORT_OVERRIDE", str(port)))
    # FastMCP auto-enables DNS rebinding protection (localhost-only Host
    # allow-list) because it sees the default host=127.0.0.1 at construction
    # time. We bind to 0.0.0.0 afterward so the compose sibling containers
    # can reach us by service DNS — turn the localhost-only check off to
    # match, mirroring FastMCP's own "only protect loopback binds" logic.
    if server.settings.host not in ("127.0.0.1", "localhost", "::1"):
        server.settings.transport_security.enable_dns_rebinding_protection = False
    server.run(transport="streamable-http")
