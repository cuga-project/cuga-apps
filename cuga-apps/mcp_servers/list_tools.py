"""List every tool on every MCP server in mcp.client.json.

Usage (from cuga-apps/):
    pip install mcp
    python -m mcp_servers.list_tools

Reads the `mcpServers` block from mcp_servers/mcp.client.json (the same file
you'd hand to a teammate or paste into Claude Desktop), opens a streamable-HTTP
MCP session to each, and prints the tool catalog.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

_CONFIG = Path(__file__).resolve().parent / "mcp.client.json"


async def list_server_tools(name: str, url: str) -> None:
    print(f"\n── {name} ──  {url}")
    try:
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                if not result.tools:
                    print("  (no tools)")
                    return
                for t in result.tools:
                    desc = (t.description or "").strip().splitlines()[0] if t.description else ""
                    print(f"  • {t.name:<28s} {desc}")
    except Exception as exc:
        print(f"  ! failed: {exc}")


async def main() -> None:
    config = json.loads(_CONFIG.read_text())
    servers: dict[str, dict] = config.get("mcpServers", {})
    if not servers:
        raise SystemExit(f"No `mcpServers:` block found in {_CONFIG}")

    print(f"Discovered {len(servers)} server(s) in {_CONFIG.name}")
    for name, spec in servers.items():
        await list_server_tools(name, spec["url"])


if __name__ == "__main__":
    asyncio.run(main())
