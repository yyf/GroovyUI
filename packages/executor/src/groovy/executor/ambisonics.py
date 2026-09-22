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
    """Encode mono or stereo audio into first-order ambisonics (4 channels, ACN).

    AmbiX ACN order: W, Y (left−right), Z (up−down), X (front−back).
    Mono is placed at front (+X). Stereo side (L−R) feeds Y.
    """
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    if pcm.shape[0] >= 2:
        mid = pcm.mean(axis=0)
        side = (pcm[0] - pcm[1]) * 0.5
        w = mid
        y = side
        z = np.zeros_like(mid)
        x = mid.copy()
    else:
        mono = pcm[0]
        w = mono.copy()
        y = np.zeros_like(mono)
        z = np.zeros_like(mono)
        x = mono.copy()
    return np.vstack([w, y, z, x])


def encode_foa_from_trajectory(
    pcm: np.ndarray,
    *,
    xyz: np.ndarray,
    sample_rate: int | None = None,
) -> np.ndarray:
    """Encode mono/stereo into FOA with per-frame Cartesian DOA (ACN/SN3D).

    ``xyz`` uses **Multi-ACCDOA** axes: +x = left, +y = up, +z = front.
    AmbiX ACN Y (positive = left) is therefore ``+x``.
    """
    del sample_rate  # reserved for future rate-aware windowing
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    mono = pcm.mean(axis=0)
    frames = mono.shape[0]
    xyz_arr = np.asarray(xyz, dtype=np.float64)
    if xyz_arr.ndim == 1:
        xyz_arr = np.broadcast_to(xyz_arr.reshape(3, 1), (3, frames)).copy()
    elif xyz_arr.shape[1] != frames:
        old_t = np.linspace(0.0, 1.0, xyz_arr.shape[1])
        new_t = np.linspace(0.0, 1.0, frames)
        xyz_arr = np.vstack([np.interp(new_t, old_t, xyz_arr[i]) for i in range(3)])
    norms = np.linalg.norm(xyz_arr, axis=0)
    norms = np.where(norms < 1e-12, 1.0, norms)
    left = xyz_arr[0] / norms
    up = xyz_arr[1] / norms
    front = xyz_arr[2] / norms
    w = mono
    # AmbiX ACN: W, Y(left)=+left, Z(up), X(front)
    return np.vstack([w, left * mono, up * mono, front * mono])


def foa_intensity_xyz(pcm: np.ndarray, *, hop: int = 512) -> np.ndarray:
    """Estimate per-hop Cartesian DOA from FOA (legacy intensity average)."""
    if pcm.ndim != 2 or pcm.shape[0] < 4:
        raise ValueError("FOA intensity requires planar (4+, frames) PCM")
    directions = foa_direction_xyz(pcm)
    frames = directions.shape[1]
    hop = max(1, int(hop))
    indices = list(range(0, frames, hop))
    if not indices:
        indices = [0]
    out = np.zeros((3, len(indices)), dtype=np.float64)
    for i, start in enumerate(indices):
        end = min(frames, start + hop)
        chunk = directions[:, start:end]
        out[:, i] = np.median(chunk, axis=1)
        norm = float(np.linalg.norm(out[:, i]))
        if norm < 1e-12:
            out[:, i] = (0.0, 0.0, 1.0)
        else:
            out[:, i] /= norm
    return out


def foa_direction_xyz(pcm: np.ndarray) -> np.ndarray:
    """Per-frame XYZ from FOA AmbiX (invert of encode_foa_from_trajectory).

    AmbiX ACN ``W,Y,Z,X`` → Multi-ACCDOA ``(left, up, front)``.

    Uses ``sign(W)·(Y,Z,X)`` so negative carriers do not flip DOA 180°, then
    forward/back-fills near-silent frames (W≈0) so extract paths stay visible.
    """
    if pcm.ndim != 2 or pcm.shape[0] < 4:
        raise ValueError("FOA direction requires planar (4+, frames) PCM")
    w, y_left, z_up, x_front = pcm[0], pcm[1], pcm[2], pcm[3]
    frames = w.shape[0]
    sgn = np.sign(w)
    sgn = np.where(sgn == 0.0, 1.0, sgn)
    raw = np.vstack([y_left * sgn, z_up * sgn, x_front * sgn])
    norms = np.linalg.norm(raw, axis=0)
    valid = norms >= 1e-10
    unit = np.zeros((3, frames), dtype=np.float64)
    unit[:, valid] = raw[:, valid] / norms[valid]

    out = np.zeros((3, frames), dtype=np.float64)
    out[2, :] = 1.0
    last = np.asarray([0.0, 0.0, 1.0], dtype=np.float64)
    first_valid = -1
    for i in range(frames):
        if valid[i]:
            last = unit[:, i]
            out[:, i] = last
            if first_valid < 0:
                first_valid = i
        else:
            out[:, i] = last
    if first_valid > 0:
        out[:, :first_valid] = out[:, first_valid : first_valid + 1]
    return out


def decode_foa_to_stereo(pcm: np.ndarray) -> np.ndarray:
    """Decode FOA AmbiX (ACN: W,Y,Z,X) to stereo using horizontal Y (left−right)."""
    if pcm.shape[0] < 4:
        raise ValueError("FOA decode requires at least 4 channels")
    w, y, _z, _x = pcm[0], pcm[1], pcm[2], pcm[3]
    left = 0.5 * (w + y)
    right = 0.5 * (w - y)
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
