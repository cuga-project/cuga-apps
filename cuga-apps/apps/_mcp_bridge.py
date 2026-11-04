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

Remote servers (REMOTE_MCP below) are third-party MCP servers we don't run,
such as Tavily's. They resolve to their public URL (overridable with
MCP_<NAME>_URL) and send `Authorization: Bearer $<TOKEN_ENV>`. Their calls are
counted twice in the usage collector: as MCP tool calls (server/tool) and as
provider API calls under the server's name, since each one spends that
provider's credits directly (local servers count their own provider calls).
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
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

# CUGA_TARGET=local forces localhost (skip the cloud fallback below) for users
# running the full local MCP stack who don't want a startup probe.
_FORCE_LOCAL = (os.getenv("CUGA_TARGET", "") or "").lower() == "local"

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


def _local_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.25) -> bool:
    """True if something is listening on host:port (a local MCP server is up)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _default_url(name: str, port: int) -> str:
    """Pick the right MCP URL for the current runtime context.

    Precedence (only consulted when MCP_<NAME>_URL is not set; that env
    var is checked in _resolved_urls and always wins):

      1. Code Engine        → public CE URL of the corresponding cuga-apps-mcp-* app
      2. Docker compose     → service DNS http://mcp-<name>:<port>/mcp
      3. Bare host, local server listening → http://localhost:<port>/mcp
      4. Bare host, no local server        → CE cloud URL (zero-config fallback)

    The bare-host cloud fallback means apps "just work" without booting the
    local MCP stack. Force one side explicitly with CUGA_TARGET=local
    (always localhost) or CUGA_TARGET=ce (always cloud), or set MCP_<NAME>_URL.

    Order matters: a Dockerfile-baked CUGA_IN_DOCKER=1 plus CE-injected
    CE_APP both end up true on Code Engine, but we want CE URLs there,
    not compose DNS that doesn't exist on CE.
    """
    if _ON_CE:
        return _ce_url(name)
    if _IN_DOCKER:
        return f"http://mcp-{name}:{port}/mcp"
    if _FORCE_LOCAL or _local_port_open(port):
        return f"http://localhost:{port}/mcp"
    log.info("No local MCP server on :%d for %r — falling back to cloud (CE).", port, name)
    return _ce_url(name)


# Third-party MCP servers, reached over HTTPS with a bearer token. Not in
# MCP_PORTS because we don't run them (nothing to launch, bundle or port-map).
REMOTE_MCP: dict[str, dict[str, str]] = {
    "tavily": {"url": "https://mcp.tavily.com/mcp/", "token_env": "TAVILY_API_KEY"},
}


def remote_mcp_configured(name: str) -> bool:
    """True if the remote server's token env var is set (the server will accept us)."""
    spec = REMOTE_MCP.get(name)
    return bool(spec and os.getenv(spec["token_env"]))


def _server_headers(name: str) -> dict[str, str]:
    spec = REMOTE_MCP.get(name)
    token = os.getenv(spec["token_env"]) if spec else None
    return {"Authorization": f"Bearer {token}"} if token else {}


def server_endpoint(name: str) -> tuple[str, dict[str, str]]:
    """(url, headers) for one server — for app code that opens its own MCP
    session (e.g. to read resource blocks, which call_tool drops)."""
    return _resolved_urls([name])[name], _server_headers(name)


def _resolved_urls(names: List[str]) -> dict[str, str]:
    out = {}
    for name in names:
        env_key = f"MCP_{name.upper()}_URL"
        if name in REMOTE_MCP:
            out[name] = os.getenv(env_key) or REMOTE_MCP[name]["url"]
            continue
        if name not in MCP_PORTS:
            raise ValueError(
                f"Unknown MCP server name: {name}. Known: {list(MCP_PORTS) + list(REMOTE_MCP)}"
            )
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
    # cuga >= 0.3 reads `field.annotation` (Pydantic FieldInfo), so map each
    # JSON-Schema property to an object carrying the equivalent Python type.
    @property
    def model_fields(self) -> dict:
        from types import SimpleNamespace
        props = self.get("properties", {}) or {}
        return {
            name: SimpleNamespace(annotation=_JSON_TO_PY.get((spec or {}).get("type")))
            for name, spec in props.items()
        }


_JSON_TO_PY = {
    "string": str, "integer": int, "number": float,
    "boolean": bool, "array": list, "object": dict,
}


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


def _track_mcp(server: str | None, tool_name: str, ok: bool, code: str | None = None) -> None:
    """Best-effort: count this MCP tool invocation in the usage collector.

    Never raises and never affects the tool call — usage tracking is optional
    infrastructure. No-op if _usage isn't importable or no server is known.
    """
    if not server:
        return
    try:
        from _usage import track_mcp
        track_mcp(server, tool_name, ok=ok, code=code)
        if server in REMOTE_MCP:
            # A hosted server spends the provider's credits directly; count it on
            # the dashboard's API-calls tab too, next to mcp-web's own calls.
            from _usage import track_call
            track_call(server, ok=ok, code=code)
    except Exception:  # noqa: BLE001 — tracking must never break a tool call
        pass


def _wrap_tool_for_cuga(tool, server: str | None = None):
    """Patch a StructuredTool so it works with cuga's executor + prompt builder:

      1. Wrap the async coroutine so direct `await tool(...)` returns a
         plain dict (cuga's code-execution agent crashes on the
         (content, artifact) tuple langchain-mcp-adapters returns).
      2. Wrap the JSON-Schema dict with `_ArgsSchemaShim` so cuga's
         prompt utilities can call `.schema()` / `.model_json_schema()`
         without AttributeError.
      3. Append a return-shape hint to the description so the agent
         doesn't waste turns guessing dict vs list.

    `server` is the MCP server name this tool came from (web, geo, …); when
    present, every invocation is counted in the usage collector so the
    dashboard can break usage down per server and per tool.
    """
    import functools as _ft

    tool_name = getattr(tool, "name", "tool")

    # ── 1. Tuple unwrap on the async path (+ usage tracking) ───────────
    original = getattr(tool, "coroutine", None)
    if original is not None:
        @_ft.wraps(original)
        async def _wrapped(*args, **kwargs):
            try:
                raw = await original(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                try:
                    from _usage import classify_error
                    _track_mcp(server, tool_name, ok=False, code=classify_error(exc))
                except Exception:  # noqa: BLE001
                    _track_mcp(server, tool_name, ok=False, code="error")
                raise
            result = _unwrap_mcp_tool_result(raw)
            # cuga error envelopes surface as an "ERROR: …" string (see
            # _unwrap_mcp_tool_result); treat those as failed calls.
            ok = not (isinstance(result, str) and result.startswith("ERROR:"))
            _track_mcp(server, tool_name, ok=ok, code=None if ok else "tool_error")
            return result

        tool.coroutine = _wrapped
        # _wrapped returns the unwrapped value, not a (content, artifact)
        # tuple — tell LangChain so the .ainvoke path (used by cuga >= 0.3)
        # doesn't reject it.
        try:
            tool.response_format = "content"
        except Exception:
            pass

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
    # Only our own servers use the tool_result envelope; remote servers
    # (Tavily, GitHub) return their own text/JSON, so the hint would mislead.
    desc = getattr(tool, "description", None)
    if server not in REMOTE_MCP and isinstance(desc, str) and _RETURN_SHAPE_HINT not in desc:
        try:
            tool.description = desc + _RETURN_SHAPE_HINT
        except Exception:
            pass

    # Stash the origin server so callers can attribute tool calls later if needed.
    if server:
        try:
            tool._mcp_server = server     # noqa: SLF001 — cooperative annotation
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
                 (web | knowledge | geo | finance | code | local) or
                 REMOTE_MCP keys (tavily).
    """
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:
        raise ImportError(
            "langchain-mcp-adapters not installed — `pip install langchain-mcp-adapters`."
        ) from exc

    urls = _resolved_urls(servers)
    connections = {}
    for name, url in urls.items():
        conn = {"transport": "streamable_http", "url": url}
        headers = _server_headers(name)
        if headers:
            conn["headers"] = headers
        connections[name] = conn
    log.info("Connecting to MCP servers: %s", ", ".join(f"{n}={u}" for n, u in urls.items()))

    client = MultiServerMCPClient(connections)

    async def _get_tagged_tools() -> list:
        """Fetch tools server-by-server so each carries its origin server name
        (for per-server/per-tool usage tracking). Falls back to one flat
        get_tools() if per-server loading isn't supported by the adapter."""
        out: list = []
        try:
            for name in urls:
                server_tools = await client.get_tools(server_name=name)
                out.extend(_wrap_tool_for_cuga(t, server=name) for t in server_tools)
            return out
        except TypeError:
            # Older adapter without server_name kwarg — load all, untagged.
            return [_wrap_tool_for_cuga(t) for t in await client.get_tools()]

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None or not loop.is_running():
        return asyncio.run(_get_tagged_tools())
    # Unlikely in practice (make_agent is called before uvicorn starts), but
    # handle it: run in a dedicated thread with its own event loop.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(lambda: asyncio.run(_get_tagged_tools()))
        return fut.result()


def call_tool(server: str, tool: str, args: dict | None = None, timeout: float = 180.0):
    """Synchronously call an MCP tool from a non-LLM code path.

    Use this when application code (a scheduler, file watcher, webhook
    handler, ...) needs the result of an MCP tool without going through the
    LLM. Returns the parsed `data` field of the tool's tool_result envelope,
    or raises RuntimeError if the tool returned an error.

    Args:
        server: One of MCP_PORTS or REMOTE_MCP keys.
        tool:   Tool name as exposed by the server.
        args:   Tool arguments (default empty dict).
        timeout: Wall-clock timeout in seconds (default 180).
    """
    url = _resolved_urls([server])[server]
    headers = _server_headers(server)

    async def _go():
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client(url, headers=headers or None) as (read, write, _close):
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

    def _run() -> object:
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

    try:
        out = _run()
    except Exception as exc:  # noqa: BLE001
        try:
            from _usage import classify_error
            _track_mcp(server, tool, ok=False, code=classify_error(exc))
        except Exception:  # noqa: BLE001
            _track_mcp(server, tool, ok=False, code="error")
        raise
    _track_mcp(server, tool, ok=True)
    return out
