"""A small MCP client session for scripts and tests, across MCP SDK versions.

mcp 2.x (installed by cuga >= 0.4.5) dropped `streamablehttp_client` and
renamed result fields (`isError` → `is_error`, `inputSchema` → `input_schema`).
`open_session(url)` hides that: it yields an object whose `list_tools()` and
`call_tool()` return plain namespaces with stable field names:

    async with open_session("http://localhost:29100/mcp") as s:
        tools = (await s.list_tools()).tools        # .name .description .inputSchema
        res = await s.call_tool("web_search", {...})  # .content .isError .text

It uses the fastmcp Client when available (the client cuga itself uses) and
falls back to the mcp 1.x ClientSession otherwise.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, AsyncIterator


def _text(content: list | None) -> str:
    return "".join(getattr(b, "text", "") or "" for b in (content or []))


def _tool_ns(t: Any) -> SimpleNamespace:
    schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
    return SimpleNamespace(
        name=t.name,
        description=t.description or "",
        inputSchema=schema or {"type": "object", "properties": {}},
    )


def _result_ns(r: Any) -> SimpleNamespace:
    is_error = getattr(r, "is_error", None)
    if is_error is None:
        is_error = getattr(r, "isError", False)
    content = list(getattr(r, "content", None) or [])
    return SimpleNamespace(content=content, isError=bool(is_error), text=_text(content))


class _FastMCPSession:
    def __init__(self, client: Any) -> None:
        self._c = client

    async def list_tools(self) -> SimpleNamespace:
        return SimpleNamespace(tools=[_tool_ns(t) for t in await self._c.list_tools()])

    async def call_tool(self, name: str, args: dict | None = None) -> SimpleNamespace:
        return _result_ns(await self._c.call_tool(name, args or {}, raise_on_error=False))


class _LegacySession:
    def __init__(self, session: Any) -> None:
        self._s = session

    async def list_tools(self) -> SimpleNamespace:
        return SimpleNamespace(tools=[_tool_ns(t) for t in (await self._s.list_tools()).tools])

    async def call_tool(self, name: str, args: dict | None = None) -> SimpleNamespace:
        return _result_ns(await self._s.call_tool(name, args or {}))


@asynccontextmanager
async def open_session(
    url: str, headers: dict[str, str] | None = None, timeout: float = 300.0
) -> AsyncIterator[Any]:
    """Open a streamable-HTTP MCP session to `url`."""
    try:
        from fastmcp import Client
        from fastmcp.client.transports import StreamableHttpTransport
    except ImportError:
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(url, headers=headers or None) as (read, write, _close):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield _LegacySession(session)
        return

    client = Client(StreamableHttpTransport(url, headers=headers or None), timeout=timeout)
    async with client:
        yield _FastMCPSession(client)
