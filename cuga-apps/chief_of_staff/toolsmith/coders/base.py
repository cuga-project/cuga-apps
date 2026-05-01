"""Coder abstraction — the swappable code-generation specialist.

Toolsmith calls a Coder when it concludes "I need actual code now."
The Coder's job is bounded: spec → Python source. It doesn't know about
the registry, the vault, the catalog, or any other system context.

Implementations:
  - LLMCoder      : generic LangChain BaseChatModel + a code-gen prompt
                    (default: RITS gpt-oss-120b)
  - ClaudeCoder   : Anthropic Sonnet 4.6 via the official SDK
                    (better at code, costs more)

Adding a new Coder is a new file under toolsmith/coders/ that implements
the Protocol. Pick via TOOLSMITH_CODER env var: "gpt_oss" | "claude".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class CodeGenSpec:
    """Everything the Coder needs to produce code, no more."""
    name: str                              # snake_case function name
    description: str                       # one-line, used in the docstring + LangChain tool desc
    parameters_schema: dict                # {param_name: {"type": "string", "required": True, ...}}
    sample_input: dict                     # known-good input for the probe call
    expected_output_shape: str = ""        # free-form hint, e.g. "JSON object with name and capital"
    api_base_url: Optional[str] = None     # for HTTP-wrapping tools
    api_method: str = "GET"
    api_path: Optional[str] = None         # may include {path_param}
    requires_secrets: list[str] = field(default_factory=list)
    extra_context: str = ""                # caller can dump anything else useful for codegen
    # Phase 3.6: auth scheme for the API. Coder uses this to wire the
    # secret into the right place (header/query/etc.).
    auth: Optional[dict] = None            # {type, secret_key, header?, param?, prefix?}


@dataclass
class CodeGenResult:
    code: str                              # the generated Python source (one async def)
    notes: str = ""                        # Coder's commentary; useful for diagnostics


@dataclass
class ProbeFailure:
    """Feedback for revise_tool — Toolsmith hands this back when probe fails."""
    reason: str
    status_code: Optional[int] = None
    response_excerpt: str = ""
    judge_feedback: str = ""


class CoderClient(Protocol):
    """Minimal contract every Coder must satisfy."""

    name: str

    async def generate_tool(self, spec: CodeGenSpec) -> CodeGenResult:
        """Produce a single async function called `<spec.name>` that takes the
        declared parameters and returns the expected output shape. The function
        body should use httpx for HTTP calls and stdlib only for everything else.
        """
        ...

    async def revise_tool(self, prior: CodeGenResult, feedback: ProbeFailure) -> CodeGenResult:
        """Fix the prior code so the probe passes. Same contract on output."""
        ...


def coder_from_env() -> CoderClient:
    """Build the Coder selected by TOOLSMITH_CODER env (default 'gpt_oss')."""
    import os
    name = os.environ.get("TOOLSMITH_CODER", "gpt_oss").lower()
    if name == "claude":
        from .claude_coder import ClaudeCoder
        return ClaudeCoder()
    if name in ("gpt_oss", "llm", "default"):
        from .llm_coder import LLMCoder
        return LLMCoder()
    raise ValueError(f"Unknown TOOLSMITH_CODER: {name!r}. Use 'gpt_oss' or 'claude'.")
