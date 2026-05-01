"""
API Doc Generator — web UI powered by CugaAgent
================================================

Upload an OpenAPI spec (JSON/YAML) or select a built-in sample to generate
human-readable API documentation with realistic example requests/responses.
The agent explains each endpoint in plain English and refines docs iteratively.

Run:
    python main.py
    python main.py --port 28811
    python main.py --provider anthropic

Then open: http://127.0.0.1:28811

Environment variables:
    LLM_PROVIDER          rits | anthropic | openai | ollama | watsonx | litellm
    LLM_MODEL             model name for the chosen provider
    AGENT_SETTING_CONFIG  path to agent settings TOML file
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent

for _p in [str(_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv(_DEMOS_DIR / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Spec store — mutable container shared by tools and FastAPI endpoints
# ---------------------------------------------------------------------------

_spec_store: dict = {"spec": None, "raw": "", "title": "", "version": ""}


def _load_spec(raw: str) -> dict:
    try:
        spec = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        try:
            import yaml  # type: ignore
            spec = yaml.safe_load(raw)
        except Exception as exc:
            return {"error": f"Could not parse spec as JSON or YAML: {exc}"}
    if not isinstance(spec, dict):
        return {"error": "Spec must be a JSON object / YAML mapping"}
    _spec_store["spec"] = spec
    _spec_store["raw"] = raw
    info = spec.get("info", {})
    _spec_store["title"] = info.get("title", "Untitled API")
    _spec_store["version"] = info.get("version", "")
    return {"ok": True, "title": _spec_store["title"], "version": _spec_store["version"]}


def _get_base_url(spec: dict) -> str:
    servers = spec.get("servers", [])
    if servers and isinstance(servers[0], dict):
        return servers[0].get("url", "https://api.example.com")
    host = spec.get("host", "api.example.com")
    scheme = (spec.get("schemes") or ["https"])[0]
    base = spec.get("basePath", "/")
    return f"{scheme}://{host}{base}"


# ---------------------------------------------------------------------------
# LangChain tools
# ---------------------------------------------------------------------------

def _make_tools():
    from langchain_core.tools import tool as _tool

    @_tool
    def list_endpoints() -> str:
        """
        List all API endpoints in the currently loaded OpenAPI spec.
        Returns each endpoint's path, HTTP method, summary, tags, and operationId.
        Call this first to understand the full API surface before writing docs.
        """
        spec = _spec_store.get("spec")
        if not spec:
            return json.dumps({"error": "No OpenAPI spec loaded. Ask the user to select or upload one."})
        paths = spec.get("paths", {})
        endpoints = []
        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, details in methods.items():
                if method.lower() not in ("get", "post", "put", "patch", "delete", "head", "options"):
                    continue
                if not isinstance(details, dict):
                    continue
                endpoints.append({
                    "path": path,
                    "method": method.upper(),
                    "summary": details.get("summary", ""),
                    "description": (details.get("description") or "")[:150],
                    "operationId": details.get("operationId", ""),
                    "tags": details.get("tags", []),
                })
        info = spec.get("info", {})
        return json.dumps({
            "api_title": info.get("title", ""),
            "api_version": info.get("version", ""),
            "base_url": _get_base_url(spec),
            "description": (info.get("description") or "")[:300],
            "endpoint_count": len(endpoints),
            "endpoints": endpoints,
        }, ensure_ascii=False, indent=2)

    @_tool
    def get_endpoint_details(path: str, method: str) -> str:
        """
        Get full details for a specific API endpoint: all parameters, request body
        schema, response schemas, auth requirements, and any inline examples.
        Call this for each endpoint you are documenting.

        Args:
            path:   API path exactly as it appears in the spec, e.g. /users/{id}
            method: HTTP method in any case, e.g. GET, post, Delete
        """
        spec = _spec_store.get("spec")
        if not spec:
            return json.dumps({"error": "No spec loaded."})
        paths = spec.get("paths", {})
        method_lc = method.lower()
        endpoint = paths.get(path, {}).get(method_lc)
        if endpoint is None:
            # Try case-insensitive path match
            for p, methods in paths.items():
                if p.lower() == path.lower() and method_lc in methods:
                    endpoint = methods[method_lc]
                    break
        if endpoint is None:
            available = [f"{m.upper()} {p}" for p, ms in paths.items()
                         if isinstance(ms, dict) for m in ms
                         if m.lower() in ("get","post","put","patch","delete")]
            return json.dumps({"error": f"{method.upper()} {path} not found.",
                               "available_endpoints": available[:20]})
        result = dict(endpoint)
        result["_base_url"] = _get_base_url(spec)
        components = spec.get("components", {})
        result["_security_schemes"] = components.get("securitySchemes",
                                       spec.get("securityDefinitions", {}))
        return json.dumps(result, ensure_ascii=False, indent=2)

    @_tool
    def get_schema(schema_name: str) -> str:
        """
        Look up a data model / schema definition from the OpenAPI spec's
        components/schemas (OpenAPI 3.x) or definitions (Swagger 2.x) section.
        Use this to resolve $ref references and document request/response shapes.

        Args:
            schema_name: Schema name only, e.g. 'User', 'Order', 'ApiError'
                         (not the full $ref path)
        """
        spec = _spec_store.get("spec")
        if not spec:
            return json.dumps({"error": "No spec loaded."})
        schemas = spec.get("components", {}).get("schemas", {})
        definitions = spec.get("definitions", {})
        combined = {**definitions, **schemas}
        if schema_name in combined:
            return json.dumps(combined[schema_name], ensure_ascii=False, indent=2)
        # Case-insensitive fallback
        for k, v in combined.items():
            if k.lower() == schema_name.lower():
                return json.dumps(v, ensure_ascii=False, indent=2)
        return json.dumps({
            "error": f"Schema '{schema_name}' not found.",
            "available_schemas": list(combined.keys()),
        })

    return [list_endpoints, get_endpoint_details, get_schema]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """
# API Documentation Generator

You are a senior technical writer who specialises in developer-facing API docs.
Your job is to produce clear, accurate, copy-paste-ready documentation from
OpenAPI/Swagger specs.

## Workflow

When the user asks you to document an API or one or more endpoints:

1. Call `list_endpoints` to see all paths, methods, and the base URL.
2. For each endpoint to document, call `get_endpoint_details` to get the full spec.
3. When details reference a $ref schema (e.g. '#/components/schemas/User'), call
   `get_schema` with just the schema name (e.g. 'User') to expand it.
4. Write the docs in the output format below.

## Output format (Markdown)

Start with a brief API overview section, then one section per endpoint:

---
## Overview

**{API Title}** `v{version}`

Base URL: `{base_url}`

One paragraph describing what the API does and who it is for.

---
### {METHOD} {path} — {Short title}

**Description:** What this endpoint does in 1-2 plain-English sentences.

**Authentication:** Bearer token / API key in `X-Api-Key` header / None

**Path parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | string | Yes | User UUID |

**Query parameters:** (omit table if none)
| Parameter | Type | Required | Default | Description |

**Request body:** (omit if GET/DELETE with no body)
| Field | Type | Required | Description |
|-------|------|----------|-------------|

**Example request:**
```bash
curl -X {METHOD} {base_url}{path} \\
  -H "Authorization: Bearer <token>" \\
  -H "Content-Type: application/json" \\
  -d '{...}'
```

**Example response (200 OK):**
```json
{...}
```

**Error responses:**
| Status | When it happens |
|--------|----------------|
| 400 | ... |
| 401 | ... |

---

## Rules for realistic examples

- Never use placeholder values like "string", "integer", or "example.com".
- Infer realistic values from field names:
    - name → "Alice Chen", email → "alice@acme.com"
    - id → "usr_a1b2c3d4" or 42
    - amount → 4999, currency → "USD"
    - status → "active", created_at → "2026-04-22T10:30:00Z"
    - token → "eyJhbGci..." (truncated JWT)
- Always include the correct Content-Type and auth headers in curl examples.
- Use the real base URL from the spec.
- Show 2xx and at least 2 error status codes per endpoint.

## Refinement

If the user asks to adjust format, focus on certain endpoints, export as a
Postman collection, add more examples, or change the tone — do it and
reproduce the relevant sections in full.
"""


def make_agent():
    from cuga.sdk import CugaAgent
    from _llm import create_llm

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402


class AskReq(BaseModel):
    question: str


class LoadSpecReq(BaseModel):
    raw: str


class LoadSpecUrlReq(BaseModel):
    url: str


# ---------------------------------------------------------------------------
# Web app
# ---------------------------------------------------------------------------

def _web(port: int) -> None:
    import uvicorn
    from fastapi import FastAPI, UploadFile, File
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse
    from ui import _HTML

    app = FastAPI(title="API Doc Generator", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    _agent = make_agent()
    _thread_id = uuid.uuid4().hex[:8]
    _conversation: list[dict] = []

    @app.post("/ask")
    async def api_ask(req: AskReq):
        nonlocal _thread_id
        question = req.question.strip()
        if not question:
            return JSONResponse({"error": "Empty question"}, status_code=400)

        spec_context = ""
        if _spec_store.get("title"):
            spec_context = (f"[Current spec: {_spec_store['title']} "
                            f"{_spec_store['version']}] ")

        _conversation.append({"role": "user", "text": question})
        try:
            result = await _agent.invoke(
                spec_context + question,
                thread_id=f"apidoc-{_thread_id}",
            )
            answer = result.answer
            _conversation.append({"role": "agent", "text": answer})
            return {"answer": answer, "conversation": _conversation}
        except Exception as exc:
            log.error("Agent error: %s", exc)
            err = str(exc)
            _conversation.append({"role": "agent", "text": f"Error: {err}"})
            return JSONResponse({"error": err}, status_code=500)

    @app.post("/load-spec")
    async def api_load_spec(req: LoadSpecReq):
        result = _load_spec(req.raw)
        if "error" in result:
            return JSONResponse(result, status_code=400)
        return result

    @app.post("/upload-spec")
    async def api_upload_spec(file: UploadFile = File(...)):
        raw = (await file.read()).decode("utf-8", errors="replace")
        result = _load_spec(raw)
        if "error" in result:
            return JSONResponse(result, status_code=400)
        return result

    @app.post("/load-spec-url")
    async def api_load_spec_url(req: LoadSpecUrlReq):
        import httpx
        url = req.url.strip()
        if not url:
            return JSONResponse({"error": "URL is required"}, status_code=400)
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
                r = await client.get(url)
            if r.status_code >= 400:
                return JSONResponse(
                    {"error": f"Fetch failed: HTTP {r.status_code}"},
                    status_code=400,
                )
        except httpx.HTTPError as exc:
            return JSONResponse({"error": f"Fetch failed: {exc}"}, status_code=400)
        result = _load_spec(r.text)
        if "error" in result:
            return JSONResponse(result, status_code=400)
        return result

    @app.get("/spec-info")
    async def api_spec_info():
        spec = _spec_store.get("spec")
        if not spec:
            return {"loaded": False}
        paths = spec.get("paths", {})
        endpoint_count = sum(
            1 for ms in paths.values() if isinstance(ms, dict)
            for m in ms if m.lower() in ("get","post","put","patch","delete")
        )
        return {
            "loaded": True,
            "title": _spec_store["title"],
            "version": _spec_store["version"],
            "endpoint_count": endpoint_count,
            "base_url": _get_base_url(spec),
        }

    @app.get("/conversation")
    async def api_conversation():
        return _conversation

    @app.post("/reset")
    async def api_reset():
        nonlocal _thread_id
        _thread_id = uuid.uuid4().hex[:8]
        _conversation.clear()
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def ui():
        return HTMLResponse(_HTML)

    print(f"\n  API Doc Generator  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="API Doc Generator")
    parser.add_argument("--port", type=int, default=28811)
    parser.add_argument("--provider", "-p", default=None,
                        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"])
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    _web(args.port)
