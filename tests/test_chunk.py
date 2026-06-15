"""Phase 3 gate: chunking correctness."""
from __future__ import annotations

from pathlib import Path

import pytest

from brain.chunk import chunk_note, chunk_text


def test_short_text_is_one_chunk():
    chunks = chunk_text("short text", chunk_size=1600, chunk_overlap=200)
    assert len(chunks) == 1
    assert chunks[0] == "short text"


def test_long_text_splits():
    text = "a" * 3000
    chunks = chunk_text(text, chunk_size=1600, chunk_overlap=200)
    assert len(chunks) > 1


def test_overlap_preserved():
    text = "x" * 1800
    chunks = chunk_text(text, chunk_size=1600, chunk_overlap=200)
    assert len(chunks) == 2
    # Second chunk should start within overlap of first chunk's end
    overlap_content = chunks[0][-200:]
    assert chunks[1].startswith(overlap_content)


def test_wikilink_not_split(tmp_path):
    """Chunk boundaries should not fall inside [[wikilinks]] if possible."""
    link = "[[Some Long Note Title Here]]"
    prefix = "a" * 1590
    text = prefix + link + " more text"
    chunks = chunk_text(text, chunk_size=1600, chunk_overlap=200)
    # The wikilink should appear intact in at least one chunk
    all_text = " ".join(chunks)
    assert link in all_text


def test_chunk_note_produces_stable_ids(cfg, tmp_path):
    """Same note content → same chunk IDs."""
    note = cfg.brain_path / "notes" / "stable.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("---\ntitle: test\n---\n\nsome content here\n")

    chunks1 = chunk_note(note, cfg)
    chunks2 = chunk_note(note, cfg)

    ids1 = [c.chunk_id for c in chunks1]
    ids2 = [c.chunk_id for c in chunks2]
    assert ids1 == ids2


def test_chunk_note_strips_frontmatter(cfg):
    """Frontmatter should not appear in chunk text."""
    note = cfg.brain_path / "notes" / "fm.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("---\ntitle: test\ncreated: 2026-01-01\n---\n\nactual body content\n")

    chunks = chunk_note(note, cfg)
    assert chunks
    for c in chunks:
        assert "title: test" not in c.text
        assert "actual body content" in c.text
