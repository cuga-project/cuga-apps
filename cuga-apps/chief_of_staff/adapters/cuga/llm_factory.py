"""LLM factory for the Chief of Staff cuga adapter.

Wraps `apps/_llm.create_llm()` to fix a real bug in `RITSChatModel`: its
`_agenerate` builds the request payload without `max_tokens`. RITS, when
no `max_tokens` is provided, computes `context_window − prompt_tokens`
server-side and returns 400 ("max_tokens must be at least 1, got -N")
whenever the prompt is large — which it always is once cuga adds its
system prompt + MCP tool descriptions.

We don't edit apps/_llm.py because the user's contract is read-only there.
Instead we build the LLM with `create_llm()` and patch `_agenerate` on the
resulting instance so the payload always carries an explicit `max_tokens`.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.language_models import BaseChatModel


_DEFAULT_MAX_TOKENS = int(os.environ.get("COS_LLM_MAX_TOKENS", "4096"))


def create_llm_for_adapter() -> BaseChatModel:
    """Build the LLM the same way `apps/_llm.create_llm` does, then patch
    out the missing `max_tokens` payload field for RITS."""
    from _llm import create_llm, RITSChatModel  # type: ignore[import-not-found]

    llm = create_llm()

    if isinstance(llm, RITSChatModel):
        _patch_rits_max_tokens(llm, _DEFAULT_MAX_TOKENS)

    return llm


def _patch_rits_max_tokens(llm: Any, default_max_tokens: int) -> None:
    """Monkey-patch the bound `_agenerate` so kwargs always include
    `max_tokens`. The original implementation forwards `**kwargs` directly
    into the payload it sends to RITS, so this is the surgical fix."""
    original = llm._agenerate

    async def _agenerate_with_max_tokens(messages, stop=None, **kwargs):
        kwargs.setdefault("max_tokens", default_max_tokens)
        return await original(messages, stop, **kwargs)

    llm._agenerate = _agenerate_with_max_tokens  # type: ignore[method-assign]
