from __future__ import annotations

from typing import Any


def float_param(kwargs: dict[str, Any], name: str, default: float) -> float:
    raw = kwargs.get(name, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def int_param(kwargs: dict[str, Any], name: str, default: int) -> int:
    raw = kwargs.get(name, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def seed_param(kwargs: dict[str, Any], *, fallback: str = "") -> int:
    """Return an explicit non-negative seed, or a stable hash of *fallback* when seed is -1/unset."""
    raw = kwargs.get("seed", -1)
    try:
        seed = int(raw)
    except (TypeError, ValueError):
        seed = -1
    if seed >= 0:
        return seed
    material = fallback or "groovy"
    return sum(ord(c) for c in material) % 2147483647


def optional_seed(kwargs: dict[str, Any]) -> int | None:
    """Return seed when explicitly set (>= 0), else None (backend may sample randomly)."""
    raw = kwargs.get("seed", -1)
    try:
        seed = int(raw)
    except (TypeError, ValueError):
        return None
    return seed if seed >= 0 else None


def bool_param(kwargs: dict[str, Any], name: str, default: bool) -> bool:
    raw = kwargs.get(name, default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw)


def optional_frequency(kwargs: dict[str, Any], name: str) -> float | None:
    raw = kwargs.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return None if value <= 0 else value
