"""Phase 3 gate: index upsert, delete, no orphans/dupes, rebuild."""
from __future__ import annotations

from pathlib import Path

import pytest

from brain.index import open_index, rebuild_index, reindex_file
from brain.vault import atomic_write


def _make_note(cfg, name: str, content: str) -> Path:
    note = cfg.brain_path / "notes" / name
    note.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(note, f"---\ntitle: {name}\n---\n\n{content}\n")
    return note


def test_index_single_note(cfg):
    note = _make_note(cfg, "alpha.md", "alpha content about quantum computing")
    with open_index(cfg) as idx:
        chunk_ids = idx.upsert_note(note)
        assert len(chunk_ids) >= 1
        assert idx.note_chunk_count(note) == len(chunk_ids)


def test_edit_changes_only_that_notes_chunks(cfg):
    note_a = _make_note(cfg, "note-a.md", "content about machine learning models")
    note_b = _make_note(cfg, "note-b.md", "content about database design patterns")

    with open_index(cfg) as idx:
        ids_a_v1 = idx.upsert_note(note_a)
        ids_b = idx.upsert_note(note_b)

        # Edit note_a — content changes but path+position-based IDs may stay same
        new_content = "---\ntitle: note-a\n---\n\nentirely different content now\n"
        atomic_write(note_a, new_content)
        ids_a_v2 = idx.upsert_note(note_a)

        # note_b should be completely unchanged
        assert idx.note_chunk_count(note_b) == len(ids_b)

        # note_a's stored text must reflect new content (re-embed happened)
        cur = idx._conn.cursor()
        cur.execute("SELECT text FROM chunks WHERE note_path=?", (str(note_a),))
        stored_texts = [row[0] for row in cur.fetchall()]
        assert any("entirely different" in t for t in stored_texts), (
            "Updated content must be stored after upsert"
        )
        assert not any("machine learning" in t for t in stored_texts), (
            "Old content must not remain after full-replace upsert (C4)"
        )


def test_shrink_prunes_surplus_chunks(cfg):
    """Shrinking a note must remove surplus chunks with no orphans."""
    long_content = "word " * 400  # ~2000 chars → likely 2 chunks
    note = _make_note(cfg, "shrink.md", long_content)

    with open_index(cfg) as idx:
        ids_long = idx.upsert_note(note)

        # Shrink note to tiny content
        atomic_write(note, "---\ntitle: shrink\n---\n\nshort now\n")
        ids_short = idx.upsert_note(note)

        assert len(ids_short) <= len(ids_long)
        # Old ids must be gone
        for old_id in ids_long:
            if old_id not in ids_short:
                # Verify it's not in the DB
                count = idx._conn.execute(
                    "SELECT COUNT(*) FROM chunks WHERE chunk_id=?", (old_id,)
                ).fetchone()[0]
                assert count == 0, f"Orphan chunk {old_id} found after shrink"


def test_delete_removes_all_chunks(cfg):
    note = _make_note(cfg, "delete-me.md", "content to be deleted from index")
    with open_index(cfg) as idx:
        idx.upsert_note(note)
        assert idx.note_chunk_count(note) > 0
        idx.delete_note(note)
        assert idx.note_chunk_count(note) == 0


def test_rebuild_reproduces_results(cfg):
    """reindex --all should produce identical chunk count after a full wipe+rebuild."""
    note_a = _make_note(cfg, "rebuild-a.md", "rebuild test content alpha gamma delta")
    note_b = _make_note(cfg, "rebuild-b.md", "rebuild test content beta epsilon zeta")

    # Full rebuild indexes ALL Markdown in Brain/ (including seeded _index.md from init_vault)
    total = rebuild_index(cfg)
    with open_index(cfg) as idx:
        count_first = idx.total_chunk_count()

    # Rebuild again — must produce identical count (idempotent)
    rebuild_index(cfg)
    with open_index(cfg) as idx:
        count_second = idx.total_chunk_count()

    assert count_first == count_second, "Rebuild must be idempotent"
    # Both target notes must be present after rebuild
    with open_index(cfg) as idx:
        assert idx.note_chunk_count(note_a) > 0
        assert idx.note_chunk_count(note_b) > 0
