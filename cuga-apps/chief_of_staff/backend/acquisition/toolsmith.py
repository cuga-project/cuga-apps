"""Toolsmith — the LLM-driven acquisition agent.

This is the durable, swap-resistant agent in the system. It owns the
"agent gets a gap, decides how to fill it" loop. Cuga (the planner) is
swappable; Toolsmith stays.

Lifecycle:
  1. Cuga emits a structured ToolGap via the adapter.
  2. Orchestrator hands the gap to Toolsmith.propose().
  3. Toolsmith asks each registered Source for proposals, then asks an
     LLM to rank/filter the merged set. (LLM call is OPTIONAL — without
     a configured provider, falls back to highest-score-wins.)
  4. UI renders proposals; user picks one.
  5. Orchestrator calls Toolsmith.acquire(proposal) which:
        a. realize() — source-specific build/install
        b. probe() — autoresearch-pattern keep/discard gate
        c. emit a description of how to mount, returned to caller

The Toolsmith does NOT do the actual mounting (that's the orchestrator
calling the cuga adapter). It produces *what* to mount; the orchestrator
makes it real.

Configuration:
  TOOLSMITH_LLM_PROVIDER  defaults to "rits"
  TOOLSMITH_LLM_MODEL     defaults to "gpt-oss-120b"
  Override either via env. Falls back to None (deterministic) if the
  provider can't be initialized — the loop still works, just without
  LLM-based ranking.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .sources.base import Proposal, RealizedTool, Source

log = logging.getLogger(__name__)

# Make apps/_llm.py importable without modifying it.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parent.parent.parent.parent  # backend/acquisition/toolsmith.py → cuga-apps/
_APPS_DIR = _REPO_ROOT / "apps"
for p in (str(_APPS_DIR), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


_RANK_SYSTEM_PROMPT = """\
You are Toolsmith, the tool-acquisition agent. The user's planner agent
hit a tool gap. Multiple sources have proposed candidate tools. Your job
is to rank them: which one most directly fills the user's stated gap?

Return a JSON object: {"ranked_ids": ["id1", "id2", ...]} — best first.
Do NOT include candidates that don't fit. If none fit, return {"ranked_ids": []}.
Output JSON only, nothing else.
"""


@dataclass
class AcquisitionResult:
    """Outcome of Toolsmith.acquire(). Surfaced to the orchestrator and UI."""
    proposal_id: str
    success: bool
    realized: RealizedTool | None = None
    probe_result: dict | None = None
    reason: str = ""


def _try_build_llm():
    """Return a configured BaseChatModel or None if unavailable.

    Honors TOOLSMITH_LLM_PROVIDER / TOOLSMITH_LLM_MODEL env, defaults to
    rits + gpt-oss-120b. Failing here is *not* fatal — Toolsmith is
    designed to work with or without an LLM.
    """
    provider = os.environ.get("TOOLSMITH_LLM_PROVIDER", "rits")
    model = os.environ.get("TOOLSMITH_LLM_MODEL", "gpt-oss-120b")
    try:
        from _llm import create_llm  # type: ignore[import-not-found]
        llm = create_llm(provider=provider, model=model)
        log.info("Toolsmith LLM ready: provider=%s model=%s", provider, model)
        return llm
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "Toolsmith LLM unavailable (provider=%s model=%s): %s — "
            "falling back to deterministic ranking",
            provider, model, exc,
        )
        return None


class Toolsmith:
    """LLM-driven acquisition agent."""

    def __init__(self, sources: list[Source] | None = None, llm=None):
        if sources is None:
            from .sources.catalog_source import CatalogSource
            from .sources.openapi_source import OpenAPISource
            sources = [CatalogSource(), OpenAPISource()]
        self._sources = list(sources)
        # llm=False means "explicitly disabled, don't try". llm=None means
        # "build the default lazily". Anything else is an LLM instance.
        if llm is False:
            self._llm = None
        elif llm is None:
            self._llm = _try_build_llm()
        else:
            self._llm = llm

    @property
    def sources(self) -> list[Source]:
        return list(self._sources)

    @property
    def llm(self):
        return self._llm

    def get_source(self, name: str) -> Source | None:
        return next((s for s in self._sources if s.name == name), None)

    async def propose(self, gap: dict, top_k: int = 3) -> list[Proposal]:
        """Ask every source, merge, rank with LLM (or by score), return top_k."""
        all_proposals: list[Proposal] = []
        for source in self._sources:
            try:
                ps = await source.propose(gap, top_k=top_k)
            except Exception:  # noqa: BLE001
                log.exception("Source %r failed during propose", source.name)
                continue
            all_proposals.extend(ps)

        if not all_proposals:
            return []

        if self._llm is None:
            return sorted(all_proposals, key=lambda p: p.score, reverse=True)[:top_k]

        return await self._llm_rank(gap, all_proposals, top_k=top_k)

    async def _llm_rank(self, gap: dict, proposals: list[Proposal], top_k: int) -> list[Proposal]:
        """Use the LLM to pick the best fits. Falls back to score on parse failure."""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore[import-not-found]

            def _build_messages(system: str, user: str):
                return [SystemMessage(content=system), HumanMessage(content=user)]
        except ModuleNotFoundError:
            def _build_messages(system: str, user: str):
                return [{"role": "system", "content": system}, {"role": "user", "content": user}]

        index = {p.id: p for p in proposals}
        candidates_repr = [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "capabilities": p.capabilities,
                "source": p.source,
                "score": p.score,
            }
            for p in proposals
        ]
        prompt = (
            f"Gap: {json.dumps(gap)}\n\n"
            f"Candidates:\n{json.dumps(candidates_repr, indent=2)}\n\n"
            "Rank them best-first. Output JSON only."
        )
        messages = _build_messages(_RANK_SYSTEM_PROMPT, prompt)
        try:
            resp = await self._llm.ainvoke(messages)
            text = getattr(resp, "content", "")
            ranked_ids = _extract_ranked_ids(text)
        except Exception:  # noqa: BLE001
            log.exception("Toolsmith LLM rank failed — falling back to score order")
            return sorted(proposals, key=lambda p: p.score, reverse=True)[:top_k]

        ranked = [index[i] for i in ranked_ids if i in index]
        # Append anything the LLM dropped, in score order, so we still
        # surface candidates if the LLM was overzealous about pruning.
        seen = set(p.id for p in ranked)
        for p in sorted(proposals, key=lambda p: p.score, reverse=True):
            if p.id not in seen:
                ranked.append(p)
        return ranked[:top_k]

    async def acquire(
        self,
        proposal: Proposal,
        probe_runner=None,
    ) -> AcquisitionResult:
        """Realize the proposal, probe it, return the outcome.

        probe_runner is injected so tests can mock it without standing up the
        actual probe harness.
        """
        source = self.get_source(proposal.source)
        if source is None:
            return AcquisitionResult(
                proposal_id=proposal.id, success=False,
                reason=f"Unknown source: {proposal.source!r}",
            )
        try:
            realized = await source.realize(proposal)
        except Exception as exc:  # noqa: BLE001
            log.exception("Realize failed for %s", proposal.id)
            return AcquisitionResult(
                proposal_id=proposal.id, success=False,
                reason=f"realize failed: {exc}",
            )

        # Catalog tools (mcp_local) skip probing — they're already-running
        # local servers we trust. Generated/external tools must probe.
        if realized.mcp_server_name is not None:
            return AcquisitionResult(
                proposal_id=proposal.id, success=True, realized=realized,
                reason="catalog mount, no probe needed",
            )

        if probe_runner is None:
            from .probe import probe_realized_tool
            probe_runner = probe_realized_tool

        probe = await probe_runner(realized, llm=self._llm)
        if not probe.get("ok"):
            return AcquisitionResult(
                proposal_id=proposal.id, success=False, realized=realized,
                probe_result=probe, reason=f"probe failed: {probe.get('reason', 'unknown')}",
            )
        return AcquisitionResult(
            proposal_id=proposal.id, success=True, realized=realized,
            probe_result=probe, reason="probed and accepted",
        )


def _extract_ranked_ids(text: str) -> list[str]:
    """Pull a list of ids out of the LLM's response. Forgiving of
    pre/post chatter and code fences."""
    # Strip Markdown code fences if present.
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    # Find the first {...} block.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        return []
    try:
        obj = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return []
    ids = obj.get("ranked_ids", [])
    return [str(i) for i in ids if isinstance(i, str)]
