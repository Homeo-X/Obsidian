"""MCP server exposing search, save, recall_preferences (Phase 5)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp import FastMCP

if TYPE_CHECKING:
    from brain.config import Config

mcp = FastMCP("brain")

_cfg: "Config | None" = None


def _get_cfg() -> "Config":
    if _cfg is None:
        raise RuntimeError("MCP server not initialized — call run_server(cfg) first.")
    return _cfg


@mcp.tool()
def search(query: str, k: int = 5) -> list[dict]:
    """
    Hybrid semantic + keyword search over the vault.
    Returns note pointers + snippets for DISCOVERY only.
    Always read the live file before quoting or acting on a result.
    """
    from brain.index import open_index
    from brain.search import hybrid_search

    cfg = _get_cfg()
    with open_index(cfg) as idx:
        return hybrid_search(idx, cfg, query, k=k)


@mcp.tool()
def save(content: str, note_type: str = "note", title: str | None = None, links: list[str] | None = None) -> dict:
    """
    Capture and save an atomic note under Brain/notes/. Honors the write contract (C1).
    Returns the saved file path.
    """
    from brain.curation import capture_signal, save_note
    import tempfile, os
    from pathlib import Path

    cfg = _get_cfg()
    inbox_path = capture_signal(cfg, content, source="mcp")
    note_path = save_note(cfg, str(inbox_path), note_type=note_type, title=title, links=links or [])
    return {"saved_path": str(note_path), "note_type": note_type}


@mcp.tool()
def recall_preferences(scope: str | None = None) -> list[dict]:
    """
    Read Brain/preferences/ output from the deterministic memory pass.
    Returns a list of preference records by lifecycle state.
    """
    from brain.frontmatter import parse as parse_fm
    from pathlib import Path

    cfg = _get_cfg()
    prefs_dir = cfg.brain_path / "preferences"
    if not prefs_dir.exists():
        return []

    results = []
    for pref_path in sorted(prefs_dir.glob("pref-*.md")):
        fm, body = parse_fm(pref_path.read_text(encoding="utf-8"))
        if scope and fm.get("lifecycle") != scope:
            continue
        results.append({
            "path": str(pref_path),
            "lifecycle": fm.get("lifecycle", "unconfirmed"),
            "signal_count": fm.get("signal_count", 0),
            "content": body.strip(),
            "warning": "read-only — mutate via `brain dream` only (C3)",
        })
    return results


def run_server(cfg: "Config") -> None:
    global _cfg
    _cfg = cfg
    mcp.run()
