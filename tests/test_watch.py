"""
Phase 4 gate: watcher → save note → search finds it WITHOUT manual reindex.
Deleting the note removes it from search results.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from brain.index import open_index
from brain.search import hybrid_search
from brain.vault import atomic_write
from brain.watch import _DebounceHandler


def _write_note(cfg, name: str, content: str) -> Path:
    note = cfg.brain_path / "notes" / name
    note.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(note, f"---\ntitle: {name}\n---\n\n{content}\n")
    return note


@pytest.fixture
def watcher(cfg):
    """Start a short-debounce watcher; yield cfg; stop on teardown."""
    from watchdog.observers import Observer

    # 100ms debounce is sufficient for tests; avoids 500ms wait per operation
    handler = _DebounceHandler(cfg, debounce_ms=100)
    observer = Observer()
    observer.schedule(handler, str(cfg.brain_path), recursive=True)
    observer.start()

    yield cfg

    observer.stop()
    observer.join(timeout=5)


def _wait_for_index(cfg, note_path: Path, expect_present: bool, timeout: float = 5.0) -> bool:
    """Poll until the note is (or isn't) in the index. Returns True if condition met."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with open_index(cfg) as idx:
            count = idx.note_chunk_count(note_path)
        if expect_present and count > 0:
            return True
        if not expect_present and count == 0:
            return True
        time.sleep(0.05)
    return False


def test_watcher_indexes_new_note_without_manual_reindex(watcher):
    """
    GATE 4: watcher running → write a note → semantic query returns it.
    No brain.reindex call anywhere in this test.
    """
    cfg = watcher
    note = _write_note(
        cfg,
        "watcher-gate4.md",
        "photosynthesis converts sunlight into chemical energy stored in glucose molecules",
    )

    indexed = _wait_for_index(cfg, note, expect_present=True, timeout=5.0)
    assert indexed, "Watcher should have auto-indexed the note within the debounce window"

    # Semantic query with paraphrase (not the exact words) — no manual reindex called
    with open_index(cfg) as idx:
        results = hybrid_search(idx, cfg, "plants use solar energy to produce sugar", k=5)

    note_paths = [r["note_path"] for r in results]
    assert any("watcher-gate4" in p for p in note_paths), (
        f"Semantic search should find the note via watcher-triggered index. Got: {note_paths}"
    )


def test_watcher_removes_deleted_note(watcher):
    """GATE 4: deleting a note removes it from search results (no manual reindex)."""
    cfg = watcher
    note = _write_note(
        cfg,
        "watcher-delete.md",
        "mitochondria are the powerhouse of the cell and produce ATP via oxidative phosphorylation",
    )

    indexed = _wait_for_index(cfg, note, expect_present=True, timeout=5.0)
    assert indexed, "Note should be indexed by watcher before deletion test"

    note.unlink()

    removed = _wait_for_index(cfg, note, expect_present=False, timeout=5.0)
    assert removed, "Deleted note's chunks should be removed from index by watcher"

    with open_index(cfg) as idx:
        results = hybrid_search(idx, cfg, "mitochondria ATP powerhouse", k=5)

    note_paths = [r["note_path"] for r in results]
    assert not any("watcher-delete" in p for p in note_paths), (
        "Deleted note should not appear in search after watcher removal"
    )


def test_watcher_reindexes_modified_note(watcher):
    """Modifying a note via watcher replaces old content with new (C4)."""
    cfg = watcher
    note = _write_note(
        cfg,
        "watcher-modify.md",
        "original content about ancient roman history and the republic era",
    )

    _wait_for_index(cfg, note, expect_present=True, timeout=5.0)

    # Overwrite with completely different content
    atomic_write(
        note,
        "---\ntitle: watcher-modify\n---\n\n"
        "updated content about deep sea creatures and bioluminescent fish in the ocean\n",
    )

    # Wait for re-index of the updated content
    time.sleep(0.5)

    with open_index(cfg) as idx:
        cur = idx._conn.cursor()
        cur.execute("SELECT text FROM chunks WHERE note_path=?", (str(note),))
        stored_texts = [row[0] for row in cur.fetchall()]

    assert any("bioluminescent" in t for t in stored_texts), (
        "Updated content should be in index after watcher re-index"
    )
    assert not any("roman history" in t for t in stored_texts), (
        "Old content must not remain after full-replace re-index (C4)"
    )
