"""
Weather Wardrobe — CUGA Demo App

A FastAPI server that takes a city name and uses CugaAgent to fetch the live
weather forecast and return practical outfit advice for the next three days.

Usage:
  python main.py [--port 28835] [--provider anthropic] [--model claude-sonnet-4-6]

Required env vars:
  LLM_PROVIDER          — LLM backend: anthropic | openai | rits | watsonx | litellm | ollama
  LLM_MODEL             — Model name for the chosen provider
  AGENT_SETTING_CONFIG  — Path to the agent settings TOML file

Optional env vars (provider-specific):
  ANTHROPIC_API_KEY     — Required when LLM_PROVIDER=anthropic
  OPENAI_API_KEY        — Required when LLM_PROVIDER=openai
  RITS_API_KEY          — Required when LLM_PROVIDER=rits
"""

import argparse
import logging
import os
import sys
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap — must come before local imports
# ---------------------------------------------------------------------------
_DIR       = Path(__file__).parent
_DEMOS_DIR = _DIR.parent
for _p in [str(_DIR), str(_DEMOS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Robustness: AGENT_SETTING_CONFIG may arrive as an in-IMAGE absolute path
# (e.g. /app/apps/settings.watsonx.toml from build/.env) while running from a
# local checkout where it doesn't exist. CUGA aborts on a missing config file,
# so remap a non-existent absolute config to a local file of the same name.
_asc = os.environ.get("AGENT_SETTING_CONFIG", "")
if os.path.isabs(_asc) and not os.path.isfile(_asc):
    for _cand in (_DIR / os.path.basename(_asc), _DEMOS_DIR / os.path.basename(_asc)):
        if _cand.is_file():
            os.environ["AGENT_SETTING_CONFIG"] = str(_cand)
            break

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Third-party imports (after path bootstrap)
# ---------------------------------------------------------------------------
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ui import _HTML

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class _FieldShim:
    """Minimal Pydantic FieldInfo stand-in.

    cuga 0.3.x calls ``input_model.model_fields[name].annotation`` inside
    arg_warning.py. With langchain-mcp-adapters >= 0.3.x, args_schema is a
    raw JSON-Schema dict, so model_fields returns plain dicts that have no
    ``.annotation`` attribute — crashing on every MCP tool call. This shim
    wraps each JSON-Schema property entry so ``.annotation`` is always present.
    It lives here rather than in the shared _mcp_bridge so this fix is fully
    self-contained within the weather_wardrobe app.
    """
    _JS_TO_PY: dict = {
        "string": str, "integer": int, "number": float,
        "boolean": bool, "array": list, "object": dict,
    }

    def __init__(self, prop: dict) -> None:
        js_type = prop.get("type") if isinstance(prop, dict) else None
        self.annotation = self._JS_TO_PY.get(js_type)


def _patch_tool(tool):
    """Fix two incompatibilities between langchain-mcp-adapters 0.3.x and cuga 0.3.x.

    Problem 1 — response_format mismatch:
      langchain-mcp-adapters registers tools with response_format='content_and_artifact',
      so StructuredTool.ainvoke() validates that the coroutine returns a (content, artifact)
      tuple. _mcp_bridge already unwraps the coroutine to return a plain dict, but cuga's
      toolguard calls tool.ainvoke() which enforces the tuple contract and raises ValueError.
      Fix: set response_format='content' so ainvoke stops expecting a tuple.

    Problem 2 — args_schema.model_fields returns plain dicts:
      cuga's arg_warning.py calls f.annotation on each model_fields value, expecting Pydantic
      FieldInfo objects. With the adapter the values are raw JSON-Schema dicts with no
      .annotation. Fix: wrap each in a _FieldShim that exposes .annotation.
    """
    # ── Fix 1: clear response_format ──────────────────────────────────────
    try:
        if getattr(tool, "response_format", None) == "content_and_artifact":
            tool.response_format = "content"
    except (AttributeError, TypeError):
        pass

    # ── Fix 2: patch model_fields to return _FieldShim objects ────────────
    schema = getattr(tool, "args_schema", None)
    if schema is not None:
        existing = getattr(schema, "model_fields", None)
        if existing is not None:
            sample = next(iter(existing.values()), None) if existing else None
            if sample is not None and not hasattr(sample, "annotation"):
                props = dict(existing)

                class _PatchedSchema(type(schema)):
                    @property
                    def model_fields(self_inner):  # noqa: N805
                        return {name: _FieldShim(p) for name, p in props.items()}

                try:
                    tool.args_schema.__class__ = _PatchedSchema
                except TypeError:
                    shims = {name: _FieldShim(p) for name, p in props.items()}
                    try:
                        object.__setattr__(tool.args_schema, "model_fields", shims)
                    except (AttributeError, TypeError):
                        pass

    return tool


def _make_tools():
    # Delegated to MCP server(s): geo.
    from _mcp_bridge import load_tools
    tools = load_tools(["geo"])
    return [_patch_tool(t) for t in tools]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a practical, friendly outfit adviser.

For every question:
1. Call get_weather for the city the user names.
2. For each of the 3 forecast days, give a one-line outfit: layers (base / warm layer / outer), rain gear if rain is likely, and suitable shoes.
3. Add **Heads-up:** one line about the day that needs the most planning (e.g. rain in the afternoon, a big temperature swing).
4. Show temperatures in °C, and in °F too if the user seems to be in the US.

Base advice only on the forecast data you received. If the weather call fails or the city isn't found, say so and ask for a nearby larger city.
"""


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

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
        enable_knowledge=False,
        auto_load_policies=False,
    )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

def _web(port: int):
    import uvicorn

    app = FastAPI(title="Weather Wardrobe", version="1.0.0")

    # Lazy-initialise the agent on first request so startup is instant
    _agent = None

    def _get_agent():
        nonlocal _agent
        if _agent is None:
            log.info("Initialising CugaAgent…")
            _agent = make_agent()
            log.info("CugaAgent ready.")
        return _agent

    class AskRequest(BaseModel):
        question: str

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.post("/ask")
    async def ask(req: AskRequest):
        from _usage import track_utterance; track_utterance(req.question)
        thread_id = str(uuid.uuid4())
        try:
            agent = _get_agent()
            result = await agent.invoke(req.question, thread_id=thread_id)
            answer = result.answer if hasattr(result, "answer") else str(result)
            return {"answer": answer}
        except Exception as exc:
            log.exception("Agent invocation failed")
            return JSONResponse(status_code=500, content={"answer": f"Error: {exc}"})

    @app.get("/health")
    async def health():
        return {"ok": True}

    # Public deployment: layered, in-memory rate limiting on POST.
    from _ratelimit import install_rate_limit
    install_rate_limit(app)
    from _usage import install_usage
    install_usage(app)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weather Wardrobe — CUGA demo app")
    parser.add_argument("--port", type=int, default=28835)
    parser.add_argument(
        "--provider", "-p", default=None,
        choices=["rits", "watsonx", "openai", "anthropic", "litellm", "ollama"],
    )
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    print(f"\n  Weather Wardrobe  →  http://127.0.0.1:{args.port}\n")
    _web(args.port)
