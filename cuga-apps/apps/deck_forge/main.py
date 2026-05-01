"""
DeckForge — FastAPI server.

Endpoints
---------
GET  /                            → serve static/index.html
GET  /api/config/status           → LLM auto-detect result
POST /api/generate                → start a generation session
GET  /api/stream/{session_id}     → SSE progress stream
GET  /api/session/{session_id}    → session status / result
GET  /api/download/{sid}/{fname}  → download output file

Run
---
    python main.py --port 28802
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = Path(__file__).parent
OUTPUTS_DIR = HERE / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# Make demo_apps/ siblings importable (for _llm.py)
sys.path.insert(0, str(HERE.parent))

app = FastAPI(title="DeckForge")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

# ---------------------------------------------------------------------------
# In-memory session registry
# ---------------------------------------------------------------------------

_sessions: dict[str, "DeckForgeSession"] = {}  # type: ignore[name-defined]


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    directory: str
    topic: str
    agent_type: str = "langgraph"   # "langgraph" | "cuga" (cuga: future)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(str(HERE / "static" / "index.html"))


@app.get("/api/config/status")
async def config_status():
    """Auto-detect which LLM provider is available and which agents are supported."""
    try:
        from _llm import detect_provider
        provider = detect_provider()
        try:
            from cuga.sdk import CugaAgent  # noqa: F401
            cuga_available = True
        except ImportError:
            cuga_available = False
        return {"configured": True, "provider": provider, "cuga_available": cuga_available, "sample_data_path": str(HERE / "data")}
    except Exception as exc:
        return {"configured": False, "provider": None, "cuga_available": False, "error": str(exc), "sample_data_path": str(HERE / "data")}


@app.post("/api/generate")
async def generate(req: GenerateRequest):
    from session import DeckForgeSession

    sid = str(uuid4())[:8]
    output_dir = OUTPUTS_DIR / sid
    session = DeckForgeSession(
        session_id=sid,
        directory=req.directory,
        topic=req.topic,
        output_dir=output_dir,
        agent_type=req.agent_type,
    )
    _sessions[sid] = session

    asyncio.create_task(_run(session))
    return {"session_id": sid}


@app.get("/api/stream/{session_id}")
async def stream(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        return StreamingResponse(
            _single_event({"type": "error", "message": "session not found"}),
            media_type="text/event-stream",
        )

    async def event_gen():
        while True:
            try:
                msg = await asyncio.wait_for(session.queue.get(), timeout=60.0)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                yield "data: {\"type\":\"ping\"}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        return {"error": "not found"}
    return {
        "status":      session.status,
        "slide_count": len(session.slides),
        "result":      session.result,
        "error":       session.error,
    }


@app.get("/api/download/{session_id}/{filename}")
async def download(session_id: str, filename: str):
    session = _sessions.get(session_id)
    if not session:
        return {"error": "session not found"}
    # Sanitise filename — prevent path traversal
    safe_name = Path(filename).name
    file_path = session.output_dir / safe_name
    if not file_path.exists():
        return {"error": f"{safe_name} not found"}
    return FileResponse(
        str(file_path),
        filename=safe_name,
        media_type=(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            if safe_name.endswith(".pptx")
            else "text/markdown"
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _run(session):
    """Wrapper so exceptions from run_agent don't silently swallow."""
    from agent import run_agent
    try:
        await run_agent(session)
    except Exception as exc:
        session.status = "error"
        session.error  = str(exc)
        try:
            await session.queue.put({"type": "error", "message": str(exc)})
        except Exception:
            pass


async def _single_event(msg: dict):
    yield f"data: {json.dumps(msg)}\n\n"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="DeckForge demo server")
    parser.add_argument("--port", type=int, default=28802)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
