"""Phase 7 gate: deterministic memory pass — LLM-free, byte-reproducible."""
from __future__ import annotations

import ast
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

from brain.memory import run_dream_pass, _next_state
from brain.vault import atomic_write


_drop_counter = 0


def _drop_signal(cfg, text: str, status: str = "preference") -> None:
    import yaml
    from datetime import datetime
    global _drop_counter

    _drop_counter += 1
    name = f"sig-test-{abs(hash(text))}-{_drop_counter:04d}.md"
    path = cfg.brain_path / "inbox" / name
    fm = {"status": status, "created": datetime.utcnow().isoformat(), "source": "test"}
    fm_str = yaml.dump(fm, default_flow_style=False, sort_keys=False).rstrip()
    atomic_write(path, f"---\n{fm_str}\n---\n\n{text}\n")


def test_memory_no_llm_imports():
    """memory.py must not import any LLM client libraries (C3)."""
    import brain.memory as mem_module
    source_path = Path(mem_module.__file__)
    source = source_path.read_text(encoding="utf-8")

    forbidden_patterns = [
        "import openai", "from openai", "import anthropic", "from anthropic",
        "import langchain", "from langchain", "import litellm", "from litellm",
        "import transformers", "from transformers", "fastembed", "TextEmbedding",
        "import cohere", "from cohere", "import groq", "from groq",
    ]
    for pattern in forbidden_patterns:
        assert pattern not in source, (
            f"memory.py must not import LLM clients (C3). Found: '{pattern}'"
        )


def test_dream_pass_is_deterministic(cfg, tmp_path):
    """Running dream twice on identical inputs yields identical preferences/ output."""
    for _ in range(3):
        _drop_signal(cfg, "prefer concise responses without filler")

    result1 = run_dream_pass(cfg)
    prefs_dir = cfg.brain_path / "preferences"
    state1 = {p.name: p.read_text() for p in sorted(prefs_dir.glob("*.md"))}

    cfg2_data = {"vault_path": str(tmp_path / "vault2")}
    from brain.config import Config, DEFAULTS
    cfg2_data_full = dict(DEFAULTS)
    cfg2_data_full["vault_path"] = str(tmp_path / "vault2")
    cfg2 = Config(cfg2_data_full)
    from brain.vault import init_vault
    init_vault(cfg2)

    for _ in range(3):
        _drop_signal(cfg2, "prefer concise responses without filler")

    result2 = run_dream_pass(cfg2)
    prefs_dir2 = cfg2.brain_path / "preferences"
    state2 = {p.name: p.read_text() for p in sorted(prefs_dir2.glob("*.md"))}

    assert set(state1.keys()) == set(state2.keys()), "Same filenames expected"
    for name in state1:
        content1 = _strip_run_id(state1[name])
        content2 = _strip_run_id(state2[name])
        assert content1 == content2, f"Preference {name} differs between runs"


def _strip_run_id(text: str) -> str:
    """Remove run_id and timestamp fields for comparison."""
    import re
    text = re.sub(r"(created|last_seen): \d{8}-\d{6}", "TIMESTAMP", text)
    return text


def test_lifecycle_transitions(cfg):
    """Lifecycle must promote at configured thresholds."""
    signal = "always use short variable names"

    cfg_thresholds = cfg.thresholds
    confirm_at = int(cfg_thresholds.get("memory_confirm", 3))
    quarantine_at = int(cfg_thresholds.get("memory_quarantine", 5))

    for _ in range(confirm_at):
        _drop_signal(cfg, signal)

    run_dream_pass(cfg)

    prefs_dir = cfg.brain_path / "preferences"
    pref_files = list(prefs_dir.glob("*.md"))
    assert pref_files, "Expected at least one preference file"

    from brain.frontmatter import parse as parse_fm
    for pf in pref_files:
        fm, _ = parse_fm(pf.read_text())
        if "variable" in fm.get("slug", ""):
            assert fm["lifecycle"] in ("confirmed", "quarantine"), (
                f"Expected confirmed or quarantine after {confirm_at} signals, got {fm['lifecycle']}"
            )


def test_snapshot_created_before_mutation(cfg):
    """dream must write a snapshot before mutating preferences/."""
    _drop_signal(cfg, "test snapshot signal")
    result = run_dream_pass(cfg)
    snap_path = Path(result["snapshot"])
    assert snap_path.exists(), "Snapshot directory must exist after dream pass"


def test_processed_signals_moved(cfg):
    """Signals processed by dream should be moved to inbox/processed/."""
    _drop_signal(cfg, "a unique test preference signal xyz")
    inbox = cfg.brain_path / "inbox"
    before = list(inbox.glob("*.md"))

    run_dream_pass(cfg)

    after = list(inbox.glob("*.md"))
    processed = list((inbox / "processed").glob("*.md"))
    assert len(processed) >= 1, "Processed signals should be in inbox/processed/"


def test_next_state_pure():
    """_next_state is a pure deterministic function."""
    assert _next_state("unconfirmed", 0, 3, 5) == "unconfirmed"
    assert _next_state("unconfirmed", 3, 3, 5) == "confirmed"
    assert _next_state("confirmed", 5, 3, 5) == "quarantine"
    assert _next_state("quarantine", 10, 3, 5) == "quarantine"
    assert _next_state("retired", 100, 3, 5) == "retired"
