"""FastEmbed wrapper: batch embed, cached ONNX model."""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from brain.config import Config

_model_cache: dict[str, object] = {}


def _get_model(model_name: str):
    if model_name not in _model_cache:
        from fastembed import TextEmbedding
        _model_cache[model_name] = TextEmbedding(model_name=model_name)
    return _model_cache[model_name]


def embed_texts(texts: list[str], cfg: "Config") -> list[list[float]]:
    """Embed a list of texts, return list of float vectors."""
    if not texts:
        return []
    model = _get_model(cfg.model)
    embeddings = list(model.embed(texts))
    return [e.tolist() for e in embeddings]


def embed_query(query: str, cfg: "Config") -> list[float]:
    """Embed a single query string."""
    results = embed_texts([query], cfg)
    return results[0] if results else []
