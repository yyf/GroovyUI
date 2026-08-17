"""Project-relative media upload helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

_SKIP_DIR_NAMES = {".groovy", ".git", "node_modules", ".venv"}


def sidecar_path_for_audio(audio_path: Path) -> Path:
    return audio_path.with_name(f"{audio_path.stem}.provenance.json")


def iter_project_files_named(project_dir: Path, name: str) -> list[Path]:
    root = project_dir.resolve()
    matches: list[Path] = []
    for path in root.rglob(name):
        if not path.is_file():
            continue
        rel_parts = set(path.relative_to(root).parts[:-1])
        if rel_parts & _SKIP_DIR_NAMES:
            continue
        matches.append(path)
    return matches


def resolve_uploaded_audio(project_dir: Path, filename: str, payload: bytes) -> str:
    """
    Store ``payload`` under assets/uploads/, or reuse an existing project file.

    If exactly one same-name, same-size audio already sits next to a
    ``*.provenance.json`` sidecar, return that path. Otherwise write to uploads
    and copy a uniquely named sidecar if one exists.
    """
    safe_name = Path(filename).name
    if not safe_name or safe_name in {".", ".."}:
        raise ValueError("Missing filename")

    existing = [
        path
        for path in iter_project_files_named(project_dir, safe_name)
        if sidecar_path_for_audio(path).is_file() and path.stat().st_size == len(payload)
    ]
    if len(existing) == 1:
        return existing[0].relative_to(project_dir.resolve()).as_posix()

    dest_dir = project_dir / "assets" / "uploads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_name
    dest.write_bytes(payload)

    sidecar_name = sidecar_path_for_audio(dest).name
    dest_sidecar = sidecar_path_for_audio(dest)
    candidates = [
        path for path in iter_project_files_named(project_dir, sidecar_name) if path != dest_sidecar
    ]
    if len(candidates) == 1:
        shutil.copy2(candidates[0], dest_sidecar)
    return f"assets/uploads/{safe_name}"
