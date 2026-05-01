"""
LangChain ↔ MCP bridge.

Apps call `load_tools(["web", "knowledge", ...])` to obtain a list of LangChain
StructuredTools that, when invoked, round-trip through the named MCP servers
over streamable HTTP.

The server URL for each name is resolved from:
  1. MCP_<NAME>_URL env var (e.g. MCP_WEB_URL)  — explicit override
  2. Default based on whether we're inside docker:
     - docker:  http://mcp-<name>:<port>/mcp    (compose service DNS)
     - local:   http://localhost:<port>/mcp
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import List

# Make apps/_ports.py importable whether launched from repo root or apps/
_HERE = Path(__file__).resolve().parent
for p in (str(_HERE), str(_HERE.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from _ports import MCP_PORTS

log = logging.getLogger(__name__)

_IN_DOCKER = Path("/.dockerenv").exists() or os.getenv("CUGA_IN_DOCKER") == "1"

# Detect Code Engine. CE injects CE_APP / CE_REVISION on every runtime;
# CUGA_TARGET=ce is the manual escape hatch for non-CE hosts that want to
# pretend (debug runs, CI smoke tests).
_ON_CE = bool(
    os.getenv("CE_APP")
    or os.getenv("CE_REVISION")
    or (os.getenv("CUGA_TARGET", "") or "").lower() == "ce"
)

# Default CE project hardcodes. CE also injects CE_SUBDOMAIN (project hash)
# and CE_REGION at runtime — we prefer those when present, fall back to the
# constants below for non-CE / debug invocations. Change these two strings
# if you redeploy in a different CE project or region.
_CE_PROJECT_HASH_DEFAULT = "1gxwxi8kos9y"
_CE_REGION_DEFAULT       = "us-east"


def _ce_url(name: str) -> str:
    """Build the CE public URL for a deployed MCP server."""
    project_hash = (
        os.getenv("CE_SUBDOMAIN")
        or os.getenv("CE_PROJECT_HASH")
        or _CE_PROJECT_HASH_DEFAULT
    )
    region = os.getenv("CE_REGION") or _CE_REGION_DEFAULT
    return f"https://cuga-apps-mcp-{name}.{project_hash}.{region}.codeengine.appdomain.cloud/mcp"


def _default_url(name: str, port: int) -> str:
    """Pick the right MCP URL for the current runtime context.

    Precedence (only consulted when MCP_<NAME>_URL is not set; that env
    var is checked in _resolved_urls and always wins):

      1. Code Engine        → public CE URL of the corresponding cuga-apps-mcp-* app
      2. Docker compose     → service DNS http://mcp-<name>:<port>/mcp
      3. Bare host          → http://localhost:<port>/mcp

    Order matters: a Dockerfile-baked CUGA_IN_DOCKER=1 plus CE-injected
    CE_APP both end up true on Code Engine, but we want CE URLs there,
    not compose DNS that doesn't exist on CE.
    """
    if _ON_CE:
        return _ce_url(name)
    if _IN_DOCKER:
        return f"http://mcp-{name}:{port}/mcp"
    return f"http://localhost:{port}/mcp"


def _resolved_urls(names: List[str]) -> dict[str, str]:
    out = {}
    for name in names:
        if name not in MCP_PORTS:
            raise ValueError(f"Unknown MCP server name: {name}. Known: {list(MCP_PORTS)}")
        env_key = f"MCP_{name.upper()}_URL"
        out[name] = os.getenv(env_key) or _default_url(name, MCP_PORTS[name])
    return out


def _unwrap_mcp_tool_result(raw):
    """langchain-mcp-adapters wraps every MCP tool with
    `response_format="content_and_artifact"`, so awaiting the tool's
    coroutine directly returns a (content_list, artifact) tuple. cuga's
    code-execution agent expects a normal value (e.g. dict / list / str)
    and crashes on `result.get("...")` against a tuple. We unwrap here:

      1. Prefer the artifact's structured_content (already a parsed dict).
      2. Fall back to the first text content entry, JSON-decoded if possible.
      3. If we end up with a cuga `{ok, data, error?}` envelope, return just
         `data` on success or a clear "ERROR: ..." string on failure — that
         matches what _mcp_bridge.call_tool already does for non-LLM callers,
         so the same tool docstring describes the same shape regardless of
         which code path invoked it.

    The original cuga StructuredTool path (.invoke/.ainvoke) is unaffected
    because LangChain itself unpacks the tuple into a ToolMessage for that
    code path; this wrapper only matters when cuga's executor `await`s the
    underlying coroutine directly.
    """
    import json as _json

    if not (isinstance(raw, tuple) and len(raw) == 2):
        return raw

    content_list, artifact = raw
    parsed = None

    # 1. Prefer structured_content (already structured per MCP 1.x).
    if isinstance(artifact, dict) and "structured_content" in artifact:
        sc = artifact["structured_content"]
        if isinstance(sc, dict) and "result" in sc:
            r = sc["result"]
            if isinstance(r, str):
                try:
                    parsed = _json.loads(r)
                except _json.JSONDecodeError:
                    pass
            elif isinstance(r, (dict, list)):
                parsed = r

    # 2. Fall back to text content.
    if parsed is None and isinstance(content_list, list) and content_list:
        first = content_list[0]
        if isinstance(first, dict) and "text" in first:
            txt = first["text"]
            try:
                parsed = _json.loads(txt)
            except _json.JSONDecodeError:
                return txt

    # 3. cuga {ok, data, error?, code?} envelope → return just data.
    if isinstance(parsed, dict) and "ok" in parsed:
        if not parsed["ok"]:
            err = parsed.get("error", "tool error")
            code = parsed.get("code", "")
            return f"ERROR: {err}" + (f" (code={code})" if code else "")
        return parsed.get("data", parsed)

    return parsed if parsed is not None else raw


class _ArgsSchemaShim(dict):
    """Make a JSON-Schema dict (what langchain-mcp-adapters now sets on
    StructuredTool.args_schema) quack like a Pydantic model class.

    cuga 0.2.x calls `tool.args_schema.schema()` and `.model_json_schema()`
    when building the system prompt and tracking tool calls. With the
    current adapter, args_schema is just a plain dict and those calls
    raise AttributeError. Without a fallback, cuga ships an empty/broken
    schema to the LLM and the agent has to discover tool shapes by trial
    and error — that's the wiki_dive symptom.

    We subclass `dict` so any code that treats args_schema as a mapping
    still works, and add the two Pydantic-style methods returning the
    underlying schema.
    """

    def schema(self) -> dict:           # Pydantic v1 method
        return dict(self)

    def model_json_schema(self) -> dict:  # Pydantic v2 method
        return dict(self)

    # Also expose model_fields for any code path that uses it for arg names.
    @property
    def model_fields(self) -> dict:
        return self.get("properties", {}) or {}


# Generic note appended to every MCP tool's description so cuga's code-
# execution agent stops assuming the return is a list (e.g. result[:3]).
# All cuga MCP tools wrap their data in tool_result(data) which becomes
# {"ok": true, "data": <data>}; our _unwrap_mcp_tool_result returns just
# `data`. The agent needs to know the shape is whatever `data` is — a
# dict for multi-field results, a list only when the tool explicitly
# returns a list. The wikipedia tools all return dicts, e.g.
# {"results": [...]}. Without this hint the agent burns turns on
# "treat result as list → KeyError → try .get → AttributeError → finally
# inspect with .keys()" before recovering.
_RETURN_SHAPE_HINT = (
    "\n\nReturn shape: this tool always returns the parsed `data` object "
    "from the cuga tool_result envelope. Use Python dict access on the "
    "documented field names (e.g. `result['results']`, `result['extract']`). "
    "Do NOT slice with `result[:N]` or index numerically — the top-level "
    "value is a dict, list, or scalar, never a tuple."
)


def _wrap_tool_for_cuga(tool):
    """Patch a StructuredTool so it works with cuga's executor + prompt builder:

      1. Wrap the async coroutine so direct `await tool(...)` returns a
         plain dict (cuga's code-execution agent crashes on the
         (content, artifact) tuple langchain-mcp-adapters returns).
      2. Wrap the JSON-Schema dict with `_ArgsSchemaShim` so cuga's
         prompt utilities can call `.schema()` / `.model_json_schema()`
         without AttributeError.
      3. Append a return-shape hint to the description so the agent
         doesn't waste turns guessing dict vs list.
    """
    import functools as _ft

    # ── 1. Tuple unwrap on the async path ──────────────────────────────
    original = getattr(tool, "coroutine", None)
    if original is not None:
        @_ft.wraps(original)
        async def _wrapped(*args, **kwargs):
            raw = await original(*args, **kwargs)
            return _unwrap_mcp_tool_result(raw)

        tool.coroutine = _wrapped

    # ── 2. Pydantic-style methods on args_schema ───────────────────────
    schema = getattr(tool, "args_schema", None)
    if isinstance(schema, dict) and not isinstance(schema, _ArgsSchemaShim):
        try:
            tool.args_schema = _ArgsSchemaShim(schema)
        except Exception:
            # Pydantic StructuredTool may forbid setattr — fail soft;
            # the tuple unwrap is the load-bearing fix.
            pass

    # ── 3. Return-shape hint in description ────────────────────────────
    desc = getattr(tool, "description", None)
    if isinstance(desc, str) and _RETURN_SHAPE_HINT not in desc:
        try:
            tool.description = desc + _RETURN_SHAPE_HINT
        except Exception:
            pass

    return tool


def load_tools(servers: List[str]) -> list:
    """Connect to one or more MCP servers and return their tools as LangChain
    StructuredTool instances ready to pass to `CugaAgent(tools=…)`.

    Tools are wrapped via `_wrap_tool_for_cuga` so the (content, artifact)
    tuple from langchain-mcp-adapters is unwrapped before cuga's executor
    sees it — see _unwrap_mcp_tool_result for details.

    Blocks until the server handshakes (or errors out). Safe to call at
    application startup before uvicorn is running.

    Args:
        servers: List of MCP server names from MCP_PORTS keys
                 (web | knowledge | geo | finance | code | local).
    """
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:
        raise ImportError(
            "langchain-mcp-adapters not installed — `pip install langchain-mcp-adapters`."
        ) from exc

    urls = _resolved_urls(servers)
    connections = {
        name: {"transport": "streamable_http", "url": url}
        for name, url in urls.items()
    }
    log.info("Connecting to MCP servers: %s", ", ".join(f"{n}={u}" for n, u in urls.items()))

    client = MultiServerMCPClient(connections)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None or not loop.is_running():
        tools = asyncio.run(client.get_tools())
    else:
        # Unlikely in practice (make_agent is called before uvicorn starts), but
        # handle it: run in a dedicated thread with its own event loop.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(lambda: asyncio.run(client.get_tools()))
            tools = fut.result()

    return [_wrap_tool_for_cuga(t) for t in tools]


def call_tool(server: str, tool: str, args: dict | None = None, timeout: float = 180.0):
    """Synchronously call an MCP tool from a non-LLM code path.

    Use this when application code (a scheduler, file watcher, webhook
    handler, ...) needs the result of an MCP tool without going through the
    LLM. Returns the parsed `data` field of the tool's tool_result envelope,
    or raises RuntimeError if the tool returned an error.

    Args:
        server: One of MCP_PORTS keys.
        tool:   Tool name as exposed by the server.
        args:   Tool arguments (default empty dict).
        timeout: Wall-clock timeout in seconds (default 180).
    """
    if server not in MCP_PORTS:
        raise ValueError(f"Unknown MCP server name: {server}. Known: {list(MCP_PORTS)}")
    url = os.getenv(f"MCP_{server.upper()}_URL") or _default_url(server, MCP_PORTS[server])

    async def _go():
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client(url) as (read, write, _close):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, args or {})
                if result.isError:
                    raise RuntimeError(f"{server}.{tool} returned an error result")
                # Concatenate text blocks (most tools return a single text block).
                text = "".join(getattr(b, "text", "") for b in (result.content or []))
                if not text:
                    return None
                import json as _json
                try:
                    payload = _json.loads(text)
                except _json.JSONDecodeError:
                    return text
                if isinstance(payload, dict) and "ok" in payload:
                    if not payload["ok"]:
                        raise RuntimeError(
                            f"{server}.{tool}: {payload.get('error', 'unknown error')}"
                        )
                    return payload.get("data")
                return payload

    coro = asyncio.wait_for(_go(), timeout=timeout)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None or not loop.is_running():
        return asyncio.run(coro)

    # Caller is inside an event loop already — run on a worker thread.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(lambda: asyncio.run(coro))
        return fut.result()
