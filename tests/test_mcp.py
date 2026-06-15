"""
Phase 5 gate: MCP tool round-trip — save a note, search and retrieve it through the server.
Tests call MCP tool functions directly (they share CLI code paths; the protocol layer is FastMCP).
"""
from __future__ import annotations

import pytest

import brain.mcp_server as mcp_module


@pytest.fixture(autouse=True)
def inject_cfg(cfg):
    """Point the MCP server module at the test vault config."""
    mcp_module._cfg = cfg
    yield
    mcp_module._cfg = None


# ── save ──────────────────────────────────────────────────────────────────────

def test_mcp_save_creates_note_under_brain(cfg):
    """GATE 5: save() writes an atomic note that obeys the write contract (C1)."""
    result = mcp_module.save(
        content="The observer effect in quantum mechanics changes the system under measurement",
        note_type="note",
        title="observer-effect",
        links=["Quantum Mechanics"],
    )
    assert "saved_path" in result
    from pathlib import Path
    note_path = Path(result["saved_path"])

    # File must exist
    assert note_path.exists(), f"Saved note must exist at {note_path}"

    # Must be inside Brain/ (write contract C1)
    try:
        note_path.resolve().relative_to(cfg.brain_path.resolve())
    except ValueError:
        pytest.fail(f"Saved note is outside Brain/: {note_path}")

    # Must have valid frontmatter
    from brain.frontmatter import parse as parse_fm
    fm, body = parse_fm(note_path.read_text())
    assert fm.get("status") == "curated"
    assert "observer" in body.lower() or "quantum" in body.lower()


def test_mcp_save_wikilinks_appear_in_note(cfg):
    """save() with links produces [[wikilinks]] in the note body."""
    result = mcp_module.save(
        content="Entropy increases in isolated systems according to the second law of thermodynamics",
        note_type="note",
        title="entropy-thermodynamics",
        links=["Thermodynamics", "Physics"],
    )
    from pathlib import Path
    note_path = Path(result["saved_path"])
    content = note_path.read_text()
    assert "[[Thermodynamics]]" in content
    assert "[[Physics]]" in content


def test_mcp_save_refuses_write_outside_brain(cfg, monkeypatch):
    """save() must not escape Brain/ even if the underlying route tries to."""
    from brain.vault import WriteContractViolation

    original_route = None
    import brain.curation as curation_mod

    original_route_fn = curation_mod.route

    def evil_route(cfg, note_type, name):
        # Attempt to route outside Brain/
        bad_path = cfg.notes_path / "evil.md"
        return bad_path, "evil"

    monkeypatch.setattr(curation_mod, "route", evil_route)

    with pytest.raises((WriteContractViolation, Exception)):
        mcp_module.save(content="evil escape attempt", note_type="note", title="evil")


# ── search ─────────────────────────────────────────────────────────────────────

def test_mcp_save_then_search_finds_note(cfg):
    """GATE 5 core: save a note then search for it through the MCP surface."""
    mcp_module.save(
        content="Neuroplasticity allows the brain to reorganize neural pathways based on experience",
        note_type="note",
        title="neuroplasticity",
    )

    results = mcp_module.search("brain rewires itself through learning", k=5)

    assert results, "search() should return results after save()"
    note_paths = [r["note_path"] for r in results]
    assert any("neuroplasticity" in p for p in note_paths), (
        f"Saved note should be retrievable via semantic search. Got: {note_paths}"
    )


def test_mcp_search_returns_pointer_not_authoritative(cfg):
    """GATE 5 + Phase 6: search results must be pointers, not authoritative content."""
    mcp_module.save(
        content="Bayes theorem updates prior probability with new evidence",
        note_type="note",
        title="bayes-theorem",
    )

    results = mcp_module.search("probability updating beliefs", k=5)
    assert results
    for r in results:
        assert r.get("pointer") is True or "pointer" in r.get("warning", ""), (
            "MCP search results must carry pointer metadata (Phase 6 policy)"
        )
        # Snippet must not be the full live-file content
        assert len(r.get("snippet", "")) < 2000, (
            "Snippet should be a short excerpt, not full authoritative file content"
        )


# ── recall_preferences ─────────────────────────────────────────────────────────

def test_mcp_recall_preferences_returns_list(cfg):
    """recall_preferences() returns a list (possibly empty on fresh vault)."""
    result = mcp_module.recall_preferences()
    assert isinstance(result, list)


def test_mcp_recall_preferences_has_warning(cfg):
    """recall_preferences() results must carry the read-only warning (C3 guard)."""
    import yaml
    from datetime import datetime
    from brain.vault import atomic_write

    # Plant a confirmed preference
    pref_path = cfg.brain_path / "preferences" / "pref-test-mcp.md"
    fm = {
        "pref_id": "test123",
        "content_hash": "abc",
        "slug": "test-mcp",
        "lifecycle": "confirmed",
        "signal_count": 3,
        "created": "20260615-000000",
        "last_seen": "20260615-000000",
    }
    fm_str = yaml.dump(fm, default_flow_style=False, sort_keys=False).rstrip()
    atomic_write(pref_path, f"---\n{fm_str}\n---\n\ntest preference content\n")

    result = mcp_module.recall_preferences()
    assert result
    for r in result:
        assert "warning" in r, "recall_preferences must carry C3 read-only warning"
        assert "dream" in r["warning"].lower() or "read-only" in r["warning"].lower()
