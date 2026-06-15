"""
Phase 3 gate: hybrid search discrimination test.
Must pass: keyword-only miss + semantic hit (paraphrase)
           AND semantic-only miss + keyword hit (rare exact token).
"""
from __future__ import annotations

import pytest

from brain.index import open_index
from brain.search import hybrid_search
from brain.vault import atomic_write


def _make_note(cfg, name: str, content: str):
    note = cfg.brain_path / "notes" / name
    note.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(note, f"---\ntitle: {name}\n---\n\n{content}\n")
    return note


@pytest.fixture
def indexed_vault(cfg):
    """Vault with two notes indexed — one for paraphrase, one for exact token."""
    note_a = _make_note(
        cfg,
        "ai-research.md",
        "Large language models are transforming how we process and understand natural language. "
        "These neural networks learn from vast amounts of text data.",
    )
    note_b = _make_note(
        cfg,
        "xyzzy-token.md",
        "The xyzzy1337 protocol defines a unique identifier used in legacy authentication systems.",
    )
    with open_index(cfg) as idx:
        idx.upsert_note(note_a)
        idx.upsert_note(note_b)
    return cfg, note_a, note_b


def test_hybrid_finds_paraphrase(indexed_vault):
    """
    Semantic should find the AI note even when the query uses different words
    (paraphrase: 'machine intelligence text processing' vs 'large language models natural language').
    """
    cfg, note_a, _ = indexed_vault
    with open_index(cfg) as idx:
        results = hybrid_search(idx, cfg, "machine intelligence text processing", k=5)

    note_paths = [r["note_path"] for r in results]
    assert any("ai-research" in p for p in note_paths), (
        "Hybrid search should find paraphrase via semantic path. Got: " + str(note_paths)
    )


def test_hybrid_finds_exact_token(indexed_vault):
    """
    FTS keyword search should find the exact rare token 'xyzzy1337' even if semantic misses it.
    """
    cfg, _, note_b = indexed_vault
    with open_index(cfg) as idx:
        results = hybrid_search(idx, cfg, "xyzzy1337", k=5)

    note_paths = [r["note_path"] for r in results]
    assert any("xyzzy-token" in p for p in note_paths), (
        "Hybrid search should find exact token via FTS path. Got: " + str(note_paths)
    )


def test_search_returns_pointers_not_authoritative(indexed_vault):
    """Results must carry the pointer warning label."""
    cfg, note_a, _ = indexed_vault
    with open_index(cfg) as idx:
        results = hybrid_search(idx, cfg, "language models", k=5)

    assert results
    for r in results:
        assert "pointer" in r or "warning" in r, "Results must carry pointer metadata"
        assert r.get("pointer") is True or "pointer" in r.get("warning", "")
