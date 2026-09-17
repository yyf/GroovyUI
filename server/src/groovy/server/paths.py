"""Resolve GroovyUI bundle / monorepo roots for portable desktop and dev."""

from __future__ import annotations

import os
from pathlib import Path


def monorepo_root_from_package() -> Path:
    """server/src/groovy/server/paths.py → repo root (parents[4])."""
    return Path(__file__).resolve().parents[4]


def looks_like_bundle(root: Path) -> bool:
    return (root / "studio" / "index.html").is_file() and (root / "templates").is_dir()


def resolve_bundle_root() -> Path:
    """Prefer GROOVY_BUNDLE_ROOT, then cwd if portable layout, else monorepo root."""
    env = (os.environ.get("GROOVY_BUNDLE_ROOT") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd().resolve()
    if looks_like_bundle(cwd):
        return cwd
    return monorepo_root_from_package()


def resolve_templates_dir(bundle_root: Path | None = None) -> Path:
    root = bundle_root or resolve_bundle_root()
    return root / "templates"


def resolve_samples_dir(bundle_root: Path | None = None) -> Path:
    root = bundle_root or resolve_bundle_root()
    return root / "assets" / "samples"


def resolve_studio_dir(bundle_root: Path | None = None) -> Path | None:
    """Directory containing index.html for the built studio (or None)."""
    env = (os.environ.get("GROOVY_STUDIO_DIR") or "").strip()
    if env:
        path = Path(env).expanduser().resolve()
        return path if (path / "index.html").is_file() else None
    root = bundle_root or resolve_bundle_root()
    serve = (os.environ.get("GROOVY_SERVE_STUDIO") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    candidate = root / "studio"
    if (candidate / "index.html").is_file() and (
        serve or looks_like_bundle(root) or (os.environ.get("GROOVY_BUNDLE_ROOT") or "").strip()
    ):
        return candidate
    # Dev convenience: monorepo apps/studio/dist when explicitly requested
    if serve:
        dist = monorepo_root_from_package() / "apps" / "studio" / "dist"
        if (dist / "index.html").is_file():
            return dist
    return None


def resolve_default_project_dir(bundle_root: Path | None = None) -> Path:
    env = (os.environ.get("GROOVY_PROJECT_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    root = bundle_root or resolve_bundle_root()
    return (root / "workspace").resolve()
