"""
Chromadb-backed knowledge base for a single DeckForge session.

Each session gets an in-memory ChromaDB collection.  Text is chunked into
~400-word windows with 80-word overlap, then embedded with sentence-transformers
(all-MiniLM-L6-v2, 384-dim).  Retrieval returns the top-k chunks with source
attribution and a normalised similarity score.
"""
from __future__ import annotations

import hashlib
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer  # type: ignore

_EMBED_MODEL = "all-MiniLM-L6-v2"
_CHUNK_WORDS = 400
_CHUNK_OVERLAP = 80

# Module-level singleton — loaded lazily, shared across sessions
_embed_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(_EMBED_MODEL)
    return _embed_model


def _chunk(text: str, size: int = _CHUNK_WORDS, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping word-based windows."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i : i + size]))
        if i + size >= len(words):
            break
        i += size - overlap
    return chunks


class KnowledgeBase:
    """Per-session ephemeral vector store."""

    def __init__(self, session_id: str) -> None:
        import uuid as _uuid
        self._session_id = session_id
        self._client = chromadb.EphemeralClient()
        # Use a UUID-suffixed name so retries never collide with prior collections
        # (EphemeralClient is a process-level singleton in chromadb 1.x)
        col_name = f"df_{_uuid.uuid4().hex[:16]}"
        self._col = self._client.create_collection(col_name)
        self._model = _get_model()
        self._total_chunks = 0
        self._sources: list[str] = []  # track which files were indexed

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def add_document(self, filepath: str, text: str) -> int:
        """Chunk, embed, and store text.  Returns number of chunks added."""
        chunks = _chunk(text)
        if not chunks:
            return 0

        prefix = hashlib.md5(filepath.encode()).hexdigest()[:8]
        ids = [f"{prefix}_c{i}" for i in range(len(chunks))]
        metas: list[dict[str, Any]] = [
            {"source": filepath, "chunk_index": i} for i in range(len(chunks))
        ]

        embeddings = self._model.encode(chunks).tolist()
        self._col.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metas)
        self._total_chunks += len(chunks)

        if filepath not in self._sources:
            self._sources.append(filepath)

        return len(chunks)

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        """Return up to n_results relevant chunks with source and score."""
        if self._total_chunks == 0:
            return []
        n = min(n_results, self._total_chunks)
        q_emb = self._model.encode([query]).tolist()
        result = self._col.query(query_embeddings=q_emb, n_results=n)
        out: list[dict] = []
        for doc, meta, dist in zip(
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            out.append(
                {
                    "text": doc,
                    "source": meta["source"],
                    "score": round(1.0 - float(dist), 4),
                }
            )
        return out

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @property
    def chunk_count(self) -> int:
        return self._total_chunks

    @property
    def sources(self) -> list[str]:
        return list(self._sources)
