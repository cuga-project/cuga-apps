"""AcquisitionAgent — the single seam that turns a ToolGap into proposals.

Phase 2: only the catalog source is wired up. Phases 3 and 4 will add OpenAPI
generation and browser fallback as additional sources, all funneling through
this class so the orchestrator stays oblivious.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .catalog import Catalog, Proposal


@dataclass
class ProposalView:
    """Serializable shape returned to the frontend."""
    id: str
    name: str
    description: str
    capabilities: list[str]
    kind: str
    auth: list[str]
    score: float
    source: str = "catalog"

    @classmethod
    def from_proposal(cls, p: Proposal) -> "ProposalView":
        e = p.entry
        return cls(
            id=e.id,
            name=e.name,
            description=e.description,
            capabilities=list(e.capabilities),
            kind=e.kind,
            auth=list(e.auth),
            score=round(p.score, 3),
        )

    def to_json(self) -> dict:
        return asdict(self)


class AcquisitionAgent:
    def __init__(self, catalog: Catalog | None = None):
        self._catalog = catalog or Catalog()

    @property
    def catalog(self) -> Catalog:
        return self._catalog

    def propose(self, gap: dict, top_k: int = 3) -> list[ProposalView]:
        """Given a gap dict from the cuga adapter, return ranked proposals."""
        return [ProposalView.from_proposal(p) for p in self._catalog.match(gap, top_k=top_k)]
