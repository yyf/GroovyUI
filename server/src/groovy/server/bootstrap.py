"""Ensure project workspace has bundled sample assets."""

from __future__ import annotations

import shutil
from pathlib import Path

from groovy.server.paths import resolve_samples_dir


def ensure_project_samples(project_dir: Path, *, bundled_dir: Path | None = None) -> list[str]:
    """Copy bundled sample media into the project workspace if missing.

    Copies top-level files under ``assets/samples/`` only (not ``archived/``).
    """
    source = bundled_dir or resolve_samples_dir()
    if not source.is_dir():
        return []

    dest = project_dir / "assets" / "samples"
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for path in sorted(source.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {
            ".wav",
            ".flac",
            ".mid",
            ".midi",
            ".mp4",
            ".m4a",
            ".mp3",
            ".mov",
            ".webm",
            ".mkv",
        }:
            continue
        target = dest / path.name
        if target.exists():
            try:
                src_stat = path.stat()
                dst_stat = target.stat()
                # Skip only when workspace copy matches bundled size + mtime.
                if (
                    src_stat.st_size == dst_stat.st_size
                    and int(src_stat.st_mtime) == int(dst_stat.st_mtime)
                ):
                    continue
            except OSError:
                pass
        shutil.copy2(path, target)
        copied.append(str(target.relative_to(project_dir)))
    return copied
