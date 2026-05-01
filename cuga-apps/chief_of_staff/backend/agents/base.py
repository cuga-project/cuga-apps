"""AgentClient — the only contract the orchestrator knows about.

Implementations live alongside this file (cuga_client.py, etc.). The orchestrator
must never import a concrete client directly; it always goes through this Protocol.
That's what makes the planner backend swappable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class ToolGap:
    """A structured signal that the agent can't fulfill the request without
    a tool it doesn't have. The orchestrator passes this to the AcquisitionAgent.
    """
    capability: str
    inputs: list[str] = field(default_factory=list)
    expected_output: str = ""

    def to_json(self) -> dict:
        return {
            "capability": self.capability,
            "inputs": list(self.inputs),
            "expected_output": self.expected_output,
        }

    @classmethod
    def from_json(cls, data: dict) -> "ToolGap":
        return cls(
            capability=data.get("capability", ""),
            inputs=list(data.get("inputs", []) or []),
            expected_output=data.get("expected_output", ""),
        )


@dataclass
class AgentResult:
    answer: str
    error: Optional[str] = None
    gap: Optional[ToolGap] = None
    # Each entry is {name, server} where server is the MCP server
    # attribution (None for generated/extra tools). Adapter-shape; the
    # orchestrator passes it through to the UI without interpretation.
    tools_used: list[dict] = field(default_factory=list)


class AgentClient(Protocol):
    """Out-of-process planner. cuga_client.py is the first implementation."""

    async def plan_and_execute(
        self,
        user_message: str,
        thread_id: str = "default",
    ) -> AgentResult:
        ...

    async def reload(
        self,
        servers: list[str],
        extra_tools: list[dict] | None = None,
        secrets: dict[str, dict[str, str]] | None = None,
        disabled_tools: list[str] | None = None,
    ) -> dict:
        """Tell the agent to rebuild itself with a new tool set + per-tool
        secrets. Used by the orchestrator after an acquisition or vault change.

        extra_tools = generated tool specs (phase 3.5+).
        secrets   = {artifact_id: {key: value}} for tools whose code requires
                    auth values at call time (phase 3.6).
        disabled_tools = tool names to mask from the agent so the user can
                    force gap-emission by removing e.g. web_search.
        """
        ...

    async def health(self) -> bool:
        ...

    async def aclose(self) -> None:
        ...
