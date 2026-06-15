"""Phase 1 gate: write-contract enforcement (C1) and atomic writes (C5)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from brain.vault import (
    WriteContractViolation,
    atomic_write,
    check_write_allowed,
    safe_write,
)


def test_write_inside_brain_allowed(cfg):
    """Writing under Brain/ must succeed."""
    target = cfg.brain_path / "notes" / "test.md"
    safe_write(cfg, target, "# Test\n")
    assert target.exists()
    assert target.read_text() == "# Test\n"


def test_write_to_notes_raises(cfg):
    """Writing under Notes/ must raise WriteContractViolation."""
    bad = cfg.notes_path / "secret.md"
    with pytest.raises(WriteContractViolation):
        safe_write(cfg, bad, "should not write")


def test_write_to_vault_root_raises(cfg):
    """Writing to vault root (outside Brain/) must raise."""
    bad = cfg.vault_path / "root.md"
    with pytest.raises(WriteContractViolation):
        safe_write(cfg, bad, "should not write")


def test_write_to_absolute_other_raises(cfg):
    """Writing to an arbitrary absolute path must raise."""
    bad = Path("/tmp/escaped.md")
    with pytest.raises(WriteContractViolation):
        safe_write(cfg, bad, "escaped")


def test_path_traversal_blocked(cfg):
    """Path traversal via .. must be blocked."""
    bad = cfg.brain_path / ".." / "Notes" / "traversal.md"
    with pytest.raises(WriteContractViolation):
        safe_write(cfg, bad, "traversal attempt")


def test_atomic_write_no_partial_on_crash(cfg, monkeypatch):
    """A simulated crash mid-write leaves no partial file (C5)."""
    target = cfg.brain_path / "notes" / "atomic-test.md"
    assert not target.exists()

    original_fsync = os.fsync
    crash_called = False

    def crashing_fsync(fd):
        nonlocal crash_called
        crash_called = True
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "fsync", crashing_fsync)

    with pytest.raises(OSError):
        atomic_write(target, "partial content")

    assert crash_called
    assert not target.exists(), "No partial file should remain after crash"


def test_atomic_write_succeeds_normally(cfg):
    """Normal atomic write produces the expected file."""
    target = cfg.brain_path / "notes" / "normal.md"
    atomic_write(target, "hello world\n")
    assert target.read_text() == "hello world\n"
