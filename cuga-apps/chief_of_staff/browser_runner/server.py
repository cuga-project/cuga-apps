"""Browser runner FastAPI service.

Lives separately from the cuga adapter so we can run a real browser
(Chromium via Playwright) in its own container with its own resource
budget. The cuga adapter dispatches `kind: browser_task` artifacts here
at call time.

Endpoints:
  GET  /health
  POST /execute   {steps, inputs, secrets, allow_user_confirm} → result
  POST /probe     {steps, sample_input, secrets} → {ok, reason, ...}
  GET  /sessions/{provider}  status of a stored profile
  POST /sessions/{provider}/clear  wipe a profile
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

from .executor import build_executor

log = logging.getLogger("browser-runner")


class _State:
    executor = None
    profiles_dir: Path = Path(os.environ.get("BROWSER_PROFILES_DIR", "/data/profiles"))


# Optional callback for user_confirm steps. Phase 4 v1 ships this as a
# webhook to the backend, which can surface a confirmation modal in the UI.
# For now, defaults to "auto-deny" — safer default; explicit flag enables
# auto-approve for benchmarks.
_CONFIRM_WEBHOOK_URL = os.environ.get("CONFIRM_WEBHOOK_URL", "").strip()


async def _confirm(prompt: str) -> bool:
    if os.environ.get("BROWSER_AUTO_CONFIRM") == "1":
        return True
    if not _CONFIRM_WEBHOOK_URL:
        log.warning("user_confirm step needs operator approval but no callback wired; denying")
        return False
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(_CONFIRM_WEBHOOK_URL, json={"prompt": prompt})
            r.raise_for_status()
            return bool((r.json() or {}).get("approved"))
    except httpx.HTTPError as exc:
        log.warning("confirm webhook failed: %s — denying", exc)
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    _State.profiles_dir.mkdir(parents=True, exist_ok=True)
    _State.executor = build_executor(str(_State.profiles_dir))
    log.info("Browser runner ready: executor=%s profiles=%s",
             _State.executor.name, _State.profiles_dir)
    try:
        yield
    finally:
        if _State.executor is not None:
            await _State.executor.aclose()


app = FastAPI(title="Browser Runner", version="0.1.0", lifespan=lifespan)


class ExecuteRequest(BaseModel):
    steps: list[dict]
    inputs: dict = {}
    secrets: dict = {}
    allow_user_confirm: bool = True


class ProbeRequest(BaseModel):
    steps: list[dict]
    sample_input: dict = {}
    secrets: dict = {}


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok" if _State.executor is not None else "initializing",
        "executor": getattr(_State.executor, "name", None),
        "profiles_dir": str(_State.profiles_dir),
    }


@app.post("/execute")
async def execute(req: ExecuteRequest) -> dict:
    if _State.executor is None:
        raise HTTPException(status_code=503, detail="executor not initialized")
    callback = _confirm if req.allow_user_confirm else None
    return await _State.executor.run(
        req.steps, inputs=req.inputs, secrets=req.secrets,
        confirm_callback=callback,
    )


@app.post("/probe")
async def probe(req: ProbeRequest) -> dict:
    if _State.executor is None:
        raise HTTPException(status_code=503, detail="executor not initialized")
    return await _State.executor.probe(
        req.steps, sample_input=req.sample_input, secrets=req.secrets,
    )


@app.get("/sessions/{provider}")
async def session_status(provider: str) -> dict:
    profile = _State.profiles_dir / provider
    return {
        "provider": provider,
        "exists": profile.exists(),
        "size_bytes": _profile_size(profile) if profile.exists() else 0,
    }


@app.post("/sessions/{provider}/clear")
async def session_clear(provider: str) -> dict:
    profile = _State.profiles_dir / provider
    if not profile.exists():
        return {"cleared": False, "reason": "no profile"}
    import shutil
    shutil.rmtree(profile)
    return {"cleared": True, "provider": provider}


def _profile_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total
