"""Chief of Staff — FastAPI entrypoint."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from orchestrator import Orchestrator
from registry.discovery import sync_from_adapter, sync_with_retry
from registry.store import ToolRegistry

log = logging.getLogger(__name__)

_orchestrator: Orchestrator | None = None
_registry: ToolRegistry | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator, _registry
    _orchestrator = Orchestrator()
    _registry = ToolRegistry()

    adapter_url = os.environ.get("CUGA_URL", "http://localhost:8000")

    async def _bootstrap():
        # Pull artifact state from Toolsmith and reload cuga so prior tools
        # mount on cold start. Cuga will be unreachable for ~30s; retry quietly.
        for attempt in range(6):
            try:
                await _orchestrator.sync_planner_with_toolsmith()
                break
            except Exception as exc:  # noqa: BLE001
                log.info("startup sync attempt %d failed: %s", attempt + 1, exc)
                await asyncio.sleep(10)
        await sync_with_retry(_registry, adapter_url)

    asyncio.create_task(_bootstrap())
    try:
        yield
    finally:
        if _orchestrator:
            await _orchestrator.aclose()
        if _registry:
            _registry.close()


app = FastAPI(title="Chief of Staff", version="0.4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    error: str | None = None
    gap: dict | None = None
    acquisition: dict | None = None
    tools_used: list[dict] = []   # [{name, server}, …]


@app.get("/health")
async def health() -> dict:
    planner_ok = await _orchestrator.planner_health() if _orchestrator else False
    toolsmith_health = await _orchestrator.toolsmith_health() if _orchestrator else {}
    tool_count = len(_registry.all()) if _registry else 0
    failed_extras = []
    if _orchestrator:
        try:
            failed_extras = await _orchestrator.planner_failed_extras()
        except Exception:  # noqa: BLE001
            failed_extras = []
    return {
        "status": "ok",
        "planner_reachable": planner_ok,
        "toolsmith": toolsmith_health,
        "tools_registered": tool_count,
        # Adapter-level extras that didn't load (silent build failures).
        # Forwarded here so the UI can flag them.
        "failed_extras": failed_extras,
    }


@app.get("/tools")
async def tools() -> list[dict]:
    if not _registry:
        return []
    disabled = _orchestrator.disabled_tools if _orchestrator else set()
    baseline = _orchestrator.baseline_servers if _orchestrator else set()
    out = []
    for r in _registry.all():
        # acquired = mounted by Toolsmith at runtime, not present in the
        # cold-start MCP_SERVERS env. Generated tools are always acquired.
        if r.source == "generated":
            acquired = True
        elif r.source.startswith("mcp:"):
            server = r.source[len("mcp:"):]
            acquired = server not in baseline
        else:
            acquired = False
        out.append({
            "id": r.id,
            "name": r.name,
            "source": r.source,
            "description": r.description,
            "health": r.health,
            "disabled": r.name in disabled,
            "acquired": acquired,
        })
    return out


@app.post("/tools/refresh")
async def refresh_tools() -> dict:
    if not _registry:
        return {"synced": 0}
    adapter_url = os.environ.get("CUGA_URL", "http://localhost:8000")
    n = await sync_from_adapter(_registry, adapter_url)
    return {"synced": n}


class ToggleRequest(BaseModel):
    disabled: bool


@app.post("/tools/{name}/toggle")
async def toggle_tool(name: str, req: ToggleRequest) -> dict:
    """Mask or unmask a tool from the planner. Triggers a planner reload.

    The toggle is a temporary, in-memory-only signal — useful for forcing
    a gap (e.g. disable web_search and re-ask "tell me a Chuck Norris
    joke from chucknorris.io" to push cuga into Toolsmith)."""
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    disabled = await _orchestrator.set_tool_disabled(name, req.disabled)
    if _registry:
        adapter_url = os.environ.get("CUGA_URL", "http://localhost:8000")
        await sync_from_adapter(_registry, adapter_url)
    return {
        "name": name,
        "disabled": req.disabled,
        "all_disabled": sorted(disabled),
    }


@app.get("/toolsmith/artifacts")
async def list_artifacts() -> list[dict]:
    """Surface Toolsmith's persistent artifact list (the user's growing
    toolbox) so the dumb UI can render it."""
    if not _orchestrator:
        return []
    return await _orchestrator.list_toolsmith_artifacts()


@app.delete("/toolsmith/artifacts/{artifact_id}")
async def remove_artifact(artifact_id: str) -> dict:
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    ok = await _orchestrator.remove_artifact(artifact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="artifact not found")
    if _registry:
        adapter_url = os.environ.get("CUGA_URL", "http://localhost:8000")
        await sync_from_adapter(_registry, adapter_url)
    return {"removed": True, "artifact_id": artifact_id}


class VaultPutRequest(BaseModel):
    tool_id: str
    secret_key: str
    value: str


class VaultDeleteRequest(BaseModel):
    tool_id: str
    secret_key: str | None = None


@app.post("/vault/secret")
async def vault_put(req: VaultPutRequest) -> dict:
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    try:
        return await _orchestrator.toolsmith.vault_put(req.tool_id, req.secret_key, req.value)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"toolsmith vault put failed: {exc}")


@app.post("/vault/delete")
async def vault_delete(req: VaultDeleteRequest) -> dict:
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    try:
        return await _orchestrator.toolsmith.vault_delete(req.tool_id, req.secret_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"toolsmith vault delete failed: {exc}")


@app.get("/vault/keys/{tool_id}")
async def vault_list_keys(tool_id: str) -> dict:
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    try:
        return await _orchestrator.toolsmith.vault_list_keys(tool_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"toolsmith vault list failed: {exc}")


@app.get("/vault/missing/{artifact_id}")
async def vault_missing(artifact_id: str) -> dict:
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    try:
        return await _orchestrator.toolsmith.vault_missing(artifact_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"toolsmith vault missing failed: {exc}")


@app.post("/internal/artifacts_changed")
async def artifacts_changed() -> dict:
    """Webhook called by the Toolsmith service when its artifact set changes.
    We resync the planner and refresh our registry."""
    if not _orchestrator:
        return {"ok": False, "reason": "not initialized"}
    try:
        reload_result = await _orchestrator.sync_planner_with_toolsmith()
    except Exception as exc:  # noqa: BLE001
        log.exception("artifacts_changed sync failed")
        return {"ok": False, "reason": str(exc)}
    if _registry:
        adapter_url = os.environ.get("CUGA_URL", "http://localhost:8000")
        await sync_from_adapter(_registry, adapter_url)
    return {"ok": True, "reload": reload_result}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    assert _orchestrator is not None
    turn = await _orchestrator.chat(req.message, thread_id=req.thread_id)
    return ChatResponse(
        response=turn.answer,
        thread_id=req.thread_id,
        error=turn.error,
        gap=turn.gap,
        acquisition=turn.acquisition,
        tools_used=list(turn.tools_used or []),
    )
