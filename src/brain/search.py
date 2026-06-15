"""Hybrid retrieval: FTS keyword ∪ vector semantic, merged via reciprocal-rank fusion."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain.config import Config
    from brain.index import Index

# Reciprocal rank fusion constant (k=60 is standard)
RRF_K = 60


def _rrf_score(rank: int) -> float:
    return 1.0 / (RRF_K + rank)


def hybrid_search(idx: "Index", cfg: "Config", query: str, k: int = 5) -> list[dict]:
    """
    Hybrid search: FTS ∪ vector, merged with reciprocal-rank fusion.
    Returns note-level results with score, note_path, snippet.
    The index is for DISCOVERY only — treat results as pointers, read the live file before acting.
    """
    from brain.embed import embed_query

    fts_results = _safe_fts(idx, query, k * 4)
    query_emb = embed_query(query, cfg)
    vec_results = idx.vec_search(query_emb, k * 4) if query_emb else []

    scores: dict[str, float] = {}
    snippets: dict[str, str] = {}

    for rank, r in enumerate(fts_results):
        cid = r["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + _rrf_score(rank)
        snippets[cid] = (r.get("text") or "")[:300]

    for rank, r in enumerate(vec_results):
        cid = r["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + _rrf_score(rank)
        if cid not in snippets:
            snippets[cid] = (r.get("text") or "")[:300]

    note_scores: dict[str, float] = {}
    note_snippets: dict[str, str] = {}

    all_chunks = {r["chunk_id"]: r for r in fts_results}
    all_chunks.update({r["chunk_id"]: r for r in vec_results})

    for cid, score in scores.items():
        note_path = all_chunks[cid].get("note_path", "")
        if note_path not in note_scores or score > note_scores[note_path]:
            note_scores[note_path] = score
            note_snippets[note_path] = snippets.get(cid, "")

    ranked = sorted(note_scores.items(), key=lambda x: x[1], reverse=True)[:k]

    return [
        {
            "note_path": note_path,
            "score": score,
            "snippet": note_snippets.get(note_path, ""),
            "pointer": True,
            "warning": "pointer — read file before acting",
        }
        for note_path, score in ranked
    ]


def _safe_fts(idx: "Index", query: str, k: int) -> list[dict]:
    try:
        return idx.fts_search(query, k)
    except Exception:
        return []
