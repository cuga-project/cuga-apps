# Building a CUGA App Against Hosted MCP Servers — Self-Contained Spec

This spec is for **an LLM agent (or developer) who is building a brand-new
CUGA-powered app from scratch**, with **no access** to any reference repo.
You have:

- A pointer to a running set of **MCP servers** hosted on IBM Code Engine.
- An **LLM API key** of your choosing (Anthropic, OpenAI, etc.).
- A Python 3.11+ environment.

That's it. Everything else you need — the LLM factory, the MCP bridge, the
FastAPI scaffold, the UI shell — is embedded **verbatim** below. Copy the
code snippets directly into your project.

---

## 1. Background — what you're building

A **CUGA agent app** is a single Python process with three responsibilities:

1. Wrap a `CugaAgent` (from the `cuga` SDK) configured with **tools** + a
   **system prompt**. CUGA is an agent runtime that handles
   plan/execute/replan, code execution, and tool invocation for you. You
   write the tool list and the prompt; CUGA handles the loop.
2. Serve a **dark-themed HTML UI** from `GET /`.
3. Expose `POST /ask` (`{question, thread_id}` → `{answer}`) so the UI (or
   any client) can chat with the agent. Optionally, expose
   `GET /session/{thread_id}` so the UI can poll for live structured state.

A CUGA app is **glue** — your code wires up tools and routes; reasoning
lives inside the agent.

### Where tools come from

Two sources, picked freely:

- **MCP tools** — tools running on a separate process exposed over
  streamable HTTP. You connect, list tools, and call them. Stable,
  shareable, language-agnostic. Generic capabilities like "web search",
  "geocode", "look up Wikipedia article", "fetch RSS feed".
- **Inline `@tool` defs** — Python functions decorated with
  `langchain_core.tools.tool` defined inside your app. Used for
  app-specific state (sessions, in-memory stores) or one-off APIs.

Most real apps use **both**. The hosted MCP servers cover the generic
heavy-lifting; inline tools own the app's private state and the
"structured card" the UI renders.

---

## 2. The hosted MCP servers

### URL pattern

The full URL for each server is

```
https://cuga-apps-mcp-<NAME>.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp
```

Replace `<NAME>` with one of: `web`, `knowledge`, `geo`, `finance`, `code`,
`local`, `text`, `invocable_apis`.

These are **streamable-HTTP MCP** endpoints. A plain `GET` returns HTTP 406
("Not Acceptable") — that's expected. A correctly handshaking MCP client
(see the bridge in §6) gets back the tool list.

There is no auth on the URLs themselves. Some tools require server-side
API keys (e.g. Tavily, OpenTripMap, Alpha Vantage); those are set at
deploy time on the MCP host. If a key is missing, the matching tool
returns the envelope `{"ok": false, "code": "missing_key", ...}` and the
agent surfaces that gracefully — your app stays up.

### Tool catalog

The full set of hosted tools, by server. The exact arg shapes are
discovered at runtime by the bridge in §6, but the names + purpose +
return-shape hints below are stable and what you reference in your
system prompt.

#### `web` — generic web I/O

| Tool | Purpose | Notes / required server-side key |
|---|---|---|
| `web_search(query, max_results=6)` | Tavily search; recent web results with title/url/snippet/published. | Server needs `TAVILY_API_KEY`. |
| `fetch_webpage(url, max_chars=10000)` | Pull a URL, strip nav/scripts, return readable text. | none |
| `fetch_webpage_links(url, limit=100)` | Outbound hyperlinks as `(text, absolute_url)`. | none |
| `fetch_feed(url, max_items=20)` | Parse RSS/Atom; return feed title + items. | none |
| `search_feeds(feed_urls, keywords, max_per_feed=50)` | Keyword filter across multiple feeds. | none |
| `get_youtube_video_info(youtube_url)` | Title + channel + canonical URL via oEmbed. | none |
| `get_youtube_transcript(youtube_url, max_words=5000)` | Captions transcript with timestamps. | none |

#### `knowledge` — Wikipedia, arXiv, Semantic Scholar

| Tool | Purpose | Key |
|---|---|---|
| `search_wikipedia(query, max_results=6)` | Title/snippet/URL per match. | none |
| `get_wikipedia_article(title, full=False)` | Article extract (or full text). | none |
| `get_article_summary(title)` | Short lead summary. | none |
| `get_article_sections(title)` | Section headings. | none |
| `get_related_articles(title, max_results=8)` | Related-article suggestions. | none |
| `search_arxiv(query, max_results=6, category="")` | arXiv search. | none |
| `get_arxiv_paper(arxiv_id)` | One paper's metadata + abstract. | none |
| `search_semantic_scholar(query, max_results=6)` | Semantic Scholar search. | none |
| `get_paper_references(paper_id)` | Reference list of a paper. | none |

#### `geo` — geocoding, points of interest, weather

| Tool | Purpose | Key |
|---|---|---|
| `geocode(place)` | Place → lat/lon + canonical display name (Nominatim). | none |
| `find_hikes(lat, lon, radius_km, ...)` | Trails near a point (Overpass / OSM). | none |
| `search_attractions(lat, lon, category, limit)` | POIs around a point. | Server needs `OPENTRIPMAP_API_KEY` (free, 500/day). |
| `get_weather(city, travel_month="")` | Current weather + outlook (wttr.in). | none |

#### `finance` — quick price lookups

| Tool | Purpose | Key |
|---|---|---|
| `get_crypto_price(symbol, vs_currency="usd")` | CoinGecko price + 24h change. Accepts tickers (`btc`, `eth`) or slugs. | none |
| `get_stock_quote(symbol, api_key=None)` | Alpha Vantage daily quote. | Server needs `ALPHA_VANTAGE_API_KEY` (or pass `api_key`). |

#### `code` — code analysis primitives

| Tool | Purpose | Key |
|---|---|---|
| `check_python_syntax(code)` | AST validation; returns `{valid, error, line, col}`. | none |
| `extract_code_metrics(code)` | LOC, branch complexity, top-level defs. | none |
| `detect_language(code)` | Heuristic language ID. | none |

#### `local` — host-machine telemetry (runs on the MCP host, **not** your machine)

| Tool | Purpose | Key |
|---|---|---|
| `get_system_metrics()` | CPU/mem/disk/load. | none |
| `get_system_metrics_with_alerts(thresholds)` | Same + warn/crit classifications. | none |
| `list_top_processes(by="cpu", n=10)` | Top CPU/mem hogs. | none |
| `check_disk_usage(path="/")` | Free/used by mount. | none |
| `find_large_files(path, min_mb=100, max_results=20)` | Disk hogs. | none |
| `get_service_status(name)` | systemctl status (Linux only). | none |
| `transcribe_audio(file_path, language="")` | faster-whisper transcription. | none |

> **Caveat.** `local` reports the **MCP host's** view of the world, not the
> user's laptop. Useful for demos, surprising if you forget.

#### `text` — text transformations

| Tool | Purpose | Key |
|---|---|---|
| `chunk_text(text, strategy, size, overlap)` | Stateless chunking. | none |
| `count_tokens(text, encoding="cl100k_base")` | tiktoken count. | none |
| `extract_text(file_path)` | Docling: PDF/DOCX/XLSX/HTML → markdown. (file path on the MCP host) | none |
| `extract_text_from_bytes(bytes, ...)` | Same, from in-memory bytes. | none |

#### `invocable_apis` — dataset-synthesis primitives

Specialty server for synthesizing invocable APIs from SQL benchmarks.
Most apps will not need this. Skip unless you're building tooling for
the Bird benchmark.

### Tool return envelope (all servers)

Every MCP tool returns one of:

```json
{"ok": true, "data": <whatever the tool produces>}

{"ok": false, "error": "human message", "code": "bad_input | not_found | missing_key | upstream"}
```

The bridge in §6 unwraps the envelope so your tool callsite sees just the
`data` payload on success, or a clear `"ERROR: ..."` string on failure.
Inline `@tool` defs you write **must follow the same envelope** so a
future migration to MCP is a copy-paste move.

---

## 3. Prerequisites

### Python + packages

```bash
python -m venv .venv && source .venv/bin/activate
pip install --upgrade pip

# CUGA SDK — install however your access dictates. Two common paths:
#   1) From a wheel / private index:  pip install cuga
#   2) From a local clone:            pip install -e /path/to/cuga-agent

# Web framework + HTTP
pip install fastapi 'uvicorn[standard]' pydantic httpx

# LangChain core + MCP adapter (for the bridge in §6)
pip install langchain langchain-core langchain-mcp-adapters mcp

# Pick exactly the LLM provider(s) you actually use:
pip install langchain-anthropic   # if LLM_PROVIDER=anthropic
pip install langchain-openai      # if LLM_PROVIDER=openai or you go via an OpenAI-compatible endpoint
pip install langchain-ollama      # if LLM_PROVIDER=ollama
pip install langchain-ibm         # if LLM_PROVIDER=watsonx
pip install langchain-litellm     # if LLM_PROVIDER=litellm
# rits needs no extra package — it talks to the RITS REST endpoint over httpx,
# which is already installed above.
```

Verify the SDK loads:

```bash
python -c "from cuga.sdk import CugaAgent; print('cuga OK')"
```

If that fails, fix the install before proceeding.

### Environment variables

Set at least:

```bash
export LLM_PROVIDER=anthropic                # one of: anthropic | openai | rits | watsonx | litellm | ollama
export LLM_MODEL=claude-sonnet-4-6           # provider-specific; the factory has sensible defaults if unset
export ANTHROPIC_API_KEY=sk-ant-…            # set the key matching your provider (see table below)
```

Per-provider env vars the factory in §5 reads:

| Provider    | Required keys                                              | Optional / overrides                                          |
|-------------|------------------------------------------------------------|---------------------------------------------------------------|
| `anthropic` | `ANTHROPIC_API_KEY`                                        | —                                                             |
| `openai`    | `OPENAI_API_KEY`                                           | —                                                             |
| `rits`      | `RITS_API_KEY`                                             | `RITS_BASE_URL` (defaults to the IBM Research production URL) |
| `watsonx`   | `WATSONX_APIKEY` + (`WATSONX_PROJECT_ID` or `WATSONX_SPACE_ID`) | `WATSONX_URL` (defaults to `https://us-south.ml.cloud.ibm.com`) |
| `litellm`   | `LITELLM_API_KEY` + `LITELLM_BASE_URL`                     | falls back to `OPENAI_API_KEY` / `OPENAI_BASE_URL`            |
| `ollama`    | none                                                       | `OLLAMA_BASE_URL` (defaults to `http://localhost:11434`)      |

Optional, but useful:

```bash
# Force the bridge to use the public Code Engine MCP URLs (it does this
# automatically when CE_APP/CE_REVISION are set, but on a laptop you set
# this yourself).
export CUGA_TARGET=ce

# Override the URL of any individual MCP server (e.g. point at your own
# private deployment of one tool, while the rest still go to CE).
# export MCP_GEO_URL=https://my-private-mcp-geo.example.com/mcp
```

---

## 4. Files you write

A finished app is a single folder with **5 files**:

```
my_app/
├── main.py             FastAPI + CugaAgent + tools (REQUIRED)
├── ui.py               exports _HTML (REQUIRED)
├── _llm.py             multi-provider LLM factory  — copy verbatim from §5
├── _mcp_bridge.py      streamable-HTTP MCP loader  — copy verbatim from §6
└── requirements.txt    pinned deps                  — copy verbatim from §3
```

No `__init__.py`. No Dockerfile. No tests in the bundle.

---

## 5. `_llm.py` — copy verbatim

This is a multi-provider LLM factory. Copy it as-is into `_llm.py`. It
supports six providers out of the box — **anthropic**, **openai**, **rits**
(IBM Research Inference-to-Service), **watsonx**, **litellm**, and **ollama**.
Every other file imports it as `from _llm import create_llm`.

You can drop provider branches you don't need to keep dependencies tight, but
none of the branches import their provider's package at module load — each
import lives inside its own `if p == "..."` arm — so leaving unused branches
in place is **free** at runtime. The conservative move is to leave the file
intact and just install the providers you actually use (see §3).

A few details worth knowing before you copy:

- **RITS is built in.** It ships as a `RITSChatModel` class in this file, not
  a third-party package. It speaks the OpenAI-compat `/v1/chat/completions`
  wire format over `httpx` and supports `bind_tools(...)`. The class is large
  (~130 lines) but self-contained — no external dependency beyond `httpx`,
  which you already installed in §3.
- **Watsonx has a max-tokens footgun.** Pass `max_tokens=` and
  `temperature=` as **top-level** kwargs to `ChatWatsonx`, NOT inside
  `params={"max_new_tokens": ...}`. Recent `langchain_ibm` uses the
  OpenAI-style chat completions wire format and silently ignores the legacy
  `params=` field — watsonx then defaults to ~1024 output tokens and
  reasoning models can blow that budget on hidden reasoning before any
  visible content is produced. The factory below is already correct; the
  long comment in the code is there to keep someone from "fixing" it back.
- **Auto-detect order matters.** If the user has multiple keys set, the
  factory picks `rits → anthropic → openai → watsonx → litellm → ollama`.
  If you want a different default for your app, set `LLM_PROVIDER`
  explicitly rather than reordering `detect_provider()`.

```python
"""
Multi-provider LLM factory for cuga-agent demo apps.

Usage:
    from _llm import create_llm

    llm = create_llm()                          # auto-detect from env vars
    llm = create_llm(provider="rits")
    llm = create_llm(provider="watsonx", model="meta-llama/llama-4-scout-17b")
    llm = create_llm(provider="openai",  model="gpt-4o")

Supported providers and required env vars:
    openai    OPENAI_API_KEY
    rits      RITS_API_KEY
    watsonx   WATSONX_APIKEY + WATSONX_PROJECT_ID (or WATSONX_SPACE_ID)
    anthropic ANTHROPIC_API_KEY
    litellm   LITELLM_API_KEY + LITELLM_BASE_URL
    ollama    OLLAMA_BASE_URL (default: http://localhost:11434) — no key needed
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.chat_models import BaseChatModel as _BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs.chat_generation import ChatGeneration
from langchain_core.outputs.chat_result import ChatResult
from langchain.tools import BaseTool
from pydantic import Field, model_validator

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RITS — IBM Research Inference-to-Service
# ---------------------------------------------------------------------------

class RITSChatModel(_BaseChatModel):
    """LangChain-compatible chat model for the internal RITS inference service."""

    MODEL_NAME_MAPPING: Dict[str, str] = {
        "llama-3-3-70b-instruct": "meta-llama/llama-3-3-70b-instruct",
        "gpt-oss-120b": "openai/gpt-oss-120b",
        "qwen3-5-397b-a17b-fp8": "qwen/qwen3.5-397B-A17B-FP8",
        "mistral-large-3-675b-2512-fp4": "mistralai/Mistral-Large-3-675B-Instruct-2512-NVFP4",
    }

    model_name: str
    base_url: str
    api_key: str
    temperature: float = 0.0
    bound_tools: Optional[List[Dict[str, Any]]] = Field(default=None)

    @model_validator(mode="after")
    def _ping_endpoint(self) -> "RITSChatModel":
        url = f"{self.base_url}/{self.model_name}/ping"
        headers = {"RITS_API_KEY": self.api_key}
        try:
            resp = httpx.get(url, headers=headers, timeout=10.0)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"RITS ping failed for '{self.model_name}' (HTTP {e.response.status_code}). "
                f"Valid models: {list(self.MODEL_NAME_MAPPING.keys())}"
            )
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.warning(f"RITS ping failed for '{self.model_name}': {e} — continuing anyway")
        return self

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ChatResult:
        msgs = []
        for m in messages:
            if isinstance(m, SystemMessage):
                msgs.append({"role": "system", "content": m.content})
            elif isinstance(m, HumanMessage):
                msgs.append({"role": "user", "content": m.content})
            elif isinstance(m, AIMessage):
                msg_dict: Dict[str, Any] = {"role": "assistant", "content": m.content}
                if m.tool_calls:
                    msg_dict["tool_calls"] = m.additional_kwargs.get("tool_calls")
                if "reasoning" in m.additional_kwargs:
                    msg_dict["reasoning"] = m.additional_kwargs["reasoning"]
                msgs.append(msg_dict)
            elif isinstance(m, ToolMessage):
                msgs.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
            else:
                msgs.append({"role": "user", "content": m.content})

        url = f"{self.base_url}/{self.model_name}/v1/chat/completions"
        headers = {"RITS_API_KEY": self.api_key}
        payload_model = self.MODEL_NAME_MAPPING.get(self.model_name, self.model_name)

        payload: Dict[str, Any] = {
            "model": payload_model,
            "messages": msgs,
            "temperature": self.temperature,
            **kwargs,
        }
        if self.bound_tools:
            payload["tools"] = self.bound_tools

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload, timeout=180.0)
            if not resp.is_success:
                logger.error(
                    "[RITSChatModel] %s %s — response body: %s",
                    resp.status_code,
                    url,
                    resp.text[:2000],
                )
            resp.raise_for_status()
            data = resp.json()

        msg_data = data["choices"][0]["message"]
        content = msg_data.get("content") or ""
        additional_kwargs: Dict[str, Any] = {}
        if "tool_calls" in msg_data:
            additional_kwargs["tool_calls"] = msg_data["tool_calls"]
        if msg_data.get("reasoning"):
            additional_kwargs["reasoning"] = msg_data["reasoning"]

        return ChatResult(generations=[ChatGeneration(
            message=AIMessage(content=content, additional_kwargs=additional_kwargs)
        )])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            asyncio.get_running_loop()
            raise RuntimeError("Use ainvoke() inside an async context.")
        except RuntimeError:
            return asyncio.run(self._agenerate(messages, stop, **kwargs))

    @property
    def _llm_type(self) -> str:
        return "rits-openai-compat"

    def bind_tools(
        self,
        tools: Sequence[Union[Dict[str, Any], type, Callable, BaseTool]],
        **kwargs: Any,
    ) -> "RITSChatModel":
        from langchain_core.utils.function_calling import convert_to_openai_tool

        tool_defs = []
        for tool in tools:
            if hasattr(tool, "name") and hasattr(tool, "args"):
                tool_defs.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": {
                            "type": "object",
                            "properties": tool.args,
                            "required": list(tool.args.keys()),
                        },
                    },
                })
            elif isinstance(tool, dict):
                tool_defs.append(tool)
            else:
                tool_defs.append(convert_to_openai_tool(tool))

        return self.model_copy(update={"bound_tools": tool_defs, **kwargs})


# ---------------------------------------------------------------------------
# Provider auto-detection
# ---------------------------------------------------------------------------

def detect_provider() -> str:
    """Pick a provider based on which API key is set in the environment."""
    if os.getenv("RITS_API_KEY"):      return "rits"
    if os.getenv("ANTHROPIC_API_KEY"): return "anthropic"
    if os.getenv("OPENAI_API_KEY"):    return "openai"
    if os.getenv("WATSONX_APIKEY"):    return "watsonx"
    if os.getenv("LITELLM_API_KEY"):   return "litellm"
    return "ollama"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> BaseChatModel:
    """
    Create a BaseChatModel for the given provider.

    Args:
        provider: One of openai | rits | watsonx | anthropic | litellm | ollama.
                  Defaults to LLM_PROVIDER env var, or auto-detected from API keys.
        model:    Model name override. Defaults to LLM_MODEL env var, then
                  provider-specific defaults.

    Returns:
        Instantiated BaseChatModel ready to pass to CugaAgent(model=...).
    """
    p = (provider or os.getenv("LLM_PROVIDER") or detect_provider()).lower()
    m = model or os.getenv("LLM_MODEL") or None

    if p == "openai":
        from langchain_openai import ChatOpenAI
        resolved_key = os.getenv("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError("Set OPENAI_API_KEY for the openai provider.")
        return ChatOpenAI(
            model=m or "gpt-4.1",
            api_key=resolved_key,
            temperature=0,
        )

    elif p == "rits":
        resolved_key = os.getenv("RITS_API_KEY")
        if not resolved_key:
            raise ValueError("Set RITS_API_KEY for the rits provider.")
        base_url = os.getenv(
            "RITS_BASE_URL",
            "https://inference-3scale-apicast-production.apps.rits.fmaas.res.ibm.com",
        )
        return RITSChatModel(
            model_name=m or "llama-3-3-70b-instruct",
            base_url=base_url,
            api_key=resolved_key,
            temperature=0,
        )

    elif p == "watsonx":
        from langchain_ibm import ChatWatsonx
        resolved_key = os.getenv("WATSONX_APIKEY")
        if not resolved_key:
            raise ValueError("Set WATSONX_APIKEY for the watsonx provider.")
        project_id = os.getenv("WATSONX_PROJECT_ID") or os.getenv("WATSONX_SPACE_ID")
        if not project_id:
            raise ValueError("Set WATSONX_PROJECT_ID or WATSONX_SPACE_ID.")
        # NOTE: pass max_tokens / temperature as top-level kwargs, NOT inside
        # `params={"max_new_tokens": ...}`. Recent langchain_ibm uses the
        # OpenAI-style chat completions wire format which expects `max_tokens`,
        # and silently ignores the legacy `params={"max_new_tokens": ...}`
        # field — watsonx then defaults to ~1024 output tokens. With reasoning
        # models like gpt-oss-120b, the (private) reasoning_content alone can
        # consume the entire 1024-token budget and the wire response truncates
        # before any visible `content` is produced. Result: every search /
        # synthesis app returns "No answer found" because state.final_answer
        # ends up as an empty string. Don't reintroduce the params= form.
        return ChatWatsonx(
            model_id=m or "meta-llama/llama-4-maverick-17b-128e-instruct-fp8",
            url=os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com"),
            project_id=project_id,
            temperature=0,
            max_tokens=16000,
        )

    elif p == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError("pip install langchain-anthropic")
        resolved_key = os.getenv("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError("Set ANTHROPIC_API_KEY for the anthropic provider.")
        return ChatAnthropic(
            model=m or "claude-sonnet-4-6",
            api_key=resolved_key,
            temperature=0,
        )

    elif p == "litellm":
        from langchain_litellm import ChatLiteLLM
        return ChatLiteLLM(
            model=m or "gpt-4o",
            api_base=os.getenv("LITELLM_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
            api_key=os.getenv("LITELLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
            temperature=0,
        )

    elif p == "ollama":
        try:
            from langchain_ollama import ChatOllama
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            return ChatOllama(
                model=m or "llama3.1:8b",
                base_url=base_url,
                temperature=0,
                num_ctx=65536,
            )
        except ImportError:
            from langchain_openai import ChatOpenAI
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            return ChatOpenAI(
                model=m or "llama3.1:8b",
                base_url=f"{base_url.rstrip('/')}/v1",
                api_key="ollama",
                temperature=0,
            )

    else:
        raise ValueError(
            f"Unknown LLM provider: {p!r}. "
            "Choose one of: openai, rits, watsonx, anthropic, litellm, ollama"
        )
```

---

## 6. `_mcp_bridge.py` — copy verbatim

This is the bridge from your CUGA app to the hosted MCP servers. Copy it
as-is. It handles three real-world quirks that bite if you write your own
naive client:

1. **URL resolution** — CE / docker / localhost precedence + `MCP_<NAME>_URL`
   override, so your app code is the same in dev and prod.
2. **Tuple unwrap** — `langchain-mcp-adapters` returns `(content, artifact)`
   tuples; CUGA's executor expects a plain dict. We unwrap.
3. **args_schema shim** — CUGA calls `.schema()` / `.model_json_schema()`
   on each tool's args schema; the adapter exposes a plain dict. We wrap
   it so both calls succeed.

```python
"""
LangChain ↔ MCP bridge for CUGA apps.

Usage:
    from _mcp_bridge import load_tools
    tools = load_tools(["web", "knowledge", "geo", "finance"])
    # → list[StructuredTool] you can pass to CugaAgent(tools=...)

URL resolution (per server name):
    1. MCP_<NAME>_URL env var if set (explicit override; always wins)
    2. Code Engine public URL when CE_APP / CE_REVISION are set,
       or when CUGA_TARGET=ce
    3. http://mcp-<name>:<port>/mcp inside docker-compose
    4. http://localhost:<port>/mcp on bare metal
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import List

log = logging.getLogger(__name__)

# ── Hosted MCP servers ───────────────────────────────────────────────────
# Default ports for local / docker runs. Update if your private deployment
# uses different ports. The Code Engine path doesn't use these.
MCP_PORTS: dict[str, int] = {
    "web":            29100,
    "knowledge":      29101,
    "geo":            29102,
    "finance":        29103,
    "code":           29104,
    "local":          29105,
    "text":           29106,
    "invocable_apis": 29107,
}

_IN_DOCKER = Path("/.dockerenv").exists() or os.getenv("CUGA_IN_DOCKER") == "1"
_ON_CE = bool(
    os.getenv("CE_APP")
    or os.getenv("CE_REVISION")
    or (os.getenv("CUGA_TARGET", "") or "").lower() == "ce"
)

# Code Engine project hash + region. Override via env if you redeployed
# in a different CE project.
_CE_PROJECT_HASH_DEFAULT = "1gxwxi8kos9y"
_CE_REGION_DEFAULT       = "us-east"


def _ce_url(name: str) -> str:
    h = os.getenv("CE_SUBDOMAIN") or os.getenv("CE_PROJECT_HASH") or _CE_PROJECT_HASH_DEFAULT
    r = os.getenv("CE_REGION") or _CE_REGION_DEFAULT
    return f"https://cuga-apps-mcp-{name}.{h}.{r}.codeengine.appdomain.cloud/mcp"


def _default_url(name: str, port: int) -> str:
    if _ON_CE:    return _ce_url(name)
    if _IN_DOCKER: return f"http://mcp-{name}:{port}/mcp"
    return f"http://localhost:{port}/mcp"


def _resolved_urls(names: List[str]) -> dict[str, str]:
    out = {}
    for name in names:
        if name not in MCP_PORTS:
            raise ValueError(f"Unknown MCP server: {name!r}. Known: {list(MCP_PORTS)}")
        out[name] = os.getenv(f"MCP_{name.upper()}_URL") or _default_url(name, MCP_PORTS[name])
    return out


# ── (content, artifact) unwrap ───────────────────────────────────────────

def _unwrap(raw):
    """langchain-mcp-adapters wraps tools so direct `await tool(...)` returns
    a (content, artifact) tuple. CUGA's executor expects a normal value.
    Unwrap to the underlying `data` payload of the {ok, data} envelope."""
    import json as _json

    if not (isinstance(raw, tuple) and len(raw) == 2):
        return raw

    content_list, artifact = raw
    parsed = None

    if isinstance(artifact, dict) and "structured_content" in artifact:
        sc = artifact["structured_content"]
        if isinstance(sc, dict) and "result" in sc:
            r = sc["result"]
            if isinstance(r, str):
                try: parsed = _json.loads(r)
                except _json.JSONDecodeError: pass
            elif isinstance(r, (dict, list)):
                parsed = r

    if parsed is None and isinstance(content_list, list) and content_list:
        first = content_list[0]
        if isinstance(first, dict) and "text" in first:
            txt = first["text"]
            try: parsed = _json.loads(txt)
            except _json.JSONDecodeError: return txt

    if isinstance(parsed, dict) and "ok" in parsed:
        if not parsed["ok"]:
            err  = parsed.get("error", "tool error")
            code = parsed.get("code", "")
            return f"ERROR: {err}" + (f" (code={code})" if code else "")
        return parsed.get("data", parsed)

    return parsed if parsed is not None else raw


# ── args_schema shim ─────────────────────────────────────────────────────

class _ArgsSchemaShim(dict):
    """Make a plain JSON-Schema dict quack like a Pydantic model class so
    cuga's prompt builder can call .schema() / .model_json_schema()."""
    def schema(self) -> dict:                return dict(self)
    def model_json_schema(self) -> dict:     return dict(self)
    @property
    def model_fields(self) -> dict:          return self.get("properties", {}) or {}


_RETURN_HINT = (
    "\n\nReturn shape: this tool always returns the parsed `data` object "
    "from the cuga tool_result envelope. Use Python dict access on the "
    "documented field names (e.g. `result['results']`, `result['extract']`). "
    "Do NOT slice with `result[:N]` or index numerically — the top-level "
    "value is a dict, list, or scalar, never a tuple."
)


def _wrap(tool):
    """Patch a StructuredTool so it works with CUGA's executor + prompts."""
    import functools as _ft

    original = getattr(tool, "coroutine", None)
    if original is not None:
        @_ft.wraps(original)
        async def _wrapped(*args, **kwargs):
            return _unwrap(await original(*args, **kwargs))
        tool.coroutine = _wrapped

    schema = getattr(tool, "args_schema", None)
    if isinstance(schema, dict) and not isinstance(schema, _ArgsSchemaShim):
        try: tool.args_schema = _ArgsSchemaShim(schema)
        except Exception: pass

    desc = getattr(tool, "description", None)
    if isinstance(desc, str) and _RETURN_HINT not in desc:
        try: tool.description = desc + _RETURN_HINT
        except Exception: pass

    return tool


# ── Public API ───────────────────────────────────────────────────────────

def load_tools(servers: List[str]) -> list:
    """Connect to the named MCP servers and return their tools as
    LangChain StructuredTool instances ready to pass to CugaAgent(tools=…).

    Blocks until handshakes complete (or error out). Safe to call at app
    startup before uvicorn is running.
    """
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:
        raise ImportError(
            "Install langchain-mcp-adapters: pip install langchain-mcp-adapters"
        ) from exc

    urls = _resolved_urls(servers)
    connections = {
        name: {"transport": "streamable_http", "url": url}
        for name, url in urls.items()
    }
    log.info("MCP: %s", ", ".join(f"{n}={u}" for n, u in urls.items()))

    client = MultiServerMCPClient(connections)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None or not loop.is_running():
        tools = asyncio.run(client.get_tools())
    else:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            tools = ex.submit(lambda: asyncio.run(client.get_tools())).result()

    return [_wrap(t) for t in tools]
```

---

## 7. `main.py` — canonical template

This is the shape every CUGA app uses. Copy, replace placeholders, ship.
The annotated comments aren't decoration — each one names a thing that
breaks if you skip it.

```python
"""
<App Name> — <one-line tagline>

<2–4 sentences: what it does, what data it uses, why it's interesting.>

Run:
    python main.py
    python main.py --port 28999
    python main.py --provider anthropic

Then open: http://127.0.0.1:28999

Env vars:
    LLM_PROVIDER          anthropic | openai | rits | watsonx | litellm | ollama
    LLM_MODEL             model name override (provider-specific defaults if unset)
    ANTHROPIC_API_KEY     when LLM_PROVIDER=anthropic
    OPENAI_API_KEY        when LLM_PROVIDER=openai
    RITS_API_KEY          when LLM_PROVIDER=rits
    WATSONX_APIKEY + WATSONX_PROJECT_ID (or WATSONX_SPACE_ID)   when LLM_PROVIDER=watsonx
    LITELLM_API_KEY + LITELLM_BASE_URL                          when LLM_PROVIDER=litellm
    AGENT_SETTING_CONFIG  CUGA settings TOML (defaulted in make_agent)
    CUGA_TARGET           "ce" forces public Code Engine MCP URLs
    MCP_<NAME>_URL        per-server URL override
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

# ── Path bootstrap — REQUIRED ──────────────────────────────────────────
# Lets `from _llm import …` and `from _mcp_bridge import …` resolve
# whether the file is run from its own directory or imported as a module.
_DIR = Path(__file__).parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ui import _HTML


# ── Per-thread session store ───────────────────────────────────────────
# Anything the app needs to keep between turns goes here, keyed by
# thread_id (the UI generates a UUID once per browser session and reuses
# it on every /ask). Inline tools mutate this; the UI polls
# /session/<thread_id> and re-renders.
_sessions: dict[str, dict] = {}


def _get_session(thread_id: str) -> dict:
    if thread_id not in _sessions:
        _sessions[thread_id] = {
            # initialise every key that inline tools or the UI panel reads
            "items": [],
            "card":  None,
        }
    return _sessions[thread_id]


# ── Tools ──────────────────────────────────────────────────────────────
def _make_tools():
    """Compose MCP-loaded tools (optional) + inline @tool defs (optional)."""
    from langchain_core.tools import tool

    inline_tools = []

    @tool
    def remember_thing(thread_id: str, item: str) -> str:
        """Add an item to the session's tracked list.

        Args:
            thread_id: Current session/thread ID (always pass through).
            item:      Plain English item.
        """
        if not item:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": "item is empty"})
        s = _get_session(thread_id)
        if item not in s["items"]:
            s["items"].append(item)
        return json.dumps({"ok": True, "data": {"items": s["items"]}})

    @tool
    def save_card(thread_id: str, card_json: str) -> str:
        """Persist the structured card the right panel renders.

        Args:
            thread_id: Current session/thread ID.
            card_json: A JSON object — see the system prompt for required keys.
        """
        try:
            _get_session(thread_id)["card"] = json.loads(card_json)
            return json.dumps({"ok": True, "data": {"saved": True}})
        except json.JSONDecodeError as exc:
            return json.dumps({"ok": False, "code": "bad_input",
                               "error": f"invalid JSON: {exc}"})

    inline_tools = [remember_thing, save_card]

    # Pull anything you want from the hosted MCP servers. Comment this out
    # entirely if your app is inline-only.
    from _mcp_bridge import load_tools
    mcp_tools = load_tools(["web", "knowledge"])    # ← edit this list

    return [*mcp_tools, *inline_tools]


# ── System prompt ──────────────────────────────────────────────────────
_SYSTEM = """\
# <App Name>

<One sentence describing the agent's identity.>

## Listening rules
Whenever the user mentions <X>, call <inline state tool> with the relevant
field. Do this eagerly, even if they're just chatting.

## On request
1. Call <fast MCP tool> to ground the request.
2. Call <other MCP tools> in any order to gather material.
3. (OPTIONAL) Call <conditional MCP tool> only if <condition>.
4. Build the structured card (see save_card docstring for the exact shape).
5. Call save_card(thread_id=..., card_json=...).
6. Reply to the user with a short prose summary. Keep it to ~2 paragraphs —
   the right panel shows the structured detail.

## Rules
- Cite sources as markdown links.
- Never fabricate facts the tools didn't return. If a tool fails, say so
  and skip that section in the card.
- Do not compose the prompt dynamically per request — that's for me, not you.

## Thread ID
You will receive the thread_id in every user message (format
"[thread:<UUID>]"). Always extract it and pass it unchanged to every
inline tool that requires thread_id.
"""


# ── Agent factory ──────────────────────────────────────────────────────
def make_agent():
    from cuga.sdk import CugaAgent
    from _llm import create_llm

    # CUGA reads AGENT_SETTING_CONFIG to pick its internal settings TOML.
    # Default to a sensible per-provider TOML so the app boots without
    # needing the user to set it.
    # All six providers in the §5 factory speak an OpenAI-compatible chat
    # protocol (or are wrapped to look like one), so settings.openai.toml is
    # the right CUGA TOML for every branch. The dict-with-default form lets
    # you swap individual providers onto a different TOML later if you ever
    # need to.
    _provider_toml = {
        "anthropic": "settings.openai.toml",
        "openai":    "settings.openai.toml",
        "rits":      "settings.openai.toml",
        "watsonx":   "settings.openai.toml",
        "litellm":   "settings.openai.toml",
        "ollama":    "settings.openai.toml",
    }
    provider = (os.getenv("LLM_PROVIDER") or "").lower()
    os.environ.setdefault(
        "AGENT_SETTING_CONFIG",
        _provider_toml.get(provider, "settings.openai.toml"),
    )

    return CugaAgent(
        model=create_llm(
            provider=os.getenv("LLM_PROVIDER"),
            model=os.getenv("LLM_MODEL"),
        ),
        tools=_make_tools(),
        special_instructions=_SYSTEM,
        cuga_folder=str(_DIR / ".cuga"),
    )


# ── Request models ─────────────────────────────────────────────────────
class AskReq(BaseModel):
    question: str
    thread_id: str = ""


# ── HTTP server ────────────────────────────────────────────────────────
def _web(port: int) -> None:
    import uvicorn

    app = FastAPI(title="<App Name>", docs_url=None, redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    _agent = None

    def _get_agent():
        nonlocal _agent
        if _agent is None:
            log.info("Initialising CugaAgent…")
            _agent = make_agent()
            log.info("CugaAgent ready.")
        return _agent

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_HTML)

    @app.post("/ask")
    async def api_ask(req: AskReq):
        thread_id = req.thread_id or str(uuid.uuid4())
        # Smuggle thread_id into the input so inline tools can read it.
        augmented = f"[thread:{thread_id}] {req.question}"
        try:
            agent = _get_agent()
            result = await agent.invoke(augmented, thread_id=thread_id)
            return {"answer": str(result), "thread_id": thread_id}
        except Exception as exc:
            log.exception("Agent invocation failed")
            return JSONResponse(
                status_code=500,
                content={"answer": f"Error: {exc}", "thread_id": thread_id},
            )

    @app.get("/session/{thread_id}")
    async def api_session(thread_id: str):
        return _get_session(thread_id)

    @app.get("/health")
    async def health():
        return {"ok": True}

    print(f"\n  <App Name>  →  http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


# ── CLI entry point ────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="<App Name>")
    parser.add_argument("--port", type=int, default=28999)
    parser.add_argument(
        "--provider", "-p", default=None,
        choices=["anthropic", "openai", "rits", "watsonx", "litellm", "ollama"],
    )
    parser.add_argument("--model", "-m", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["LLM_MODEL"] = args.model

    _web(args.port)


if __name__ == "__main__":
    main()
```

### Why each detail matters

| Detail | Why |
|---|---|
| `_DIR` path bootstrap | Resolves `from _llm import …` and `from _mcp_bridge import …` regardless of CWD. |
| `from cuga.sdk import CugaAgent` | Canonical import. The legacy `from cuga import CugaAgent` works in some installs but is brittle. |
| `cuga_folder=str(_DIR / ".cuga")` | Per-app runtime state goes next to the app code, not in a shared scratch dir. |
| `AGENT_SETTING_CONFIG` defaulted in `make_agent()` | Without it, CUGA picks a TOML that may demand `OPENAI_API_KEY` and crashes if your provider is Anthropic. |
| `_get_agent()` lazily | Lets the server start fast even if `make_agent()` blocks on slow MCP handshakes — first `/ask` triggers the load. |
| `AskReq` with `question` + `thread_id=""` | Same shape every CUGA app uses; tests/clients hit any app the same way. |
| `[thread:<UUID>] question` augmentation | Smuggles the thread id into the agent's input so inline tools can read it via the `thread_id` arg in their signatures. |
| `result = await agent.invoke(augmented, thread_id=thread_id)` then `str(result)` | The CugaAgent return is a typed object; coerce to str to get the human reply. |
| Tools return `json.dumps({"ok": …, …})` strings | Same envelope as MCP. Inline tools can be promoted to MCP later with no callsite change. Raw dicts confuse the agent. |

---

## 8. `ui.py` — minimum viable UI

Export a single string `_HTML` — a fully self-contained dark-themed HTML
page. Vanilla JS only. Calls `POST /ask`, optionally polls
`GET /session/<thread_id>` for live structured state.

```python
"""HTML UI — exports _HTML, served at GET /."""

_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>App Name</title>
<style>
  * { box-sizing: border-box; }
  :root {
    --bg: #0f1117; --card: #1a1a2e; --border: #2d2d4a;
    --accent: #6366f1; --text: #e2e8f0; --muted: #94a3b8;
    --danger: #f87171;
  }
  body {
    margin: 0; height: 100vh; display: flex; flex-direction: column;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text);
  }
  header {
    padding: 16px 24px; background: var(--card);
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between;
    position: sticky; top: 0; z-index: 100;
  }
  header h1 { margin: 0; font-size: 18px; font-weight: 700; }
  header h1 span { color: var(--accent); }
  .badge {
    font-size: 12px; padding: 4px 10px; border-radius: 999px;
    background: rgba(99,102,241,0.18); color: #cbd5e1;
  }
  main {
    flex: 1; display: grid; grid-template-columns: 1fr 1fr;
    gap: 16px; padding: 16px; overflow: hidden;
  }
  .panel {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px; overflow-y: auto;
    display: flex; flex-direction: column;
  }
  .panel h2 {
    margin: 0 0 12px 0; font-size: 12px; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.06em;
  }
  .chips {
    display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px;
  }
  .chip {
    font-size: 12px; padding: 6px 10px; border-radius: 999px;
    background: var(--bg); border: 1px solid var(--border);
    color: #cbd5e1; cursor: pointer;
  }
  .chip:hover { border-color: var(--accent); color: #fff; }
  .messages { flex: 1; overflow-y: auto; margin-bottom: 12px;
              display: flex; flex-direction: column; gap: 8px; }
  .msg {
    padding: 10px 14px; border-radius: 10px; line-height: 1.55;
    white-space: pre-wrap; word-break: break-word; font-size: 13px;
    max-width: 100%;
  }
  .msg.user { background: var(--accent); color: #fff; align-self: flex-end; }
  .msg.agent { background: var(--bg); border: 1px solid var(--border);
               align-self: flex-start; }
  .msg.error { background: rgba(248,113,113,0.12); color: var(--danger);
               border: 1px solid var(--danger); align-self: flex-start; }
  .msg.thinking { color: var(--muted); font-style: italic;
                  border: 1px dashed var(--border); align-self: flex-start; }
  .input-row { display: flex; gap: 8px; }
  .input-row input {
    flex: 1; background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 9px 12px; color: var(--text);
    font-size: 14px; outline: none;
  }
  .input-row input:focus { border-color: var(--accent); }
  button {
    background: var(--accent); color: #fff; border: 0; border-radius: 8px;
    padding: 9px 18px; font-weight: 600; cursor: pointer; font-size: 14px;
  }
  button:disabled { opacity: 0.5; cursor: wait; }
  pre {
    margin: 0; white-space: pre-wrap; word-break: break-word;
    font: inherit; line-height: 1.5;
  }
  .empty { color: var(--muted); font-size: 13px;
           padding: 40px 0; text-align: center; }
</style>
</head>
<body>

<header>
  <h1>App <span>Name</span></h1>
  <span class="badge" id="status">ready</span>
</header>

<main>
  <section class="panel">
    <h2>Ask</h2>
    <div class="chips" id="examples">
      <span class="chip">Example prompt 1</span>
      <span class="chip">Example prompt 2</span>
      <span class="chip">Example prompt 3</span>
    </div>
    <div class="messages" id="messages"></div>
    <div class="input-row">
      <input id="q" placeholder="Ask the agent…"
        onkeydown="if(event.key==='Enter') ask()" />
      <button id="send" onclick="ask()">Send</button>
    </div>
  </section>

  <section class="panel">
    <h2>Result</h2>
    <div id="out"><div class="empty">No data yet — ask the agent something.</div></div>
  </section>
</main>

<script>
  // Stable per-browser-tab session id
  let SID = sessionStorage.getItem('app_session');
  if (!SID) {
    SID = (crypto.randomUUID
      ? crypto.randomUUID()
      : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
          const r = Math.random() * 16 | 0;
          return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        }));
    sessionStorage.setItem('app_session', SID);
  }

  const messagesEl = document.getElementById('messages');
  const q          = document.getElementById('q');
  const send       = document.getElementById('send');
  const status     = document.getElementById('status');
  const out        = document.getElementById('out');

  document.querySelectorAll('.chip').forEach(c =>
    c.addEventListener('click', () => { q.value = c.textContent; q.focus(); }));

  function addMsg(text, cls) {
    const div = document.createElement('div');
    div.className = 'msg ' + cls;
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // Render the structured card the agent saved via save_card. Adjust the
  // shape and renderer to match your app's card.
  function renderCard(card) {
    if (!card) return;
    out.innerHTML = '<pre>' + esc(JSON.stringify(card, null, 2)) + '</pre>';
  }

  let _lastHash = '';
  async function pollSession() {
    try {
      const r = await fetch('/session/' + SID);
      if (!r.ok) return;
      const data = await r.json();
      const hash = JSON.stringify(data);
      if (hash !== _lastHash) {
        _lastHash = hash;
        if (data.card) renderCard(data.card);
      }
    } catch (_) { /* ignore */ }
  }
  setInterval(pollSession, 10000);

  async function ask() {
    const question = q.value.trim();
    if (!question) return;
    q.value = '';
    send.disabled = true;
    status.textContent = 'thinking…';
    addMsg(question, 'user');
    const thinking = addMsg('Working on it…', 'thinking');
    try {
      const r = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, thread_id: SID }),
      });
      const j = await r.json();
      thinking.remove();
      if (!r.ok) addMsg('Error: ' + (j.answer || r.statusText), 'error');
      else { addMsg(j.answer || '(no answer)', 'agent'); pollSession(); }
    } catch (e) {
      thinking.remove();
      addMsg('Network error: ' + e.message, 'error');
    } finally {
      send.disabled = false;
      status.textContent = 'ready';
      q.focus();
    }
  }
</script>
</body>
</html>
"""
```

When your card is more interesting than a JSON dump, write a real renderer
in the `renderCard` function. Keep it vanilla JS, no frameworks, no
external CSS.

### UI conventions worth preserving

- Dark theme, two-panel layout: chat on the left, structured card on the
  right.
- Sticky header with a status badge.
- 6–9 example chips so first-time users have something to click.
- `sessionStorage` UUID for the thread id, reused across `/ask` calls.
- Poll `/session/<thread_id>` every 10 s, diff on a hash, repaint only on
  change. Don't poll if your app has no live state.

---

## 9. `requirements.txt`

```txt
# CUGA SDK installed separately (private — see prerequisites).

fastapi>=0.110
uvicorn[standard]>=0.27
pydantic>=2.0
httpx>=0.27

langchain>=0.3
langchain-core>=0.3
langchain-mcp-adapters>=0.1
mcp>=1.0

# Pick exactly the providers you support. The `_llm.py` factory imports
# these lazily inside each branch, so leaving extras commented out is fine —
# only uncomment the ones whose `LLM_PROVIDER=...` you actually plan to use.
langchain-anthropic>=0.2
# langchain-openai>=0.2
# langchain-ollama>=0.2
# langchain-ibm>=0.3            # for LLM_PROVIDER=watsonx
# langchain-litellm>=0.1        # for LLM_PROVIDER=litellm
# rits needs no extra package — RITSChatModel in _llm.py talks to the RITS
# REST endpoint directly via httpx (already pinned above).
```

---

## 10. The tool envelope — one rule

**Every** tool — inline or MCP — returns a JSON string in this shape:

```python
# Success
return json.dumps({"ok": True, "data": <whatever>})

# Failure
return json.dumps({"ok": False, "error": "human message", "code": "bad_input"})
# valid codes: bad_input | not_found | missing_key | upstream
```

This is also the contract MCP servers use, so your inline tool can be
promoted to a shared server later as a copy-paste move.

> **Anti-pattern.** Returning a raw `dict` from a `@tool` def. The agent
> silently mishandles it. Always `json.dumps(...)`.

---

## 11. The system prompt — workflow, not procedure

The system prompt is the agent's identity + workflow. Keep it **static**
(`_SYSTEM = """..."""` at module scope). Don't compose it per request.

A workable shape:

```text
# <App Name>
You are a <role>. Your job is to <one sentence>.

## Listening rules  (only if your app has session state)
Whenever the user mentions <X>, call <inline state tool>. Do this eagerly.

## On request
1. Call <fast tool> to ground.
2. Call <other tools> in any order:
   - <tool A> for <reason>
   - <tool B> for <reason>
   - OPTIONAL: <tool C> only if <condition>
3. Build the structured result.
4. Call save_<thing>(thread_id=..., <thing>_json=...).
5. Reply with a short prose summary. The right panel shows the detail.

## Rules
- Cite sources as markdown links.
- Never fabricate. If a tool fails, say so and skip that section.

## Thread ID
You will receive the thread_id in every user message (format
"[thread:<UUID>]"). Always extract it and pass it unchanged to every
inline tool that requires thread_id.
```

Put **JSON-shape requirements** in the `save_<thing>` tool's docstring,
not in the system prompt. The agent re-reads tool docstrings on every
call; the system prompt is one-shot.

---

## 12. Three flavors

### A. All inline (no MCP)

Skip `_mcp_bridge.py` entirely. Don't import `load_tools`. Just return
your inline `@tool` defs.

```python
def _make_tools():
    from langchain_core.tools import tool

    @tool
    def add_thing(thread_id: str, value: str) -> str:
        """..."""
        ...

    return [add_thing, ...]
```

Use this when the app's value comes entirely from in-memory state +
custom logic (e.g. a recipe planner that operates over a static lookup
table, a deck composer that mutates a slide tree).

### B. All MCP (no inline)

Use this when the app is a thin orchestrator over hosted capabilities and
has no session state worth tracking.

```python
def _make_tools():
    from _mcp_bridge import load_tools
    return load_tools(["web", "knowledge"])
```

Skip `/session/<thread_id>` and the right-panel polling — there's
nothing to render that the agent's prose doesn't already say.

### C. Mixed (most common)

```python
def _make_tools():
    from langchain_core.tools import tool
    from _mcp_bridge import load_tools

    mcp_tools = load_tools(["geo", "web", "knowledge", "finance"])

    @tool
    def set_focus(thread_id: str, topic: str) -> str: ...

    @tool
    def save_briefing(thread_id: str, briefing_json: str) -> str: ...

    return [*mcp_tools, set_focus, save_briefing]
```

Use the MCP servers for capability (search, geocode, weather, prices,
Wikipedia). Use inline tools for session memory + the structured card.

### Worked design example

Imagine you're building a "city briefing" app: user names a city, you
build a one-card briefing.

| Need | Source |
|---|---|
| Resolve city → lat/lon | MCP `geo.geocode` |
| Current weather | MCP `geo.get_weather` |
| Today's news | MCP `web.web_search` |
| Background blurb | MCP `knowledge.get_wikipedia_article` |
| Optional: nearby attractions | MCP `geo.search_attractions` |
| Optional: crypto sidebar | MCP `finance.get_crypto_price` |
| Remember which city is active | Inline `set_current_city` |
| Bias news search by user-set focus topics | Inline `add_focus_topic` |
| Render the card on the right panel | Inline `save_briefing` |

The inline state tools are tiny — each one mutates a session dict and
returns `{"ok": True, "data": ...}`. The MCP tools come "for free" via
`load_tools(["geo", "web", "knowledge", "finance"])`. The system prompt
ties it all together.

---

## 13. Run + verify

```bash
# 1. Install
pip install -r requirements.txt
pip install <cuga-sdk-source>

# 2. Configure
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-6
export ANTHROPIC_API_KEY=sk-ant-...
export CUGA_TARGET=ce      # use the public Code Engine MCP URLs

# 3. Run
python main.py --port 28999

# 4. Smoke-test
curl http://localhost:28999/health
# → {"ok": true}

curl -X POST http://localhost:28999/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"<example prompt>","thread_id":"smoke-1"}'
# → {"answer": "<real, non-empty agent response>", "thread_id": "smoke-1"}

curl http://localhost:28999/session/smoke-1
# → JSON of your session state (card may be set if the agent saved one)

open http://localhost:28999       # UI loads, dark theme, chat works
```

If `/health` is fine but `/ask` errors with an MCP timeout, confirm
`CUGA_TARGET=ce` is set, or set the URL explicitly:

```bash
export MCP_WEB_URL=https://cuga-apps-mcp-web.1gxwxi8kos9y.us-east.codeengine.appdomain.cloud/mcp
```

---

## 14. Anti-patterns

These break things. Don't.

- **Hardcoding a provider, model, or API key.** Read every credential
  from `os.getenv(...)`. The user picks at runtime.
- **Returning a raw `dict` from an inline `@tool` def.** Always `json.dumps(...)`.
- **Importing `from cuga import CugaAgent`.** Use `from cuga.sdk import CugaAgent`.
- **Composing the system prompt per request.** Pin it in `_SYSTEM` at
  module scope and tweak there.
- **Pre-validating env vars at boot.** A missing tool key shouldn't
  crash the app — let the matching tool return `missing_key`. The agent
  surfaces it; the app stays up with partial config.
- **Auto-refreshing the UI** for an app that has no live state. If
  there's nothing to repaint, don't poll.
- **Skipping the path bootstrap** in `main.py`. Without it,
  `_llm` / `_mcp_bridge` resolution breaks the moment your CWD changes.
- **Shipping a Dockerfile, compose file, tests, or React build inside
  the app folder.** Packaging belongs at the platform level.
- **Using `asyncio.get_event_loop()`** anywhere. Python 3.13 dropped its
  auto-create. For background tasks, schedule from inside
  `@app.on_event("startup")` via `asyncio.create_task(...)`.
- **Changing the CugaAgent constructor signature.** Stick to the four
  keyword args: `model`, `tools`, `special_instructions`, `cuga_folder`.
- **Promoting the user prompt to the system prompt.** They're different
  channels for a reason.

---

## 15. Definition of done

Before declaring the app finished:

- [ ] App folder is one of `<your_app>/{main.py, ui.py, _llm.py, _mcp_bridge.py, requirements.txt}` (+ optional helpers)
- [ ] No `__init__.py`, no Dockerfile, no tests, no React build inside the folder
- [ ] `from cuga.sdk import CugaAgent` (not `from cuga import …`)
- [ ] `_make_tools()` returns the union of MCP-loaded + inline `@tool` defs
- [ ] Every inline tool returns `json.dumps({"ok": ..., ...})` — never a raw dict
- [ ] Every inline tool documents its args in its docstring
- [ ] Inline tools that touch session state take `thread_id` as their first positional argument
- [ ] `_SYSTEM` is static (defined as a module-level string)
- [ ] `_SYSTEM` references each MCP tool by name and explains when to call it
- [ ] The `save_<thing>` tool's docstring documents the exact JSON shape the UI expects
- [ ] `POST /ask` accepts `{question, thread_id}` and returns `{answer}`
- [ ] `GET /health` returns `{"ok": true}`
- [ ] `GET /` returns the `_HTML` string
- [ ] If the app has live state, `GET /session/<thread_id>` returns it and the UI polls every 10 s
- [ ] UI is dark-themed, vanilla JS, single self-contained string
- [ ] No hardcoded provider / model / key anywhere in `main.py`
- [ ] README / runbook documents port, env vars, MCP servers used, the tool list, and 3+ example prompts
- [ ] Standalone bring-up works: `python main.py --port <port>` → `/health` ok, `/ask` returns a real response, UI loads, card populates

---

## 16. TL;DR

1. Make a folder. Put `_llm.py` (§5) and `_mcp_bridge.py` (§6) in it
   verbatim.
2. Decide your **card shape** (what the right panel renders) and your
   **MCP tool set** (which servers to `load_tools([...])`).
3. Write `main.py` from the §7 template. Define inline tools for your
   session state and a `save_<thing>` tool whose docstring spells out
   the card shape.
4. Write `_SYSTEM` (§11). Static, references each MCP tool by name.
5. Write `ui.py` from the §8 template. Vanilla JS, polls
   `/session/<thread_id>`, dark theme, two panels.
6. `pip install -r requirements.txt` + the CUGA SDK; export
   `LLM_PROVIDER`, `LLM_MODEL`, the matching API key, and
   `CUGA_TARGET=ce`.
7. `python main.py --port 28999`. Verify `/health`, `/ask`, `/`. Ship.
