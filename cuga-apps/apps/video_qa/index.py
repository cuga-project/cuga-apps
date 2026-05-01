"""
Vector index for video transcript segments using ChromaDB.

Dependencies:
    pip install chromadb sentence-transformers
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_INDEX_DIR = Path(__file__).parent / ".cache" / "chroma"
_INDEX_DIR.mkdir(parents=True, exist_ok=True)

_client = None


def _get_client():
    global _client
    if _client is None:
        import chromadb
        _client = chromadb.PersistentClient(path=str(_INDEX_DIR))
    return _client


def _collection_name(video_path: str | Path) -> str:
    h    = hashlib.sha256(str(Path(video_path).resolve()).encode()).hexdigest()[:12]
    stem = Path(video_path).stem[:20].replace(" ", "_").replace("-", "_")
    return f"vqa_{stem}_{h}"


def is_indexed(video_path: str | Path) -> bool:
    name = _collection_name(video_path)
    try:
        col = _get_client().get_collection(name)
        return col.count() > 0
    except Exception:
        return False


def index_segments(
    video_path: str | Path,
    segments: list[dict[str, Any]],
    force: bool = False,
) -> int:
    name   = _collection_name(video_path)
    client = _get_client()

    if force:
        try:
            client.delete_collection(name)
        except Exception:
            pass

    try:
        from chromadb.utils import embedding_functions
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    except Exception:
        ef = None

    col = client.get_or_create_collection(name=name, embedding_function=ef)

    if col.count() > 0 and not force:
        log.info("Collection '%s' already has %d segments — skipping index", name, col.count())
        return col.count()

    ids       = [str(i) for i in range(len(segments))]
    documents = [s["text"] for s in segments]
    metadatas = [
        {"start": s["start"], "end": s["end"],
         "start_fmt": s["start_fmt"], "end_fmt": s["end_fmt"], "index": i}
        for i, s in enumerate(segments)
    ]

    batch = 512
    for start in range(0, len(ids), batch):
        col.add(
            ids=ids[start:start+batch],
            documents=documents[start:start+batch],
            metadatas=metadatas[start:start+batch],
        )

    log.info("Indexed %d segments into collection '%s'", len(segments), name)
    return len(segments)


def search(
    video_path: str | Path,
    query: str,
    n_results: int = 6,
) -> list[dict[str, Any]]:
    name = _collection_name(video_path)
    try:
        from chromadb.utils import embedding_functions
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    except Exception:
        ef = None

    try:
        col = _get_client().get_collection(name=name, embedding_function=ef)
    except Exception:
        log.warning("Collection '%s' not found — video may not be indexed yet", name)
        return []

    actual_n = min(n_results, col.count())
    if actual_n == 0:
        return []

    results   = col.query(query_texts=[query], n_results=actual_n)
    docs      = results["documents"][0]
    metas     = results["metadatas"][0]
    distances = results["distances"][0]

    hits = []
    for doc, meta, dist in zip(docs, metas, distances):
        hits.append({
            "text":      doc,
            "start":     meta["start"],
            "end":       meta["end"],
            "start_fmt": meta["start_fmt"],
            "end_fmt":   meta["end_fmt"],
            "distance":  round(dist, 4),
        })

    hits.sort(key=lambda h: h["start"])
    return hits


def get_at_time(
    video_path: str | Path,
    seconds: float,
    all_segments: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for seg in all_segments:
        if seg["start"] <= seconds <= seg["end"]:
            return seg
    if not all_segments:
        return None
    return min(all_segments, key=lambda s: abs(s["start"] - seconds))


def delete_index(video_path: str | Path) -> None:
    name = _collection_name(video_path)
    try:
        _get_client().delete_collection(name)
        log.info("Deleted collection '%s'", name)
    except Exception:
        pass
