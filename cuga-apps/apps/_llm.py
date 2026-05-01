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
