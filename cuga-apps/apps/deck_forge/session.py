"""
DeckForgeSession — per-request state container.

Holds the RAG knowledge base, the accumulating slide list,
the async progress queue, and output paths.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from rag import KnowledgeBase
from deck_writer import Slide


@dataclass
class DeckForgeSession:
    session_id: str
    directory: str
    topic: str
    output_dir: Path
    agent_type: str = "langgraph"   # "langgraph" | "cuga"

    # Populated during the agent run
    slides: list[Slide] = field(default_factory=list)
    status: str = "pending"           # pending | running | done | error
    result: dict | None = None        # set on success: {pptx, md, slide_count}
    error: str | None = None          # set on failure

    # Initialised in __post_init__
    queue: asyncio.Queue = field(init=False)
    kb: KnowledgeBase = field(init=False)

    def __post_init__(self) -> None:
        self.queue = asyncio.Queue()
        self.kb = KnowledgeBase(self.session_id)
        self.output_dir.mkdir(parents=True, exist_ok=True)
