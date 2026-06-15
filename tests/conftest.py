"""Shared fixtures for all tests."""
from __future__ import annotations

import pytest
from pathlib import Path
import tempfile
import shutil

from brain.config import Config, DEFAULTS


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """A temporary vault directory with Brain/ scaffold."""
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


@pytest.fixture
def cfg(tmp_vault: Path) -> Config:
    """A Config pointing at a temp vault."""
    data = dict(DEFAULTS)
    data["vault_path"] = str(tmp_vault)
    data["model"] = "BAAI/bge-base-en-v1.5"
    data["embed_dim"] = 768
    cfg = Config(data)
    from brain.vault import init_vault
    init_vault(cfg)
    return cfg
