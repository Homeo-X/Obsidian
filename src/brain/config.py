"""Load and validate configuration from ~/.config/brain/config.yaml and .env."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

APP_NAME = "brain"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ENV_FILE = CONFIG_DIR / ".env"

DEFAULTS: dict[str, Any] = {
    "vault_path": str(Path.home() / "vault"),
    "model": "BAAI/bge-base-en-v1.5",
    "embed_dim": 768,
    "chunk_size": 1600,
    "chunk_overlap": 200,
    "debounce_ms": 500,
    "thresholds": {
        "similarity_error": 0.90,
        "similarity_review": 0.80,
        "memory_confirm": 3,
        "memory_quarantine": 5,
    },
    "notes": {
        "read_paths": [],
    },
    "methodology": "generic",
}


class Config:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    @property
    def vault_path(self) -> Path:
        return Path(self._data["vault_path"]).expanduser().resolve()

    @property
    def brain_path(self) -> Path:
        return self.vault_path / "Brain"

    @property
    def notes_path(self) -> Path:
        return self.vault_path / "Notes"

    @property
    def index_path(self) -> Path:
        return self.vault_path / ".index"

    @property
    def meta_path(self) -> Path:
        return self.vault_path / ".vault-meta"

    @property
    def model(self) -> str:
        return self._data["model"]

    @property
    def embed_dim(self) -> int:
        return int(self._data["embed_dim"])

    @property
    def chunk_size(self) -> int:
        return int(self._data["chunk_size"])

    @property
    def chunk_overlap(self) -> int:
        return int(self._data["chunk_overlap"])

    @property
    def debounce_ms(self) -> int:
        return int(self._data["debounce_ms"])

    @property
    def thresholds(self) -> dict[str, float]:
        return self._data["thresholds"]

    @property
    def notes_read_paths(self) -> list[str]:
        return self._data.get("notes", {}).get("read_paths", [])

    @property
    def methodology(self) -> str:
        return self._data.get("methodology", "generic")


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(vault_path: str | None = None) -> Config:
    """Load config, merge with defaults, validate required fields."""
    load_dotenv(ENV_FILE, override=False)
    load_dotenv(Path(".env"), override=False)

    data = dict(DEFAULTS)

    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            user_cfg = yaml.safe_load(f) or {}
        data = _deep_merge(data, user_cfg)

    if vault_path:
        data["vault_path"] = vault_path
    elif os.environ.get("BRAIN_VAULT_PATH"):
        data["vault_path"] = os.environ["BRAIN_VAULT_PATH"]

    cfg = Config(data)

    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    if not cfg.vault_path.parent.exists():
        raise RuntimeError(
            f"vault_path parent does not exist: {cfg.vault_path.parent}\n"
            f"Set vault_path in {CONFIG_FILE} or BRAIN_VAULT_PATH env var."
        )
    if cfg.embed_dim <= 0:
        raise RuntimeError("embed_dim must be positive")
    if cfg.chunk_size <= cfg.chunk_overlap:
        raise RuntimeError("chunk_size must be greater than chunk_overlap")


def write_default_config(vault_path: str) -> None:
    """Write a default config file if one doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        cfg_data = dict(DEFAULTS)
        cfg_data["vault_path"] = vault_path
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(cfg_data, f, default_flow_style=False, sort_keys=False)
