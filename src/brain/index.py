"""SQLite FTS5 + sqlite-vec index: build, upsert-by-note, delete, rebuild (C2, C4)."""
from __future__ import annotations

import sqlite3
import struct
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import sqlite_vec

from brain.chunk import Chunk, chunk_note
from brain.config import Config
from brain.embed import embed_texts
from brain.frontmatter import read_chunk_ids, write_chunk_ids


def _db_path(cfg: Config) -> Path:
    return cfg.index_path / "brain.sqlite"


def _connect(cfg: Config) -> sqlite3.Connection:
    db_path = _db_path(cfg)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _init_schema(conn: sqlite3.Connection, embed_dim: int) -> None:
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id     TEXT PRIMARY KEY,
            note_path    TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            text         TEXT NOT NULL,
            chunk_index  INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_note ON chunks(note_path);

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            text,
            note_path UNINDEXED,
            chunk_id UNINDEXED,
            content='chunks',
            content_rowid='rowid'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
            chunk_id TEXT PRIMARY KEY,
            embedding float[{embed_dim}]
        );

        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid, text, note_path, chunk_id)
            VALUES (new.rowid, new.text, new.note_path, new.chunk_id);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text, note_path, chunk_id)
            VALUES ('delete', old.rowid, old.text, old.note_path, old.chunk_id);
        END;

        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts, rowid, text, note_path, chunk_id)
            VALUES ('delete', old.rowid, old.text, old.note_path, old.chunk_id);
            INSERT INTO chunks_fts(rowid, text, note_path, chunk_id)
            VALUES (new.rowid, new.text, new.note_path, new.chunk_id);
        END;
    """)
    conn.commit()


class Index:
    def __init__(self, conn: sqlite3.Connection, cfg: Config) -> None:
        self._conn = conn
        self._cfg = cfg

    def close(self) -> None:
        self._conn.close()

    def upsert_note(self, path: Path) -> list[str]:
        """Full-replace re-embed a note (C4). Returns new chunk IDs."""
        if not path.exists():
            self.delete_note(path)
            return []

        chunks = chunk_note(path, self._cfg)
        if not chunks:
            self.delete_note(path)
            return []

        texts = [c.text for c in chunks]
        embeddings = embed_texts(texts, self._cfg)

        self.delete_note(path)

        cur = self._conn.cursor()
        chunk_ids: list[str] = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            cur.execute(
                "INSERT INTO chunks(chunk_id, note_path, content_hash, text, chunk_index) "
                "VALUES (?, ?, ?, ?, ?)",
                (chunk.chunk_id, chunk.note_path, chunk.content_hash, chunk.text, i),
            )
            emb_bytes = struct.pack(f"{len(emb)}f", *emb)
            cur.execute(
                "INSERT INTO chunks_vec(chunk_id, embedding) VALUES (?, ?)",
                (chunk.chunk_id, emb_bytes),
            )
            chunk_ids.append(chunk.chunk_id)

        self._conn.commit()
        write_chunk_ids(path, chunk_ids)
        return chunk_ids

    def delete_note(self, path: Path) -> None:
        """Remove all chunks for a note (triggered on delete or before re-embed)."""
        note_path = str(path)
        cur = self._conn.cursor()
        cur.execute("SELECT chunk_id FROM chunks WHERE note_path = ?", (note_path,))
        old_ids = [row[0] for row in cur.fetchall()]
        for cid in old_ids:
            cur.execute("DELETE FROM chunks_vec WHERE chunk_id = ?", (cid,))
        cur.execute("DELETE FROM chunks WHERE note_path = ?", (note_path,))
        self._conn.commit()

    def note_chunk_count(self, path: Path) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM chunks WHERE note_path = ?", (str(path),))
        return cur.fetchone()[0]

    def total_chunk_count(self) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM chunks")
        return cur.fetchone()[0]

    def fts_search(self, query: str, k: int = 20) -> list[dict]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT chunk_id, note_path, text, rank "
            "FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, k),
        )
        return [dict(row) for row in cur.fetchall()]

    def vec_search(self, embedding: list[float], k: int = 20) -> list[dict]:
        emb_bytes = struct.pack(f"{len(embedding)}f", *embedding)
        cur = self._conn.cursor()
        cur.execute(
            "SELECT chunk_id, distance "
            "FROM chunks_vec WHERE embedding MATCH ? AND k = ?",
            (emb_bytes, k),
        )
        rows = cur.fetchall()
        results = []
        for row in rows:
            cid, dist = row[0], row[1]
            chunk = cur.execute(
                "SELECT note_path, text FROM chunks WHERE chunk_id = ?", (cid,)
            ).fetchone()
            if chunk:
                results.append({
                    "chunk_id": cid,
                    "note_path": chunk[0],
                    "text": chunk[1],
                    "distance": dist,
                })
        return results


@contextmanager
def open_index(cfg: Config) -> Generator[Index, None, None]:
    conn = _connect(cfg)
    _init_schema(conn, cfg.embed_dim)
    idx = Index(conn, cfg)
    try:
        yield idx
    finally:
        idx.close()


def reindex_file(idx: Index, cfg: Config, path: Path) -> list[str]:
    return idx.upsert_note(path)


def rebuild_index(cfg: Config) -> int:
    """Wipe .index/ and rebuild from all Markdown files in Brain/ + opted-in Notes/."""
    import shutil

    index_path = cfg.index_path
    if index_path.exists():
        shutil.rmtree(index_path)
    index_path.mkdir(parents=True)

    with open_index(cfg) as idx:
        total = 0
        for md_path in _all_indexable_paths(cfg):
            idx.upsert_note(md_path)
            total += 1
    return total


def _all_indexable_paths(cfg: Config) -> list[Path]:
    paths: list[Path] = []
    if cfg.brain_path.exists():
        paths.extend(p for p in cfg.brain_path.rglob("*.md") if not p.name.startswith("."))
    for rel in cfg.notes_read_paths:
        target = cfg.vault_path / rel
        if target.exists():
            paths.extend(p for p in target.rglob("*.md") if not p.name.startswith("."))
    return paths
