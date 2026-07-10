from __future__ import annotations

from pathlib import Path

from groovy.executor.cache import CacheStore

MEDIA_SEARCH_DIRS = ("assets/samples", "assets/uploads")
MEDIA_EXTENSIONS = {".wav", ".flac", ".aiff", ".aif", ".mp3", ".ogg", ".mid", ".midi"}


def _normalize_relative(path: str) -> str:
    return path.strip().replace("\\", "/")


def _normalize_basename(name: str) -> str:
    """Fold case and treat hyphens/underscores as equivalent for matching."""
    return name.lower().replace("-", "_")


def _list_media_files(cache: CacheStore) -> list[str]:
    paths: list[str] = []
    for folder in MEDIA_SEARCH_DIRS:
        root = cache.project_dir / folder
        if not root.is_dir():
            continue
        for candidate in root.rglob("*"):
            if candidate.is_file() and candidate.suffix.lower() in MEDIA_EXTENSIONS:
                paths.append(str(candidate.relative_to(cache.project_dir)).replace("\\", "/"))
    return paths


def find_media_path_suggestions(cache: CacheStore, relative: str) -> list[str]:
    """Return project-relative paths that share the same filename as ``relative``."""
    normalized = _normalize_relative(relative)
    if not normalized:
        return []
    basename = Path(normalized).name
    if not basename:
        return []
    matches = [path for path in _list_media_files(cache) if Path(path).name == basename]
    if matches:
        return list(dict.fromkeys(matches))
    folded = _normalize_basename(basename)
    return list(
        dict.fromkeys(
            path for path in _list_media_files(cache) if _normalize_basename(Path(path).name) == folded
        )
    )


def resolve_project_media_path(cache: CacheStore, relative: str) -> tuple[Path, str]:
    """
    Resolve a project-relative media path.

    Returns ``(absolute_path, canonical_project_relative_path)``.
    Bare filenames (e.g. ``male-1.wav``) also match under ``assets/samples/`` and
    ``assets/uploads/``. Hyphen/underscore spelling differences are tolerated when
    the match is unambiguous.
    """
    normalized = _normalize_relative(relative)
    if not normalized:
        raise FileNotFoundError(build_media_not_found_error(cache, relative))

    direct = cache.resolve_project_path(normalized)
    if direct.exists():
        return direct, normalized

    if "/" not in normalized:
        for folder in MEDIA_SEARCH_DIRS:
            candidate_rel = f"{folder}/{normalized}"
            candidate = cache.resolve_project_path(candidate_rel)
            if candidate.exists():
                return candidate, candidate_rel

    suggestions = find_media_path_suggestions(cache, relative)
    if len(suggestions) == 1:
        candidate = cache.resolve_project_path(suggestions[0])
        if candidate.exists():
            return candidate, suggestions[0]

    raise FileNotFoundError(build_media_not_found_error(cache, relative))


def build_media_not_found_error(cache: CacheStore, relative: str) -> str:
    normalized = _normalize_relative(relative)
    attempted = cache.resolve_project_path(normalized) if normalized else None
    suggestions = find_media_path_suggestions(cache, relative)

    lines = [f"FILE_NOT_FOUND: {relative or '(empty path)'}"]
    if attempted is not None:
        lines.append(f"Resolved to: {attempted}")
    lines.append(f"Project folder: {cache.project_dir}")
    lines.append(
        "Paths are relative to the project folder (default: workspace/), "
        "not your Mac/Windows Downloads path or the repo templates/ folder."
    )
    if suggestions:
        preview = ", ".join(suggestions[:4])
        suffix = f" (and {len(suggestions) - 4} more)" if len(suggestions) > 4 else ""
        lines.append(f"Similar file(s) under the project — try: {preview}{suffix}")
    else:
        lines.append(
            "Drop the file onto the canvas to copy it into assets/uploads/, "
            "or place it under assets/samples/ and reference assets/samples/your-file.wav."
        )
    return "\n".join(lines)
