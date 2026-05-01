"""Toolsmith FastAPI service.

Exposes the LangGraph ReAct Toolsmith agent over HTTP. Same swappability
pattern as the cuga adapter, but Toolsmith is the *durable* side — it
holds the user's growing tool universe.

Endpoints:
  GET  /health
  POST /acquire    → run the ReAct loop on a gap, return result + transcript
  GET  /tools      → list installed tool artifacts (summary)
  GET  /tools/{id} → full artifact (including code body)
  POST /tools/{id}/probe → re-run probe against an existing artifact
  DELETE /tools/{id}     → remove an artifact

The backend orchestrator talks to this over HTTP via ToolsmithClient.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .agent import AcquireResult, Toolsmith
from .artifact import ToolArtifact

log = logging.getLogger("toolsmith")


class _State:
    smith: Optional[Toolsmith] = None


# Backend's URL — Toolsmith calls back here when artifacts change so the
# backend can refresh its registry and reload cuga.
_BACKEND_NOTIFY_URL = os.environ.get("BACKEND_NOTIFY_URL", "http://chief-of-staff-backend:8765/internal/artifacts_changed")


async def _notify_backend(_artifact: Optional[ToolArtifact]) -> None:
    """Tell the backend to resync with current artifact state. Fire-and-forget."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(_BACKEND_NOTIFY_URL)
    except httpx.HTTPError as exc:
        log.warning("notify-backend failed (continuing): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _State.smith = Toolsmith(on_artifact_change=_notify_backend)
    log.info("Toolsmith ready: coder=%s llm=%s artifacts=%d",
             _State.smith.coder.name,
             "yes" if _State.smith.llm is not None else "no",
             len(_State.smith.list_artifacts()))
    yield


app = FastAPI(title="Toolsmith", version="0.1.0", lifespan=lifespan)


class AcquireRequest(BaseModel):
    gap: dict


class AcquireResponse(BaseModel):
    success: bool
    artifact_id: Optional[str]
    summary: str
    transcript: list[dict]
    artifact: Optional[dict] = None
    needs_secrets: Optional[dict] = None
    already_existed: bool = False


@app.get("/health")
async def health() -> dict:
    smith = _State.smith
    return {
        "status": "ok" if smith is not None else "initializing",
        "coder": smith.coder.name if smith else None,
        "orchestration_llm": (smith.llm is not None) if smith else False,
        "artifact_count": len(smith.list_artifacts()) if smith else 0,
    }


@app.post("/acquire", response_model=AcquireResponse)
async def acquire(req: AcquireRequest) -> AcquireResponse:
    if _State.smith is None:
        raise HTTPException(status_code=503, detail="Toolsmith not initialized")
    result: AcquireResult = await _State.smith.acquire(req.gap)
    artifact_dict = None
    if result.artifact_id:
        loaded = _State.smith.store.load(result.artifact_id)
        if loaded:
            artifact_dict = loaded.to_mcp_tool_spec()
    return AcquireResponse(
        success=result.success, artifact_id=result.artifact_id,
        summary=result.summary, transcript=result.transcript,
        artifact=artifact_dict,
        needs_secrets=result.needs_secrets,
        already_existed=result.already_existed,
    )


@app.get("/tools")
async def list_tools() -> list[dict]:
    if _State.smith is None:
        return []
    return _State.smith.list_artifacts()


@app.get("/tools/{artifact_id}")
async def get_tool(artifact_id: str) -> dict:
    if _State.smith is None:
        raise HTTPException(status_code=503, detail="Toolsmith not initialized")
    artifact = _State.smith.store.load(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return {
        **artifact.to_summary(),
        "code": artifact.code,
        "mcp_tool_spec": artifact.to_mcp_tool_spec(),
    }


@app.delete("/tools/{artifact_id}")
async def delete_tool(artifact_id: str) -> dict:
    if _State.smith is None:
        raise HTTPException(status_code=503, detail="Toolsmith not initialized")
    ok = await _State.smith.remove_artifact(artifact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="artifact not found")
    return {"removed": True, "artifact_id": artifact_id}


# ---------------------------------------------------------------------------
# Vault — secret storage proxied via Toolsmith. Phase 3.6.
# ---------------------------------------------------------------------------

class VaultPutRequest(BaseModel):
    tool_id: str
    secret_key: str
    value: str


class VaultDeleteRequest(BaseModel):
    tool_id: str
    secret_key: str | None = None


@app.get("/vault/keys/{tool_id}")
async def vault_list_keys(tool_id: str) -> dict:
    """List which secret keys are present for a tool (values not returned)."""
    if _State.smith is None:
        raise HTTPException(status_code=503, detail="Toolsmith not initialized")
    return {
        "tool_id": tool_id,
        "keys": _State.smith.vault.list_keys(tool_id),
        "backend": _State.smith.vault.backend_name,
    }


@app.post("/vault/secret")
async def vault_put(req: VaultPutRequest) -> dict:
    if _State.smith is None:
        raise HTTPException(status_code=503, detail="Toolsmith not initialized")
    if not req.value:
        raise HTTPException(status_code=400, detail="value cannot be empty")
    _State.smith.vault.put(req.tool_id, req.secret_key, req.value)
    # Notify the backend so it can resync the adapter — the new secret may
    # unblock a previously-disabled tool.
    await _notify_backend(None)
    return {"stored": True, "tool_id": req.tool_id, "secret_key": req.secret_key}


@app.post("/vault/delete")
async def vault_delete(req: VaultDeleteRequest) -> dict:
    if _State.smith is None:
        raise HTTPException(status_code=503, detail="Toolsmith not initialized")
    _State.smith.vault.delete(req.tool_id, req.secret_key)
    await _notify_backend(None)
    return {"deleted": True, "tool_id": req.tool_id, "secret_key": req.secret_key}


@app.get("/vault/missing/{artifact_id}")
async def vault_missing(artifact_id: str) -> dict:
    """Which required secrets are still unset for this artifact?"""
    if _State.smith is None:
        raise HTTPException(status_code=503, detail="Toolsmith not initialized")
    artifact = _State.smith.store.load(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    required = list(artifact.manifest.requires_secrets or [])
    missing = _State.smith.vault.missing(artifact_id, required)
    return {
        "artifact_id": artifact_id,
        "required": required,
        "missing": missing,
        "ready": len(missing) == 0,
    }


@app.get("/specs/all_artifacts")
async def all_artifact_specs() -> list[dict]:
    """Return every artifact's MCP-tool-spec — the backend uses this on
    startup to reconstruct the full extra_tools list for the cuga adapter."""
    if _State.smith is None:
        return []
    out = []
    for summary in _State.smith.list_artifacts():
        artifact = _State.smith.store.load(summary["id"])
        if artifact:
            out.append(artifact.to_mcp_tool_spec())
    return out


@app.get("/effective_state")
async def effective_state() -> dict:
    """Combined view the backend hands to cuga's /agent/reload.

    Splits artifacts by provenance.source:
      - source == "catalog"  → contributes to mcp_servers (the cuga adapter
        loads it via apps/_mcp_bridge load_tools)
      - everything else      → contributes to extra_tools (executed in the
        adapter against an import-allowlisted exec namespace)

    Phase 3.6: includes a `secrets` map (artifact_id → {key: value}) so the
    adapter can inject per-tool credentials at call time. Tools whose required
    secrets aren't in the vault are filtered out — they'd error at call time
    anyway. The frontend learns about them via /vault/missing.
    """
    if _State.smith is None:
        return {"mcp_servers": [], "extra_tools": [], "secrets": {}, "blocked_artifacts": []}

    mcp_servers: list[str] = []
    extra_tools: list[dict] = []
    secrets: dict[str, dict[str, str]] = {}
    blocked: list[dict] = []

    for summary in _State.smith.list_artifacts():
        artifact = _State.smith.store.load(summary["id"])
        if artifact is None:
            continue
        source = (artifact.manifest.provenance or {}).get("source", "openapi")
        # Catalog mounts are MCP servers loaded by the adapter directly.
        if source == "catalog" and artifact.manifest.kind != "browser_task":
            target = artifact.manifest.name
            if target and target not in mcp_servers:
                mcp_servers.append(target)
            continue

        required = list(artifact.manifest.requires_secrets or [])
        missing = _State.smith.vault.missing(artifact.manifest.id, required)
        if missing:
            blocked.append({"artifact_id": artifact.manifest.id, "missing": missing})
            continue

        # Phase 4 — both code-kind and browser_task-kind artifacts ride
        # extra_tools. The adapter dispatches based on spec["kind"].
        spec = artifact.to_mcp_tool_spec()
        spec["id"] = artifact.manifest.id
        extra_tools.append(spec)
        if required:
            secrets[artifact.manifest.id] = _State.smith.vault.all_secrets_for(artifact.manifest.id)

    return {
        "mcp_servers": mcp_servers,
        "extra_tools": extra_tools,
        "secrets": secrets,
        "blocked_artifacts": blocked,
    }
