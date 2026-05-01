"""
LLM provider factory for the Travel Planner demo.

Supports: rits, watsonx, anthropic, openai, ollama, litellm

Usage:
    from llm import create_llm
    model = create_llm()          # reads LLM_PROVIDER + LLM_MODEL from env
    agent = CugaAgent(model=model, tools=[...])
"""

import asyncio
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs.chat_generation import ChatGeneration
from langchain_core.outputs.chat_result import ChatResult
from langchain.tools import BaseTool
from pydantic import Field, model_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RITS — IBM Research Inference-to-Service
# ---------------------------------------------------------------------------

class RITSChatModel(BaseChatModel):
    """LangChain-compatible chat model backed by the internal IBM RITS inference service."""

    # Short endpoint name → full payload model name
    MODEL_NAME_MAPPING: Dict[str, str] = {
        "llama-3-3-70b-instruct":              "meta-llama/llama-3-3-70b-instruct",
        "gpt-oss-120b":                        "openai/gpt-oss-120b",
        "qwen3-5-397b-a17b-fp8":               "qwen/qwen3.5-397B-A17B-FP8",
        "mistral-large-3-675b-2512-fp4":       "mistralai/Mistral-Large-3-675B-Instruct-2512-NVFP4",
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
            logger.error(
                f"RITS ping failed for model '{self.model_name}' "
                f"(HTTP {e.response.status_code}). "
                f"Valid model names: {list(self.MODEL_NAME_MAPPING.keys())}. URL: {url}"
            )
            raise
        except httpx.TimeoutException:
            logger.error(
                f"RITS ping timed out for '{self.model_name}' at {url}. "
                "Check that the model backend is deployed."
            )
            raise
        except httpx.RequestError as e:
            logger.error(
                f"RITS ping failed for '{self.model_name}': cannot connect to {url}. "
                f"Check RITS_BASE_URL. Error: {e}"
            )
            raise
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
                msg_dict: Dict[str, Any] = {"role": "assistant", "content": m.content or ""}

                # Normalise tool_calls: LangChain may store them in either
                # m.tool_calls (native) or m.additional_kwargs["tool_calls"]
                # (raw OpenAI format). We need the raw OpenAI format for RITS.
                raw_tc = m.additional_kwargs.get("tool_calls")
                if not raw_tc and m.tool_calls:
                    raw_tc = [
                        {
                            "id": tc.get("id", f"call_{i}"),
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"]),
                            },
                        }
                        for i, tc in enumerate(m.tool_calls)
                    ]
                if raw_tc:
                    msg_dict["tool_calls"] = raw_tc

                if m.additional_kwargs.get("reasoning"):
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
            resp = await client.post(url, headers=headers, json=payload, timeout=60.0)
            resp.raise_for_status()
            data = resp.json()

        msg_data = data["choices"][0]["message"]
        content = msg_data.get("content") or ""
        additional_kwargs: Dict[str, Any] = {}
        if "tool_calls" in msg_data:
            additional_kwargs["tool_calls"] = msg_data["tool_calls"]
        if msg_data.get("reasoning"):
            additional_kwargs["reasoning"] = msg_data["reasoning"]

        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content=content, additional_kwargs=additional_kwargs
        ))])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            asyncio.get_running_loop()
            raise RuntimeError("Use ainvoke() / agenerate() from async context.")
        except RuntimeError:
            return asyncio.run(self._agenerate(messages, stop, **kwargs))

    @property
    def _llm_type(self) -> str:
        return "rits-openai-compat"

    def bind_tools(
        self,
        tools: Sequence[Union[Dict[str, Any], type, Callable, BaseTool]],
        **kwargs,
    ) -> "RITSChatModel":
        from langchain_core.utils.function_calling import convert_to_openai_tool

        tool_defs = []
        for t in tools:
            if hasattr(t, "name") and hasattr(t, "args"):
                tool_defs.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": {
                            "type": "object",
                            "properties": t.args,
                            "required": list(t.args.keys()),
                        },
                    },
                })
            else:
                try:
                    tool_defs.append(convert_to_openai_tool(t))
                except Exception as e:
                    if isinstance(t, dict):
                        tool_defs.append(t)
                    else:
                        raise ValueError(f"Cannot convert tool {t} to OpenAI format: {e}")

        return self.model_copy(update={"bound_tools": tool_defs, **kwargs})


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

RITS_BASE_URL = (
    "https://inference-3scale-apicast-production.apps.rits.fmaas.res.ibm.com"
)


def create_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.0,
    rits_api_key: Optional[str] = None,
    rits_base_url: Optional[str] = None,
) -> BaseChatModel:
    """
    Instantiate a LangChain-compatible LLM from environment variables.

    Provider is read from LLM_PROVIDER env var (default: "anthropic").
    Model is read from LLM_MODEL env var; falls back to sensible defaults.

    Supported providers:
      rits       — IBM RITS internal inference (requires RITS_API_KEY)
      watsonx    — IBM watsonx.ai (requires WATSONX_APIKEY + WATSONX_PROJECT_ID or WATSONX_SPACE_ID)
      anthropic  — Anthropic Claude (requires ANTHROPIC_API_KEY)
      openai     — OpenAI (requires OPENAI_API_KEY)
      ollama     — Local Ollama (no key required)
      litellm    — LiteLLM proxy (requires LITELLM_API_KEY + LITELLM_BASE_URL)
    """
    provider = provider or os.environ.get("LLM_PROVIDER", "anthropic")
    model = model or os.environ.get("LLM_MODEL")

    # ── RITS ────────────────────────────────────────────────────────────────
    if provider == "rits":
        api_key = rits_api_key or os.environ.get("RITS_API_KEY")
        if not api_key:
            raise ValueError("LLM_PROVIDER=rits requires RITS_API_KEY to be set.")
        base_url = rits_base_url or os.environ.get("RITS_BASE_URL", RITS_BASE_URL)
        return RITSChatModel(
            model_name=model or "llama-3-3-70b-instruct",
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
        )

    # ── watsonx ─────────────────────────────────────────────────────────────
    elif provider == "watsonx":
        try:
            from langchain_ibm import ChatWatsonx
        except ImportError:
            raise ImportError("Install langchain-ibm: pip install langchain-ibm")

        api_key = os.environ.get("WATSONX_APIKEY")
        if not api_key:
            raise ValueError("LLM_PROVIDER=watsonx requires WATSONX_APIKEY to be set.")

        project_id = os.environ.get("WATSONX_PROJECT_ID")
        space_id = os.environ.get("WATSONX_SPACE_ID")
        if not project_id and not space_id:
            raise ValueError(
                "LLM_PROVIDER=watsonx requires WATSONX_PROJECT_ID or WATSONX_SPACE_ID."
            )

        # NOTE: pass temperature / max_tokens as top-level kwargs, NOT inside
        # `params={"max_new_tokens": ...}`. Recent langchain_ibm uses the
        # OpenAI-style chat completions wire format which expects `max_tokens`,
        # and silently ignores the legacy `params={"max_new_tokens": ...}`
        # field — watsonx then defaults to ~1024 output tokens. With reasoning
        # models like gpt-oss-120b that's not enough budget for the reasoning
        # channel plus the visible answer, so `content` comes back empty and
        # the UI shows nothing. Mirror of the same fix in apps/_llm.py.
        url = os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
        params: Dict[str, Any] = {
            "model_id": model or "meta-llama/llama-3-3-70b-instruct",
            "url": url,
            "apikey": api_key,
            "temperature": temperature,
            "max_tokens": 16000,
        }
        if project_id:
            params["project_id"] = project_id
        else:
            params["space_id"] = space_id
        return ChatWatsonx(**params)

    # ── Anthropic ────────────────────────────────────────────────────────────
    elif provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError("Install langchain-anthropic: pip install langchain-anthropic")

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY to be set.")
        return ChatAnthropic(
            model=model or "claude-3-5-sonnet-20241022",
            temperature=temperature,
            api_key=api_key,
        )

    # ── OpenAI ───────────────────────────────────────────────────────────────
    elif provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ImportError("Install langchain-openai: pip install langchain-openai")

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY to be set.")
        return ChatOpenAI(model=model or "gpt-4o", temperature=temperature, api_key=api_key)

    # ── Ollama ───────────────────────────────────────────────────────────────
    elif provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            raise ImportError("Install langchain-ollama: pip install langchain-ollama")

        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        return ChatOllama(
            model=model or "llama3.1:8b",
            base_url=base_url,
            temperature=temperature,
            num_ctx=65536,
        )

    # ── LiteLLM ──────────────────────────────────────────────────────────────
    elif provider == "litellm":
        try:
            from langchain_litellm import ChatLiteLLM
        except ImportError:
            raise ImportError("Install langchain-litellm: pip install langchain-litellm")

        params: Dict[str, Any] = {
            "model": model or "GCP/gemini-2.0-flash",
            "temperature": temperature,
            "custom_llm_provider": "openai",
        }
        api_key = os.environ.get("LITELLM_API_KEY")
        if api_key:
            params["api_key"] = api_key
        base_url = os.environ.get("LITELLM_BASE_URL")
        if base_url:
            params["api_base"] = base_url
        return ChatLiteLLM(**params)

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER='{provider}'. "
            "Choose from: rits, watsonx, anthropic, openai, ollama, litellm"
        )
