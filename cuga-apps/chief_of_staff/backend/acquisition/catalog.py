"""Catalog loader + simple text-overlap matcher.

Phase 2 keeps this dumb on purpose: no LLM call, no embeddings — just token-set
overlap between the gap description and each entry's capabilities + name.
The catalog is small (5–10 entries) and curated, so this is plenty.
Phase 3 will swap in an LLM matcher when the catalog grows past human curation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "catalog.yaml"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


@dataclass
class CatalogEntry:
    id: str
    name: str
    description: str
    capabilities: list[str]
    kind: str
    target: str
    auth: list[str]


@dataclass
class Proposal:
    entry: CatalogEntry
    score: float


class Catalog:
    def __init__(self, path: Path | str = DEFAULT_CATALOG_PATH):
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        self.entries: list[CatalogEntry] = [
            CatalogEntry(
                id=e["id"],
                name=e["name"],
                description=e["description"],
                capabilities=list(e.get("capabilities", [])),
                kind=e["kind"],
                target=e["target"],
                auth=list(e.get("auth", [])),
            )
            for e in data.get("entries", [])
        ]
        log.info("Loaded %d catalog entries from %s", len(self.entries), path)

    def by_id(self, entry_id: str) -> CatalogEntry | None:
        return next((e for e in self.entries if e.id == entry_id), None)

    def match(self, gap: dict[str, Any], top_k: int = 3) -> list[Proposal]:
        """Score every entry against the gap and return the top_k > 0."""
        gap_tokens = _tokenize(
            " ".join([
                gap.get("capability", ""),
                gap.get("expected_output", ""),
                " ".join(gap.get("inputs", []) or []),
            ])
        )
        if not gap_tokens:
            return []

        scored: list[Proposal] = []
        for entry in self.entries:
            entry_tokens = _tokenize(
                " ".join([entry.name, entry.description] + entry.capabilities)
            )
            overlap = gap_tokens & entry_tokens
            if not overlap:
                continue
            # Jaccard-ish: overlap normalized by the gap size, so a gap with
            # one strong matching word still scores high.
            score = len(overlap) / max(len(gap_tokens), 1)
            scored.append(Proposal(entry=entry, score=score))

        scored.sort(key=lambda p: p.score, reverse=True)
        return scored[:top_k]
