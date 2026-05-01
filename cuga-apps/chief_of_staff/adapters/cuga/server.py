"""Cuga adapter — wraps an in-process CugaAgent and exposes /chat over HTTP.

This is the only place that imports cuga.sdk. Chief of Staff's orchestrator
talks to this service over HTTP, which is what makes the planner backend
swappable: a different adapter (gpt-oss, custom, etc.) implements the same
endpoints and chief_of_staff doesn't change.

Reuses apps/_mcp_bridge.load_tools and apps/_llm.create_llm — read-only
consumption, no edits to those files.

Phase 3: /agent/reload now accepts an `extra_tools` list — dynamically
generated tools (e.g. from the OpenAPI source) that are merged into the
MCP-loaded set. These are httpx-backed StructuredTools built on the fly.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Make apps/ importable so we can reuse _mcp_bridge and _llm without copying.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parent.parent.parent.parent  # chief_of_staff/adapters/cuga/server.py → cuga-apps/
_APPS_DIR = _REPO_ROOT / "apps"
for p in (str(_APPS_DIR), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

log = logging.getLogger("cuga-adapter")

# Default subset chosen so the demo has real gaps to fill via acquisition.
_DEFAULT_SERVERS = "web,local,code"

_GAP_MARKER = "[[TOOL_GAP]]"
_GAP_RE = re.compile(rf"{re.escape(_GAP_MARKER)}\s*(\{{.*?\}})", re.DOTALL)

SYSTEM_INSTRUCTIONS = f"""\
You are a Chief of Staff agent. You have access to a configurable set of tools
loaded from MCP servers (web search, knowledge, geo, finance, code, local file
ops, text processing, invocable APIs) plus dynamically-acquired tools generated
from public APIs. Pick the tools that fit the user's question; ignore the rest.

If you don't have a tool that fits the user's need, end your reply with this
exact marker on its own line, followed by a single-line JSON object describing
the gap:

{_GAP_MARKER}
{{"capability": "<short phrase>", "inputs": ["<input>", ...], "expected_output": "<what the user wanted>"}}

The capability phrase should be 2-5 words (e.g. "weather lookup", "wikipedia
search", "geocoding"). The Toolsmith agent will then attempt to acquire a
matching tool.

Important rule about gap-emission:
- If the user names a specific service, API, or website by name (e.g.
  "chucknorris.io", "OpenWeather", "REST Countries", "Hacker News",
  "icanhazdadjoke", "PokeAPI") and you do not have a tool whose name or
  description directly references that service, you MUST emit the gap
  marker rather than fall back to web_search.
- For definitional or factual queries (e.g. "What is X?", "Who is X?",
  "What is the capital of X?"), use web_search if available — DO NOT
  emit a gap. These are exactly what web_search is for.
"""


def _parse_gap(answer: str) -> tuple[str, dict | None]:
    m = _GAP_RE.search(answer)
    if not m:
        return answer, None
    try:
        gap = json.loads(m.group(1))
    except json.JSONDecodeError:
        log.warning("Failed to parse gap JSON: %s", m.group(1))
        return answer, None
    cleaned = answer[: m.start()].rstrip()
    return cleaned, gap


class _State:
    agent = None
    tools: list = []
    servers_loaded: list[str] = []
    extra_tools_spec: list[dict] = []   # dicts as received in /agent/reload
    # Per-tool secrets pushed by the backend on /agent/reload. Lives in
    # adapter process memory only; not persisted, not logged.
    secrets: dict[str, dict[str, str]] = {}
    # Tool names the orchestrator wants masked from cuga (so the user can
    # force a gap by removing e.g. web_search from this turn's toolset).
    disabled_tools: list[str] = []
    # Extras whose code couldn't be loaded (bad imports, schema mismatch,
    # etc.). We keep these around so /health can surface them — without
    # this they fail silently and look like "tool was never registered".
    failed_extras: list[dict] = []
    lock: asyncio.Lock = asyncio.Lock()


# Per-chat-call sink for tool names that actually got invoked during the
# turn. Set in /chat, appended to by the tool-invocation wrapper, read out
# at the end of the turn for the response.
_tools_used: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "cos_tools_used", default=None
)


def _wrap_tool_for_tracking(tool: Any) -> Any:
    """Patch the tool's invoke entry-points so each call records the tool
    name into the per-turn ContextVar. Re-entrant safe — if the
    ContextVar isn't set (e.g. tool called outside /chat), we skip the
    record cleanly.

    We wrap multiple slots because cuga doesn't go through LangChain's
    ainvoke path. Its code-exec sandbox binds tools by reading
    `tool.coroutine` (preferred) or `tool.func`, then calls them
    directly inside the LLM-generated Python (`await web_search(...)`).
    Patching `_arun` alone would never fire."""
    if getattr(tool, "_cos_tracked", False):
        return tool
    name = getattr(tool, "name", "unknown")

    def _record() -> None:
        sink = _tools_used.get()
        if sink is not None:
            sink.append(name)

    coroutine = getattr(tool, "coroutine", None)
    if callable(coroutine):
        async def _tracked_coroutine(*args, **kwargs):
            _record()
            return await coroutine(*args, **kwargs)
        tool.coroutine = _tracked_coroutine  # type: ignore[attr-defined]

    func = getattr(tool, "func", None)
    if callable(func) and func is not coroutine:
        # `func` may be sync or async depending on the tool; preserve the
        # original async-ness by sniffing.
        import inspect
        if inspect.iscoroutinefunction(func):
            async def _tracked_func(*args, **kwargs):
                _record()
                return await func(*args, **kwargs)
        else:
            def _tracked_func(*args, **kwargs):
                _record()
                return func(*args, **kwargs)
        tool.func = _tracked_func  # type: ignore[attr-defined]

    # _arun is the LangChain-native path for any tools cuga happens to
    # call through ainvoke — wrap it too so we don't miss those.
    arun = getattr(tool, "_arun", None)
    if callable(arun):
        async def _tracked_arun(*args, **kwargs):
            _record()
            return await arun(*args, **kwargs)
        tool._arun = _tracked_arun  # type: ignore[method-assign]

    tool._cos_tracked = True  # type: ignore[attr-defined]
    return tool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _initialize_with_servers()
    try:
        yield
    finally:
        await _aclose_agent()


async def _aclose_agent() -> None:
    if _State.agent is not None:
        try:
            await _State.agent.aclose()
        except Exception:  # noqa: BLE001
            log.exception("aclose failed")
        finally:
            _State.agent = None
            _State.tools = []
            _State.servers_loaded = []


# ---------------------------------------------------------------------------
# Dynamic tool generation — phase 3.6
#
# Two paths, picked by which keys the spec dict has:
#
# A) "code" present  → Coder-generated artifact. We exec() the source against
#    a restricted globals dict (import allowlist), pull out the entry-point
#    function, and wrap it. Auth secrets declared in `requires_secrets` are
#    resolved from the vault and injected as keyword arguments at call time;
#    cuga's args_schema sees only the user-facing parameters.
#
# B) "code" missing  → fallback parameter-substitution closure (phase 3 v1
#    behavior), used by catalog mounts and any spec that didn't go through
#    the Coder. Calls invoke_url with httpx using kwargs as query/body.
# ---------------------------------------------------------------------------

import ast

_ALLOWED_TOP_IMPORTS = {
    "httpx", "json", "re", "datetime", "urllib", "asyncio", "typing",
    "math", "base64", "hashlib", "hmac", "uuid", "time",
    # Allow pydantic + langchain types since the Coder occasionally emits
    # type hints from these. They're already in the env.
    "pydantic", "typing_extensions",
}


class _CodeSecurityError(RuntimeError):
    pass


def _exec_artifact_code(code: str, function_name: str):
    """Compile + exec generated tool code with a restricted-import gate.

    Returns the entry-point coroutine function. Raises _CodeSecurityError
    if the AST contains a disallowed import.
    """
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                top = n.name.split(".")[0]
                if top not in _ALLOWED_TOP_IMPORTS:
                    raise _CodeSecurityError(f"disallowed import: {n.name!r}")
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top and top not in _ALLOWED_TOP_IMPORTS:
                raise _CodeSecurityError(f"disallowed import: from {node.module!r}")

    namespace: dict = {"__builtins__": __builtins__}
    exec(compile(tree, f"<tool:{function_name}>", "exec"), namespace)  # noqa: S102
    func = namespace.get(function_name)
    if func is None:
        raise ValueError(
            f"function {function_name!r} not defined in artifact code; "
            f"defined names: {sorted(k for k in namespace if not k.startswith('__'))}"
        )
    return func


# Vault accessor — defaults to looking up _State.secrets, but tests can
# override via set_secret_lookup().
def _default_secret_lookup(artifact_id: str, key: str):
    return (_State.secrets.get(artifact_id) or {}).get(key)


_secret_lookup = _default_secret_lookup
# Optional: a function that updates a secret in the upstream vault. Phase
# 3.7's OAuth2 refresh uses this to persist a freshly-minted access token
# back into the toolsmith vault. Set by main; tests can override.
_secret_writer = None


def set_secret_lookup(fn):
    global _secret_lookup
    _secret_lookup = fn


def set_secret_writer(fn):
    global _secret_writer
    _secret_writer = fn


# Per-tool auth metadata, indexed by artifact id. Populated from /agent/reload
# alongside extra_tools_spec; used by the OAuth2 refresh path.
_auth_meta: dict = {}


async def _refresh_oauth2_token(artifact_id: str, auth_meta: dict) -> str | None:
    """Use the stored refresh token + client creds to mint a new access token.
    Persists the new token (and any new refresh_token) back to the vault.
    Returns the new access token or None on failure.
    """
    refresh_key = auth_meta.get("refresh_secret_key")
    token_url = auth_meta.get("token_url")
    client_id_key = auth_meta.get("client_id_key")
    client_secret_key = auth_meta.get("client_secret_key")
    if not (refresh_key and token_url and client_id_key and client_secret_key):
        log.info("OAuth2 refresh skipped — auth_meta is incomplete for %r", artifact_id)
        return None

    refresh_token = _secret_lookup(artifact_id, refresh_key)
    client_id = _secret_lookup(artifact_id, client_id_key)
    client_secret = _secret_lookup(artifact_id, client_secret_key)
    if not (refresh_token and client_id and client_secret):
        return None

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(token_url, data=payload)
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("OAuth2 refresh failed for %r: %s", artifact_id, exc)
        return None

    new_access = data.get("access_token")
    if not new_access:
        log.warning("OAuth2 refresh response missing access_token for %r", artifact_id)
        return None

    # Persist to in-memory state.
    secret_key = auth_meta.get("secret_key")
    if secret_key:
        _State.secrets.setdefault(artifact_id, {})[secret_key] = new_access
    new_refresh = data.get("refresh_token")
    if new_refresh:
        _State.secrets.setdefault(artifact_id, {})[refresh_key] = new_refresh

    # Best-effort: persist back to the upstream vault so other adapter
    # restarts / probes see the refreshed token.
    if _secret_writer is not None:
        try:
            await _secret_writer(artifact_id, secret_key, new_access)
            if new_refresh:
                await _secret_writer(artifact_id, refresh_key, new_refresh)
        except Exception:  # noqa: BLE001
            log.exception("Persist refreshed OAuth2 token to vault failed")

    log.info("OAuth2 refresh succeeded for %r", artifact_id)
    return new_access


def _build_extra_tool(spec: dict):
    """Build a LangChain StructuredTool from a spec.

    spec keys:
      kind                 "code" | "browser_task" (default "code")
      tool_name, description, invoke_params (cuga-visible param schema)
      requires_secrets     hidden from cuga, injected at call time
      code, entry_point_function    (kind=code: phase 3.6+ exec path)
      invoke_url, invoke_method     (legacy fallback: param-substitution closure)
      steps                (kind=browser_task: phase 4 DSL list)
    """
    from langchain_core.tools import StructuredTool  # type: ignore[import-not-found]
    from pydantic import create_model  # type: ignore[import-not-found]

    name = spec["tool_name"]
    description = spec.get("description") or name
    params_schema = spec.get("invoke_params") or {}
    requires_secrets = list(spec.get("requires_secrets") or [])
    artifact_id = spec.get("id") or name
    kind = spec.get("kind") or "code"

    # Build a pydantic args_schema EXCLUDING the secret kwargs — cuga must
    # not see them or try to ask the user for them.
    type_map = {"string": str, "number": float, "integer": int, "boolean": bool}

    # Some upstream sources hand us flattened schemas where the param
    # value is a bare type string (e.g. {"city": "string"}) instead of
    # the JSON-Schema {"city": {"type": "string", ...}} shape. Coerce so
    # downstream .get() calls don't blow up — without this fix, two of
    # three extra-tool builds (OpenMeteo*) fail silently and cuga ends
    # up looking like it's missing tools the toolbox actually has.
    def _normalize_param(info):
        if isinstance(info, dict):
            return info
        if isinstance(info, str):
            return {"type": info}
        return {}

    fields = {}
    for pname, pinfo in params_schema.items():
        if pname in requires_secrets:
            continue
        info = _normalize_param(pinfo)
        ptype = type_map.get(info.get("type", "string"), str)
        default = info.get("default")
        required = info.get("required", default is None)
        if required and default is None:
            fields[pname] = (ptype, ...)
        else:
            fields[pname] = (ptype, default)
    Args = create_model(f"{name}_args", **fields) if fields else create_model(f"{name}_args")

    # Phase 4 — browser_task path. Cuga calls this; we forward to the
    # browser-runner over HTTP. No exec, no secret injection here (the
    # browser-runner handles secret substitution into the DSL).
    if kind == "browser_task":
        steps = spec.get("steps") or []

        async def _browser_invoke(**kwargs):
            secrets = {}
            for key in requires_secrets:
                val = _secret_lookup(artifact_id, key)
                if val is None:
                    raise RuntimeError(f"missing secret {key!r} for browser tool {artifact_id!r}")
                secrets[key] = val
            url = os.environ.get("BROWSER_RUNNER_URL", "http://chief-of-staff-browser:8002")
            async with httpx.AsyncClient(timeout=300.0) as client:
                r = await client.post(f"{url.rstrip('/')}/execute", json={
                    "steps": steps, "inputs": dict(kwargs), "secrets": secrets,
                    "allow_user_confirm": True,
                })
                r.raise_for_status()
                return r.json()

        return StructuredTool.from_function(
            coroutine=_browser_invoke, name=name, description=description, args_schema=Args,
        )

    # Path A: real exec of artifact code.
    code = spec.get("code")
    entry_point = spec.get("entry_point_function") or name
    if code:
        try:
            func = _exec_artifact_code(code, entry_point)
        except (_CodeSecurityError, SyntaxError, ValueError) as exc:
            log.error("Artifact %r rejected: %s", artifact_id, exc)
            return _build_error_stub_tool(name, description, str(exc), Args, StructuredTool)

        async def _invoke(**kwargs):
            return await _invoke_with_oauth2_retry(
                artifact_id=artifact_id, func=func,
                requires_secrets=requires_secrets, kwargs=kwargs,
            )

        return StructuredTool.from_function(
            coroutine=_invoke, name=name, description=description, args_schema=Args,
        )

    # Path B: fallback parameter-substitution closure.
    url = spec["invoke_url"]
    method = (spec.get("invoke_method") or "GET").upper()
    headers = spec.get("headers") or {}
    path_param_re = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
    path_params = path_param_re.findall(url)

    async def _fallback_invoke(**kwargs):
        u = url
        kw = dict(kwargs)
        for pp in path_params:
            if pp in kw:
                u = u.replace(f"{{{pp}}}", str(kw.pop(pp)))
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                r = await client.get(u, params=kw, headers=headers)
            else:
                r = await client.request(method, u, json=kw, headers=headers)
            r.raise_for_status()
            try:
                return r.json()
            except ValueError:
                return r.text

    return StructuredTool.from_function(
        coroutine=_fallback_invoke, name=name, description=description, args_schema=Args,
    )


async def _invoke_with_oauth2_retry(*, artifact_id, func, requires_secrets, kwargs):
    """Resolve secrets, call the tool. On HTTPStatusError 401, attempt one
    OAuth2 refresh and retry. All other exceptions propagate."""
    secrets = {}
    if requires_secrets:
        for key in requires_secrets:
            val = _secret_lookup(artifact_id, key)
            if val is None:
                raise RuntimeError(f"missing secret {key!r} for tool {artifact_id!r}")
            secrets[key] = val
    try:
        return await func(**kwargs, **secrets)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 401:
            raise
        meta = _auth_meta.get(artifact_id) or {}
        if (meta.get("type") or "").lower() != "oauth2_token":
            raise
        new_access = await _refresh_oauth2_token(artifact_id, meta)
        if not new_access:
            raise
        # Re-resolve secrets (the refreshed access token replaces the old).
        secrets = {key: _secret_lookup(artifact_id, key) for key in (requires_secrets or [])}
        return await func(**kwargs, **secrets)


def _build_error_stub_tool(name, description, reason, Args, StructuredTool):
    """Return a tool that always errors. Used when artifact code fails the
    import allowlist — we still register *something* so cuga can report
    the failure cleanly instead of crashing on unknown tool name."""
    async def _err(**_kw):
        raise RuntimeError(f"tool {name!r} disabled: {reason}")
    return StructuredTool.from_function(
        coroutine=_err, name=name,
        description=f"{description} [disabled: {reason}]",
        args_schema=Args,
    )


async def _initialize_with_servers(
    servers: list[str] | None = None,
    extra_tools_spec: list[dict] | None = None,
    secrets: dict[str, dict[str, str]] | None = None,
    disabled_tools: list[str] | None = None,
) -> None:
    """(Re-)build the CugaAgent for the given MCP server set + extra tools."""
    from _mcp_bridge import load_tools  # noqa: WPS433
    from cuga.sdk import CugaAgent  # noqa: WPS433
    from .llm_factory import create_llm_for_adapter  # noqa: WPS433

    if servers is None:
        servers = [
            s.strip()
            for s in os.environ.get("MCP_SERVERS", _DEFAULT_SERVERS).split(",")
            if s.strip()
        ]
    if extra_tools_spec is None:
        extra_tools_spec = list(_State.extra_tools_spec)
    if secrets is None:
        secrets = dict(_State.secrets)
    if disabled_tools is None:
        disabled_tools = list(_State.disabled_tools)
    disabled_set = {n for n in (disabled_tools or []) if n}

    log.info(
        "Loading MCP tool sets: %s + %d extra tools (disabled=%s)",
        servers, len(extra_tools_spec), sorted(disabled_set) or "none",
    )

    async with _State.lock:
        await _aclose_agent()

        # Load each MCP server individually so we can tag each returned
        # tool with its origin server. The /tools endpoint surfaces this
        # so the UI can group tools by server. load_tools() handshakes
        # with the MCP server on each call (~few hundred ms per server,
        # acceptable for the small fixed set we have).
        tools: list = []
        for server_name in servers:
            try:
                server_tools = list(load_tools([server_name]))
            except Exception as exc:  # noqa: BLE001
                log.exception("MCP tool load failed for server=%s", server_name)
                raise RuntimeError(
                    f"Failed to load MCP tools from {server_name}: {exc}"
                ) from exc
            for t in server_tools:
                try:
                    setattr(t, "_cos_server", server_name)
                except Exception:  # noqa: BLE001
                    pass
            tools.extend(server_tools)

        # Merge phase-3 generated tools — provenance source is the artifact
        # spec, not an MCP server. We tag with "_cos_server=None" so the
        # /tools endpoint can render them under a 'generated' bucket.
        failed_extras: list[dict] = []
        for spec in extra_tools_spec:
            tool_name = spec.get("tool_name") or "<unnamed>"
            try:
                t = _build_extra_tool(spec)
                setattr(t, "_cos_server", None)
                tools.append(t)
            except Exception as exc:  # noqa: BLE001
                log.exception("Failed to build extra tool: %s", tool_name)
                failed_extras.append({
                    "tool_name": tool_name,
                    "artifact_id": spec.get("id"),
                    "error_class": type(exc).__name__,
                    "error": str(exc)[:240],
                })

        # Apply user-requested disable list. We drop the tool entirely so
        # cuga doesn't even see it in the schema — this is the mechanism
        # behind the UI toggle that lets the user force gaps.
        if disabled_set:
            before = len(tools)
            tools = [t for t in tools if getattr(t, "name", "") not in disabled_set]
            log.info("Filtered %d disabled tools (%d → %d)", before - len(tools), before, len(tools))

        # Wrap each surviving tool so per-turn invocations get recorded.
        tools = [_wrap_tool_for_tracking(t) for t in tools]

        if not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = "sk-placeholder-not-used"

        llm = create_llm_for_adapter()
        agent = CugaAgent(model=llm, tools=tools, special_instructions=SYSTEM_INSTRUCTIONS)
        await agent.initialize()

        # Phase 3.7 — index auth metadata by artifact id so the OAuth2
        # refresh path can find it from inside the tool wrapper.
        global _auth_meta
        _auth_meta = {
            (s.get("id") or s.get("tool_name")): s.get("auth")
            for s in extra_tools_spec
            if s.get("auth")
        }

        _State.agent = agent
        _State.tools = tools
        _State.servers_loaded = servers
        _State.extra_tools_spec = list(extra_tools_spec)
        _State.secrets = dict(secrets)
        _State.disabled_tools = sorted(disabled_set)
        _State.failed_extras = failed_extras
        log.info("Cuga adapter ready — %d total tools (%d MCP + %d generated, %d with secrets)",
                 len(tools), len(tools) - len(extra_tools_spec),
                 len(extra_tools_spec), len(secrets))


app = FastAPI(title="Cuga Adapter", version="0.3.0", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    error: str | None = None
    gap: dict | None = None
    # Per-call attribution: each entry is {name, server} where server is
    # the MCP server the tool came from, or None for generated/extra tools.
    tools_used: list[dict] = []


class ReloadRequest(BaseModel):
    servers: list[str]
    extra_tools: list[dict] = []
    secrets: dict[str, dict[str, str]] = {}
    disabled_tools: list[str] = []


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok" if _State.agent is not None else "initializing",
        "servers_loaded": _State.servers_loaded,
        "tool_count": len(_State.tools),
        "extra_tool_count": len(_State.extra_tools_spec),
        # Extras whose code couldn't be loaded (bad imports, bad schema,
        # etc.). Surfaced so the UI can flag them rather than have them
        # disappear silently.
        "failed_extras": list(_State.failed_extras),
    }


@app.get("/tools")
async def list_tools() -> list[dict]:
    extra_names = {s.get("tool_name") for s in _State.extra_tools_spec}
    return [
        {
            "name": getattr(t, "name", str(t)),
            "description": getattr(t, "description", "") or "",
            "kind": "generated" if getattr(t, "name", "") in extra_names else "mcp",
            "server": getattr(t, "_cos_server", None),
        }
        for t in _State.tools
    ]


@app.post("/agent/reload")
async def reload_agent(req: ReloadRequest) -> dict:
    try:
        await _initialize_with_servers(
            req.servers, req.extra_tools, req.secrets, req.disabled_tools,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "status": "ok",
        "servers_loaded": _State.servers_loaded,
        "tool_count": len(_State.tools),
        "extra_tool_count": len(_State.extra_tools_spec),
        "tools_with_secrets": len(_State.secrets),
        "disabled_tools": list(_State.disabled_tools),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if _State.agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    sink: list[str] = []
    token = _tools_used.set(sink)
    try:
        result = await _State.agent.invoke(req.message, thread_id=req.thread_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("agent.invoke failed")
        return ChatResponse(
            response="", thread_id=req.thread_id, error=str(exc),
            tools_used=_attribute_servers(list(dict.fromkeys(sink))),
        )
    finally:
        _tools_used.reset(token)

    answer = getattr(result, "answer", str(result))
    cleaned, gap = _parse_gap(answer)
    # De-duplicate while preserving call order (first invocation wins).
    tools_used = _attribute_servers(list(dict.fromkeys(sink)))
    return ChatResponse(
        response=cleaned,
        thread_id=req.thread_id,
        error=getattr(result, "error", None),
        gap=gap,
        tools_used=tools_used,
    )


def _attribute_servers(names: list[str]) -> list[dict]:
    """Map tool names to {name, server} pairs using the live tool list.
    Generated/extra tools have server=None — the chat UI renders that as
    'generated' rather than an MCP server."""
    server_by_name: dict[str, str | None] = {
        getattr(t, "name", ""): getattr(t, "_cos_server", None)
        for t in _State.tools
    }
    out = []
    for n in names:
        out.append({"name": n, "server": server_by_name.get(n)})
    return out
