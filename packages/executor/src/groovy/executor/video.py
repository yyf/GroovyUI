"""Project-relative video clip handle for mux / preview / save."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VideoClip:
    """A rendered or composed video file under the project tree."""

    id: str
    path: str  # project-relative path
    source_node_type: str | None = None
    source_video_path: str | None = None
    width: int | None = None
    height: int | None = None
    content_hash: str | None = None

    @classmethod
    def create(
        cls,
        path: str,
        *,
        source_node_type: str | None = None,
        source_video_path: str | None = None,
        width: int | None = None,
        height: int | None = None,
        content_hash: str | None = None,
    ) -> VideoClip:
        return cls(
            id=str(uuid.uuid4()),
            path=path,
            source_node_type=source_node_type,
            source_video_path=source_video_path,
            width=width,
            height=height,
            content_hash=content_hash,
        )

    def ensure_content_hash(self, *, project_dir: Path | None = None) -> str:
        """SHA-256 of the on-disk clip (cached on the instance)."""
        if self.content_hash:
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
