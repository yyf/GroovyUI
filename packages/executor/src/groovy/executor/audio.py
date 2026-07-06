from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np


@dataclass
class AudioBuffer:
    id: str
    sample_rate: int
    channels: int
    frame_count: int
    channel_layout: str = "mono"
    channel_map: list[str] = field(default_factory=list)
    dtype: str = "float64"
    layout: str = "planar"
    path: str | None = None
    source_node: str | None = None
    source_node_type: str | None = None
    content_hash: str | None = None

    @property
    def data(self) -> np.ndarray:
        if self.path is None:
            raise ValueError("AudioBuffer has no backing path")
        raw = np.fromfile(self.path, dtype=np.float64)
        return raw.reshape(self.channels, self.frame_count)

    @classmethod
    def from_planar(
        cls,
        pcm: np.ndarray,
        sample_rate: int,
        *,
        source_node: str | None = None,
        source_node_type: str | None = None,
        channel_layout: str | None = None,
    ) -> AudioBuffer:
        if pcm.ndim == 1:
            pcm = pcm.reshape(1, -1)
        channels, frame_count = pcm.shape
        layout = channel_layout or ("mono" if channels == 1 else "stereo")
        channel_map = (
            ["FL", "FR"][:channels] if channels <= 2 else [f"ch{i}" for i in range(channels)]
        )
        content_hash = hashlib.sha256(pcm.tobytes()).hexdigest()
        return cls(
            id=str(uuid.uuid4()),
            sample_rate=sample_rate,
            channels=channels,
            frame_count=frame_count,
            channel_layout=layout,
            channel_map=channel_map,
            content_hash=f"sha256:{content_hash}",
            source_node=source_node,
            source_node_type=source_node_type,
        )

    def to_meta(self) -> dict:
        return {
            "id": self.id,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "channel_layout": self.channel_layout,
            "channel_map": self.channel_map,
            "frame_count": self.frame_count,
            "dtype": self.dtype,
            "layout": self.layout,
            "source_node": self.source_node,
            "source_node_type": self.source_node_type,
            "created_at": datetime.now(UTC).isoformat(),
            "content_hash": self.content_hash,
        }
