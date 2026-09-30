"""Resolve template JSON from public templates/ or local docs/internal/templates/."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_TEMPLATES = ROOT / "templates"
DEV_TEMPLATES = ROOT / "docs" / "internal" / "templates"


def find_template_path(template_id: str) -> Path | None:
    name = f"{template_id}.groovy.json"
    for directory in (PUBLIC_TEMPLATES, DEV_TEMPLATES):
        path = directory / name
        if path.is_file():
            return path
    return None


def require_template(template_id: str) -> Path:
    path = find_template_path(template_id)
    if path is None:
        pytest.skip(
            f"Template {template_id!r} not found "
            f"(checked {PUBLIC_TEMPLATES} and {DEV_TEMPLATES})"
        )
    return path
