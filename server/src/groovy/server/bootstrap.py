"""Ensure project workspace has bundled sample assets."""

from __future__ import annotations

import shutil
from pathlib import Path

BUNDLED_SAMPLES_DIR = Path(__file__).resolve().parents[4] / "assets" / "samples"


def ensure_project_samples(project_dir: Path, *, bundled_dir: Path | None = None) -> list[str]:
    """Copy bundled sample media into the project workspace if missing.

    Copies top-level files under ``assets/samples/`` only (not ``archived/``).
    """
    source = bundled_dir or BUNDLED_SAMPLES_DIR
    if not source.is_dir():
        return []

    dest = project_dir / "assets" / "samples"
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for path in sorted(source.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".wav", ".flac", ".mid", ".midi", ".mp4", ".m4a", ".mp3"}:
            continue
        target = dest / path.name
        if target.exists():
            continue
        shutil.copy2(path, target)
        copied.append(str(target.relative_to(project_dir)))
    return copied
