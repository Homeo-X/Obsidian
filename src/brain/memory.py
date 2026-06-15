"""
Deterministic memory accretion pass (C3: NO LLM imports, NO model calls).
Lifecycle: unconfirmed → confirmed → quarantine → retired.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import yaml

from brain.config import Config
from brain.vault import atomic_write, check_write_allowed

# Prevent accidental LLM imports — this module must stay deterministic.
# Any attempt to import llm-related libraries will fail at import time
# via the test in test_memory.py.

LIFECYCLE = ["unconfirmed", "confirmed", "quarantine", "retired"]


def _slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:48].strip("-")


def _pref_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _read_fm(path: Path) -> tuple[dict, str]:
    """Read YAML frontmatter + body from a file."""
    text = path.read_text(encoding="utf-8")
    from brain.frontmatter import parse
    return parse(text)


def _write_pref(cfg: Config, pref_id: str, slug: str, fm: dict, body: str) -> Path:
    """Write a preference file atomically."""
    path = cfg.brain_path / "preferences" / f"pref-{slug}.md"
    check_write_allowed(cfg, path)
    fm_str = yaml.dump(fm, default_flow_style=False, sort_keys=False).rstrip()
    atomic_write(path, f"---\n{fm_str}\n---\n\n{body}\n")
    return path


def _snapshot(cfg: Config, run_id: str) -> Path:
    """Snapshot Brain/ before mutation (makes passes reversible)."""
    snap_dir = cfg.brain_path / ".snapshots" / f"dream-{run_id}"
    snap_dir.parent.mkdir(parents=True, exist_ok=True)

    if cfg.brain_path.exists():
        shutil.copytree(
            cfg.brain_path,
            snap_dir,
            ignore=shutil.ignore_patterns(".snapshots"),
            dirs_exist_ok=False,
        )
    return snap_dir


def run_dream_pass(cfg: Config) -> dict:
    """
    Deterministic accretion pass.
    1. Snapshot Brain/ for rollback.
    2. Read inbox signals with status=preference.
    3. Count repeated signals by content hash.
    4. Promote through lifecycle based on configured thresholds.
    5. Move processed signals to inbox/processed/.
    Returns a summary dict (no LLM calls anywhere in this function).
    """
    run_id = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    snap_path = _snapshot(cfg, run_id)

    thresholds = cfg.thresholds
    confirm_threshold = int(thresholds.get("memory_confirm", 3))
    quarantine_threshold = int(thresholds.get("memory_quarantine", 5))

    inbox = cfg.brain_path / "inbox"
    processed_dir = inbox / "processed"
    prefs_dir = cfg.brain_path / "preferences"
    prefs_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Collect signals
    signal_files = list(inbox.glob("*.md")) if inbox.exists() else []
    signal_counts: dict[str, dict] = {}

    for sig_path in signal_files:
        fm, body = _read_fm(sig_path)
        if fm.get("status") not in ("preference", "raw"):
            continue
        content = body.strip()
        if not content:
            continue
        content_hash = _pref_id(content)
        if content_hash not in signal_counts:
            signal_counts[content_hash] = {
                "content": content,
                "count": 0,
                "files": [],
            }
        signal_counts[content_hash]["count"] += 1
        signal_counts[content_hash]["files"].append(sig_path)

    # Load existing preferences
    existing_prefs: dict[str, tuple[Path, dict, str]] = {}
    for pref_path in prefs_dir.glob("pref-*.md"):
        pfm, pbody = _read_fm(pref_path)
        phash = pfm.get("content_hash")
        if phash:
            existing_prefs[phash] = (pref_path, pfm, pbody)

    promoted = 0
    transitions: list[str] = []

    for content_hash, info in signal_counts.items():
        count = info["count"]
        content = info["content"]
        slug = _slug(content[:40])

        if content_hash in existing_prefs:
            pref_path, pfm, pbody = existing_prefs[content_hash]
            old_state = pfm.get("lifecycle", "unconfirmed")
            total_count = pfm.get("signal_count", 0) + count
            pfm["signal_count"] = total_count
            pfm["last_seen"] = run_id

            new_state = _next_state(old_state, total_count, confirm_threshold, quarantine_threshold)
            if new_state != old_state:
                pfm["lifecycle"] = new_state
                transitions.append(f"{slug}: {old_state} → {new_state}")
                promoted += 1

            check_write_allowed(cfg, pref_path)
            fm_str = yaml.dump(pfm, default_flow_style=False, sort_keys=False).rstrip()
            atomic_write(pref_path, f"---\n{fm_str}\n---\n\n{pbody}\n")
        else:
            if count < 1:
                continue
            pref_fm = {
                "pref_id": content_hash,
                "content_hash": content_hash,
                "slug": slug,
                "lifecycle": "unconfirmed",
                "signal_count": count,
                "created": run_id,
                "last_seen": run_id,
            }
            total_count = count
            state = _next_state("unconfirmed", total_count, confirm_threshold, quarantine_threshold)
            pref_fm["lifecycle"] = state
            if state != "unconfirmed":
                transitions.append(f"{slug}: new → {state}")
                promoted += 1

            _write_pref(cfg, content_hash, slug, pref_fm, content)

        for sig_path in info["files"]:
            dest = processed_dir / sig_path.name
            if sig_path.exists():
                atomic_write(dest, sig_path.read_text(encoding="utf-8"))
                sig_path.unlink()

    return {
        "run_id": run_id,
        "snapshot": str(snap_path),
        "signals_processed": len(signal_counts),
        "promoted": promoted,
        "transitions": transitions,
    }


def _next_state(
    current: str, count: int, confirm_threshold: int, quarantine_threshold: int
) -> str:
    """Pure function: deterministic lifecycle transition."""
    if current == "retired":
        return "retired"
    if count >= quarantine_threshold:
        return "quarantine"
    if count >= confirm_threshold:
        return "confirmed"
    return "unconfirmed"
