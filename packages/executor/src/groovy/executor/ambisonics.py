from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np


@dataclass
class AmbisonicBuffer:
    """HOA B-format buffer (AmbiX ACN channel order, SN3D normalization)."""

    id: str
    sample_rate: int
    frame_count: int
    layout_order: int
    channels: int
    channel_ordering: str = "ACN"
    normalization: str = "SN3D"
    path: str | None = None
    source_node_type: str | None = None
    spatial_meta: dict = field(default_factory=dict)

    @classmethod
    def from_pcm(
        cls,
        pcm: np.ndarray,
        sample_rate: int,
        *,
        layout_order: int = 1,
        source_node_type: str = "AmbisonicEncode",
        spatial_meta: dict | None = None,
    ) -> AmbisonicBuffer:
        if pcm.ndim == 1:
            pcm = pcm.reshape(1, -1)
        channels, frame_count = pcm.shape
        expected = (layout_order + 1) ** 2
        if channels != expected:
            raise ValueError(f"Expected {expected} ambisonic channels for order {layout_order}, got {channels}")
        return cls(
            id=str(uuid.uuid4()),
            sample_rate=sample_rate,
            frame_count=frame_count,
            layout_order=layout_order,
            channels=channels,
            source_node_type=source_node_type,
            spatial_meta=dict(spatial_meta or {}),
        )

    def to_meta(self) -> dict:
        return {
            "id": self.id,
            "type": "AMBISONICS",
            "sample_rate": self.sample_rate,
            "frame_count": self.frame_count,
            "layout_order": self.layout_order,
            "channels": self.channels,
            "channel_layout": "ambisonics",
            "channel_ordering": self.channel_ordering,
            "normalization": self.normalization,
            "encoding_scheme": f"FOA AmbiX (ACN/SN3D)" if self.layout_order == 1 else f"HOA order {self.layout_order} AmbiX",
            "source_node_type": self.source_node_type,
            "spatial_meta": self.spatial_meta,
            "created_at": datetime.now(UTC).isoformat(),
        }


def encode_foa_from_audio(pcm: np.ndarray) -> np.ndarray:
    """Encode mono or stereo audio into first-order ambisonics (4 channels, ACN)."""
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    mono = pcm.mean(axis=0)
    w = mono.copy()
    if pcm.shape[0] >= 2:
        x = (pcm[0] - pcm[1]) * 0.5
        y = np.zeros_like(mono)
    else:
        x = mono.copy()
        y = np.zeros_like(mono)
    z = np.zeros_like(mono)
    return np.vstack([w, y, z, x])


def decode_foa_to_stereo(pcm: np.ndarray) -> np.ndarray:
    """Decode FOA (ACN: W,Y,Z,X) to stereo using a simple horizontal decoder."""
    if pcm.shape[0] < 4:
        raise ValueError("FOA decode requires at least 4 channels")
    w, _y, _z, x = pcm[0], pcm[1], pcm[2], pcm[3]
    left = 0.5 * (w + x)
    right = 0.5 * (w - x)
    return np.vstack([left, right])


def rotate_foa_yaw(pcm: np.ndarray, yaw_deg: float) -> np.ndarray:
    """Rotate FOA soundfield around the vertical axis (yaw in degrees)."""
    if pcm.shape[0] < 4:
        return pcm
    yaw = math.radians(yaw_deg)
    cos_t, sin_t = math.cos(yaw), math.sin(yaw)
    out = pcm.copy()
    y, x = out[1], out[3]
    out[1] = cos_t * y + sin_t * x
    out[3] = -sin_t * y + cos_t * x
    return out
