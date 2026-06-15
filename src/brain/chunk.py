"""Chunking: 1600-char / 200-overlap; atomic-note aware (one small note = one chunk)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from brain.config import Config
from brain.frontmatter import parse as parse_fm


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    note_path: str
    text: str
    content_hash: str


def _make_id(note_path: str, index: int) -> str:
    raw = f"{note_path}::{index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32]


WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _find_link_boundaries(text: str) -> set[int]:
    """Return character positions that are inside a wikilink — avoid splitting there."""
    positions: set[int] = set()
    for m in WIKILINK_RE.finditer(text):
        positions.update(range(m.start(), m.end()))
    return positions


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """
    Split text into overlapping chunks of ~chunk_size chars.
    Tries not to split mid-wikilink.
    """
    if len(text) <= chunk_size:
        return [text]

    link_positions = _find_link_boundaries(text)
    chunks: list[str] = []
    start = 0
    n = len(text)

    while start < n:
        end = min(start + chunk_size, n)
        # Adjust end to avoid mid-wikilink split
        if end < n:
            candidate = end
            while candidate > start + chunk_overlap and candidate in link_positions:
                candidate -= 1
            end = candidate
        chunks.append(text[start:end])
        if end >= n:
            break
        start = end - chunk_overlap

    return chunks


def chunk_note(path: Path, cfg: Config) -> list[Chunk]:
    """Chunk a Markdown note, stripping frontmatter before chunking."""
    raw = path.read_text(encoding="utf-8")
    _, body = parse_fm(raw)

    note_path = str(path)
    texts = chunk_text(body.strip(), cfg.chunk_size, cfg.chunk_overlap)

    return [
        Chunk(
            chunk_id=_make_id(note_path, i),
            note_path=note_path,
            text=t,
            content_hash=_content_hash(t),
        )
        for i, t in enumerate(texts)
        if t.strip()
    ]
