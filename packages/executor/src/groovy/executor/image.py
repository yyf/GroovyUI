"""Project-relative still image handle for LoadImage → GenerateVideo I2V."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def is_image_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in _IMAGE_SUFFIXES


@dataclass
class ImageClip:
    """A still image file under the project tree."""

    id: str
    path: str  # project-relative path
    source_node_type: str | None = None
    width: int | None = None
    height: int | None = None
    content_hash: str | None = None

    @classmethod
    def create(
        cls,
        path: str,
        *,
        source_node_type: str | None = None,
        width: int | None = None,
        height: int | None = None,
        content_hash: str | None = None,
    ) -> ImageClip:
        return cls(
            id=str(uuid.uuid4()),
            path=path,
            source_node_type=source_node_type,
            width=width,
            height=height,
            content_hash=content_hash,
        )

    def ensure_content_hash(self, *, project_dir: Path | None = None) -> str:
        if self.content_hash:
            return self.content_hash
        if not str(self.path or "").strip():
            # Optional empty LoadImage (I2V not armed) — no file to hash.
            self.content_hash = ""
            return self.content_hash
        root = Path(project_dir) if project_dir is not None else Path.cwd()
        file_path = Path(self.path)
        if not file_path.is_absolute():
            file_path = root / file_path
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        self.content_hash = f"sha256:{digest.hexdigest()}"
        return self.content_hash


def probe_image_dimensions(path: Path) -> tuple[int, int] | None:
    """Best-effort width/height via Pillow when installed."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            w, h = img.size
            if w > 0 and h > 0:
                return int(w), int(h)
    except Exception:
        return None
    return None
