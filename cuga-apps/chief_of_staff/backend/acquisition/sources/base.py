"""Source plugin interface.

A Source is anything that can produce candidate tools for a given gap.
Phase 3 ships two: catalog (curated MCP servers) and openapi (generated
from public OpenAPI specs). Phase 4 will add browser-based sources.

The Toolsmith agent dispatches gaps to sources and ranks the merged
proposals; sources are pluggable so adding e.g. a Smithery integration is
just a new file.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional, Protocol


@dataclass
class Proposal:
    """A candidate tool the Toolsmith found, ready to show in the consent UI."""
    id: str                         # source-namespaced, e.g. "catalog:geo" or "openapi:restcountries"
    name: str
    description: str
    capabilities: list[str]
    source: str                     # "catalog" | "openapi" | (future) "browser"
    score: float                    # 0..1, higher = better match
    auth: list[str] = field(default_factory=list)
    # Source-specific payload that approve() will need. Opaque to the
    # orchestrator/UI; only the originating source reads it.
    spec: dict = field(default_factory=dict)
    # Probe is None until probed. Populated by the probe harness.
    probe_result: Optional[dict] = None

    def to_json(self) -> dict:
        return asdict(self)


class Source(Protocol):
    """A pluggable acquisition source.

    Implementations live under acquisition/sources/. They share no state;
    the Toolsmith calls each one independently and merges results.
    """

    name: str

    async def propose(self, gap: dict, top_k: int = 3) -> list[Proposal]:
        """Given a gap, return up to top_k ranked proposals."""
        ...

    async def realize(self, proposal: Proposal) -> "RealizedTool":
        """Actually build / install / connect the tool. Called only after
        the user approves. May fail; caller should handle exceptions."""
        ...


@dataclass
class RealizedTool:
    """Output of Source.realize — what gets handed to the probe + adapter."""
    proposal_id: str
    # If the tool is an MCP server name (string in apps/_ports.py), this is set.
    mcp_server_name: Optional[str] = None
    # If the tool is dynamically generated (phase 3+), these are populated:
    tool_name: Optional[str] = None      # display name (e.g. "get_country")
    description: Optional[str] = None
    invoke_url: Optional[str] = None     # the upstream URL the tool calls
    invoke_method: str = "GET"
    invoke_params: dict = field(default_factory=dict)  # JSON-schema-ish
    sample_input: dict = field(default_factory=dict)   # what the probe should call with
    requires_secrets: list[str] = field(default_factory=list)
