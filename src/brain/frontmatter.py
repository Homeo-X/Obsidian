"""Parse and emit YAML frontmatter; chunk-ID bookkeeping in note files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

FENCE = "---"
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
CHUNK_ID_KEY = "chunk_ids"


def parse(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body_text). Empty dict if no frontmatter."""
    m = FM_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    body = text[m.end():]
    return fm, body


def emit(fm: dict[str, Any], body: str) -> str:
    """Reconstruct a file with YAML frontmatter prepended to body."""
    if not fm:
        return body
    header = yaml.dump(fm, default_flow_style=False, sort_keys=False).rstrip("\n")
    return f"{FENCE}\n{header}\n{FENCE}\n{body}"


def read_chunk_ids(path: Path) -> list[str]:
    """Read the chunk_ids list from a note's frontmatter."""
    if not path.exists():
        return []
    fm, _ = parse(path.read_text(encoding="utf-8"))
    ids = fm.get(CHUNK_ID_KEY, [])
    return ids if isinstance(ids, list) else []


def write_chunk_ids(path: Path, chunk_ids: list[str]) -> None:
    """Update (or add) the chunk_ids field in a note's frontmatter in place."""
    from brain.vault import atomic_write

    text = path.read_text(encoding="utf-8")
    fm, body = parse(text)
    if chunk_ids:
        fm[CHUNK_ID_KEY] = chunk_ids
    else:
        fm.pop(CHUNK_ID_KEY, None)
    atomic_write(path, emit(fm, body))
