"""
Lightweight embedding utilities — hash-based mock when a real model is unavailable.
"""
from __future__ import annotations
import hashlib
import struct
from typing import List

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


def _hash_embed(text: str, dim: int = 128) -> List[float]:
    """Deterministic pseudo-embedding via iterated SHA-256."""
    vec: List[float] = []
    seed = text.encode()
    i = 0
    while len(vec) < dim:
        h = hashlib.sha256(seed + i.to_bytes(4, "little")).digest()
        vec.extend(struct.unpack("16f", h[:64]))
        i += 1
    floats = vec[:dim]
    norm = (sum(x * x for x in floats) ** 0.5) or 1.0
    return [x / norm for x in floats]


def embed(text: str, dim: int = 128) -> List[float]:
    return _hash_embed(text, dim)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = sum(x * x for x in a) ** 0.5
    nb  = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0
