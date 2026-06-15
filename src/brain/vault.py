"""Vault path resolution, write-contract enforcement (C1), and atomic writes (C5)."""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

import yaml

from brain.config import Config


class WriteContractViolation(Exception):
    """Raised when a write is attempted outside Brain/ (C1)."""


def _resolve_brain(cfg: Config) -> Path:
    return cfg.brain_path.resolve()


def check_write_allowed(cfg: Config, target: Path) -> None:
    """Raise WriteContractViolation if target is outside Brain/."""
    brain = _resolve_brain(cfg)
    try:
        target.resolve().relative_to(brain)
    except ValueError:
        raise WriteContractViolation(
            f"Write contract violation (C1): '{target}' is not under Brain/ ({brain}).\n"
            "The agent may only write inside vault/Brain/."
        )


def atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write content atomically: temp → fsync → rename (C5)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(tmp_fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Write bytes atomically: temp → fsync → rename (C5)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def safe_write(cfg: Config, path: Path, content: str) -> None:
    """Enforce write contract then write atomically."""
    check_write_allowed(cfg, path)
    atomic_write(path, content)


def init_vault(cfg: Config) -> None:
    """Scaffold vault directory structure and seed seed files."""
    vault = cfg.vault_path
    brain = cfg.brain_path

    for subdir in ["inbox", "notes", "index", "preferences", "log"]:
        (brain / subdir).mkdir(parents=True, exist_ok=True)

    (vault / "Notes").mkdir(parents=True, exist_ok=True)
    (vault / ".index").mkdir(parents=True, exist_ok=True)
    (vault / ".vault-meta").mkdir(parents=True, exist_ok=True)

    _seed_brain_yaml(cfg)
    _seed_mode_json(cfg)
    _seed_address_counter(cfg)
    _seed_root_index(cfg)
    _init_index_schema(cfg)


def _init_index_schema(cfg: Config) -> None:
    """Create the SQLite index with schema (empty) so doctor reports OK."""
    from brain.index import open_index
    with open_index(cfg):
        pass


def _seed_brain_yaml(cfg: Config) -> None:
    path = cfg.brain_path / "_brain.yaml"
    if path.exists():
        return
    data = {
        "schema_version": 1,
        "chunk_size": cfg.chunk_size,
        "chunk_overlap": cfg.chunk_overlap,
        "model": cfg.model,
        "embed_dim": cfg.embed_dim,
        "thresholds": cfg.thresholds,
        "notes": {"read_paths": cfg.notes_read_paths},
        "retention": {"inbox_days": 30, "log_days": 365},
    }
    atomic_write(path, yaml.dump(data, default_flow_style=False, sort_keys=False))


def _seed_mode_json(cfg: Config) -> None:
    import json

    path = cfg.meta_path / "mode.json"
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps({"methodology": cfg.methodology}, indent=2) + "\n")


def _seed_address_counter(cfg: Config) -> None:
    path = cfg.meta_path / "address-counter.txt"
    if path.exists():
        return
    atomic_write(path, "0\n")


def _seed_root_index(cfg: Config) -> None:
    path = cfg.brain_path / "index" / "_index.md"
    if path.exists():
        return
    content = "# Brain Index\n\nDomain indexes:\n\n_No domains yet. Add notes to create domains._\n"
    atomic_write(path, content)


def read_mode(cfg: Config) -> str:
    import json

    path = cfg.meta_path / "mode.json"
    if not path.exists():
        return "generic"
    with open(path) as f:
        return json.load(f).get("methodology", "generic")


def next_zettel_id(cfg: Config) -> str:
    """Increment and return the next Zettelkasten ID atomically."""
    path = cfg.meta_path / "address-counter.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    current = int(path.read_text().strip()) if path.exists() else 0
    nxt = current + 1
    atomic_write(path, f"{nxt}\n")
    return str(nxt).zfill(6)
