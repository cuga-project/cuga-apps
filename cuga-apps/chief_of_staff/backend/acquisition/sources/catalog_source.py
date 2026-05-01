"""Catalog source — phase 2 logic, refactored as a Source plugin.

No behavior change. The matcher and YAML are unchanged; this file just
adapts the existing API to the new Source/Proposal interface.
"""

from __future__ import annotations

from .. import catalog as _catalog
from .base import Proposal, RealizedTool


class CatalogSource:
    name = "catalog"

    def __init__(self, catalog: _catalog.Catalog | None = None):
        self._catalog = catalog or _catalog.Catalog()

    @property
    def catalog(self) -> _catalog.Catalog:
        return self._catalog

    async def propose(self, gap: dict, top_k: int = 3) -> list[Proposal]:
        scored = self._catalog.match(gap, top_k=top_k)
        return [
            Proposal(
                id=f"catalog:{p.entry.id}",
                name=p.entry.name,
                description=p.entry.description,
                capabilities=list(p.entry.capabilities),
                source=self.name,
                score=round(p.score, 3),
                auth=list(p.entry.auth),
                spec={"catalog_id": p.entry.id, "kind": p.entry.kind, "target": p.entry.target},
            )
            for p in scored
        ]

    async def realize(self, proposal: Proposal) -> RealizedTool:
        catalog_id = proposal.spec["catalog_id"]
        entry = self._catalog.by_id(catalog_id)
        if entry is None:
            raise ValueError(f"Catalog entry {catalog_id!r} not found")
        if entry.kind != "mcp_local":
            raise NotImplementedError(f"Catalog kind {entry.kind!r} not supported by catalog source")
        return RealizedTool(
            proposal_id=proposal.id,
            mcp_server_name=entry.target,
        )
