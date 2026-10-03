"""Project-relative video clip handle for mux / preview / save."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass
class VideoClip:
    """A rendered or composed video file under the project tree."""

    id: str
    path: str  # project-relative path
    source_node_type: str | None = None
    source_video_path: str | None = None
    width: int | None = None
    height: int | None = None

    @classmethod
    def create(
        cls,
        path: str,
        *,
        source_node_type: str | None = None,
        source_video_path: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> VideoClip:
        return cls(
            id=str(uuid.uuid4()),
            path=path,
            source_node_type=source_node_type,
            source_video_path=source_video_path,
            width=width,
            height=height,
        )
