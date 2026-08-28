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
    layout_order: int | None = None
    encoding_scheme: str | None = None
    file_format: str | None = None
    file_subtype: str | None = None
    spatial_meta: dict = field(default_factory=dict)
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
        pcm = np.asarray(pcm, dtype=np.float64)
        if pcm.ndim == 1:
            pcm = pcm.reshape(1, -1)
        channels, frame_count = pcm.shape
        from groovy.executor.audio_meta import channel_layout_for_channels, channel_map_for_layout

        layout = channel_layout or channel_layout_for_channels(channels)
        channel_map = channel_map_for_layout(layout, channels)
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
        meta = {
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
        if self.layout_order is not None:
            meta["layout_order"] = self.layout_order
        if self.encoding_scheme:
            meta["encoding_scheme"] = self.encoding_scheme
        if self.file_format:
            meta["file_format"] = self.file_format
        if self.file_subtype:
            meta["file_subtype"] = self.file_subtype
        if self.spatial_meta:
            meta["spatial_meta"] = self.spatial_meta
        return meta


@dataclass
class StemsBuffer:
    id: str
    sample_rate: int
    channels: int
    frame_count: int
    stems: dict[str, AudioBuffer]

    def to_meta(self) -> dict:
        return {
            "id": self.id,
            "type": "STEMS",
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "frame_count": self.frame_count,
            "stems": {
                name: {"id": buf.id, "frame_count": buf.frame_count}
                for name, buf in self.stems.items()
            },
        }

    @classmethod
    def from_stem_pcm(
        cls,
        stem_pcm: dict[str, np.ndarray],
        sample_rate: int,
        *,
        channel_layout: str = "mono",
        source_node_type: str = "SeparateStems",
    ) -> StemsBuffer:
        buffers: dict[str, AudioBuffer] = {}
        frame_count = 0
        channels = 1
        for name, pcm in stem_pcm.items():
            if pcm.ndim == 1:
                pcm = pcm.reshape(1, -1)
            buf = AudioBuffer.from_planar(
                pcm,
                sample_rate,
                source_node_type=source_node_type,
                channel_layout=channel_layout,
            )
            buffers[name] = buf
            frame_count = buf.frame_count
            channels = buf.channels
        return cls(
            id=str(uuid.uuid4()),
            sample_rate=sample_rate,
            channels=channels,
            frame_count=frame_count,
            stems=buffers,
        )
