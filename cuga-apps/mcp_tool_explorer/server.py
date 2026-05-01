"""
MCP Tool Explorer — browse every MCP server in this stack and invoke tools.

Serves a single-page UI that:
  - Lists every MCP server from apps/_ports.MCP_PORTS (web, knowledge, geo,
    finance, code, local) with a reachability badge.
  - Introspects each server via the MCP protocol (`tools/list`) and shows
    name, description, and JSON-Schema input shape.
  - Renders a form per tool and lets you invoke it (`tools/call`) with
    arbitrary arguments, displaying the structured response.

The MCP servers already run as their own Docker containers (see
docker-compose.yml) and expose streamable-HTTP at
`http://localhost:291xx/mcp`. This app is a pure client — it does not
start or manage those containers.

Run:
    python mcp_tool_explorer/server.py                 # default :28900
    python mcp_tool_explorer/server.py --port 28901
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from apps._ports import MCP_PORTS  # noqa: E402

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  [mcp-tool-explorer]  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_IN_DOCKER = Path("/.dockerenv").exists() or os.getenv("CUGA_IN_DOCKER") == "1"
_ON_CE = bool(
    os.getenv("CE_APP")
    or os.getenv("CE_REVISION")
    or (os.getenv("CUGA_TARGET", "") or "").lower() == "ce"
)

# Default CE project hardcodes — overridden by CE-injected CE_SUBDOMAIN /
# CE_REGION when running on Code Engine.
_CE_PROJECT_HASH_DEFAULT = "1gxwxi8kos9y"
_CE_REGION_DEFAULT       = "us-east"


def _server_url(name: str) -> str:
    # 1. Per-server explicit override always wins.
    env_override = os.getenv(f"MCP_{name.upper()}_URL")
    if env_override:
        return env_override
    # 2. On Code Engine, derive from the deployed app naming convention.
    if _ON_CE:
        project_hash = (
            os.getenv("CE_SUBDOMAIN")
            or os.getenv("CE_PROJECT_HASH")
            or _CE_PROJECT_HASH_DEFAULT
        )
        region = os.getenv("CE_REGION") or _CE_REGION_DEFAULT
        return f"https://cuga-apps-mcp-{name}.{project_hash}.{region}.codeengine.appdomain.cloud/mcp"
    # 3. In docker compose, use the service DNS.
    host = f"mcp-{name}" if _IN_DOCKER else "localhost"
    return f"http://{host}:{MCP_PORTS[name]}/mcp"


def _probe_target(url: str, fallback_port: int) -> tuple[str, int]:
    host_part = url.split("://", 1)[-1].split("/", 1)[0]
    host, _, port_str = host_part.partition(":")
    try:
        port = int(port_str) if port_str else fallback_port
    except ValueError:
        port = fallback_port
    return host, port


def _tcp_reachable(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


@asynccontextmanager
async def _session(url: str):
    async with streamablehttp_client(url) as (read, write, _close):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _list_tools(name: str) -> list[dict]:
    url = _server_url(name)
    async with _session(url) as session:
        result = await session.list_tools()
        tools: list[dict] = []
        for tool in result.tools:
            tools.append({
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
            })
        return tools


async def _call_tool(server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    url = _server_url(server)
    async with _session(url) as session:
        result = await session.call_tool(tool, args)
        blocks: list[dict] = []
        for block in result.content or []:
            text = getattr(block, "text", None)
            if text is not None:
                blocks.append({"type": "text", "text": text})
                continue
            try:
                blocks.append({
                    "type": getattr(block, "type", block.__class__.__name__),
                    "data": block.model_dump(),
                })
            except Exception:
                blocks.append({"type": "unknown", "data": str(block)})
        return {"is_error": bool(result.isError), "content": blocks}


class CallReq(BaseModel):
    args: dict[str, Any] = {}


def make_app() -> FastAPI:
    app = FastAPI(title="MCP Tool Explorer")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/servers")
    async def api_servers():
        out = []
        for name, port in MCP_PORTS.items():
            url = _server_url(name)
            host, probe_port = _probe_target(url, port)
            out.append({
                "name": name,
                "port": port,
                "url": url,
                "online": _tcp_reachable(host, probe_port),
            })
        return out

    @app.get("/api/servers/{name}/tools")
    async def api_tools(name: str):
        if name not in MCP_PORTS:
            raise HTTPException(404, f"Unknown server: {name}")
        try:
            tools = await asyncio.wait_for(_list_tools(name), timeout=10.0)
            return {"tools": tools}
        except Exception as exc:
            log.exception("list_tools failed for %s", name)
            return JSONResponse(
                {"error": f"{type(exc).__name__}: {exc}", "tools": []},
                status_code=502,
            )

    @app.post("/api/servers/{name}/tools/{tool}/call")
    async def api_call(name: str, tool: str, req: CallReq):
        if name not in MCP_PORTS:
            raise HTTPException(404, f"Unknown server: {name}")
        try:
            result = await asyncio.wait_for(
                _call_tool(name, tool, req.args), timeout=120.0,
            )
            return result
        except Exception as exc:
            log.exception("call_tool failed for %s.%s", name, tool)
            return JSONResponse(
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "is_error": True,
                    "content": [],
                },
                status_code=502,
            )

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html_path = _HERE / "index.html"
        return HTMLResponse(html_path.read_text())

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP Tool Explorer")
    parser.add_argument("--port", type=int, default=28900)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    import uvicorn

    print(f"\n  MCP Tool Explorer  →  http://{args.host}:{args.port}\n")
    uvicorn.run(make_app(), host=args.host, port=args.port, log_level="warning")
