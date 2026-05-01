"""ClaudeCoder — uses Anthropic's Claude Sonnet for code generation.

Empirically the best model for "wrap an HTTP API in clean Python" right
now. Costs more per token than gpt-oss but typically gets the code
right on the first try, so the total spend on a probe-revise loop is
often lower.

Set ANTHROPIC_API_KEY in apps/.env. Override the model via
TOOLSMITH_CODER_MODEL (default: claude-sonnet-4-6).
"""

from __future__ import annotations

import logging
import os

from .base import CodeGenResult, CodeGenSpec, CoderClient, ProbeFailure
from .llm_coder import _SYSTEM_PROMPT, _REVISE_PROMPT, _format_spec_prompt, _extract_code

log = logging.getLogger(__name__)


class ClaudeCoder(CoderClient):
    name = "claude"

    def __init__(self, client=None, model: str | None = None):
        self._model = model or os.environ.get("TOOLSMITH_CODER_MODEL", "claude-sonnet-4-6")
        self._client = client or _build_client()

    async def generate_tool(self, spec: CodeGenSpec) -> CodeGenResult:
        text = await self._invoke(_SYSTEM_PROMPT, _format_spec_prompt(spec))
        return CodeGenResult(code=_extract_code(text), notes="")

    async def revise_tool(self, prior: CodeGenResult, feedback: ProbeFailure) -> CodeGenResult:
        revise_msg = _REVISE_PROMPT.format(
            reason=feedback.reason,
            status=feedback.status_code,
            excerpt=feedback.response_excerpt[:1000],
            judge=feedback.judge_feedback or "(none)",
        ) + "\n\nPrior code:\n```python\n" + prior.code + "\n```"
        text = await self._invoke(_SYSTEM_PROMPT, revise_msg)
        return CodeGenResult(code=_extract_code(text), notes="revision")

    async def _invoke(self, system: str, user: str) -> str:
        if self._client is None:
            raise RuntimeError("ClaudeCoder has no anthropic client configured")
        msg = await self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Anthropic returns content blocks; concatenate the text ones.
        parts = []
        for block in getattr(msg, "content", []):
            text = getattr(block, "text", None)
            if text is not None:
                parts.append(text)
        return "".join(parts)


def _build_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("ANTHROPIC_API_KEY not set — ClaudeCoder will fail until configured")
        return None
    try:
        from anthropic import AsyncAnthropic  # type: ignore[import-not-found]
        return AsyncAnthropic(api_key=api_key)
    except ImportError:
        log.warning("anthropic package not installed; install via requirements.txt")
        return None
