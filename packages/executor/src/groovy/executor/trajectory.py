from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import numpy as np

TrajectorySource = Literal["authored", "extracted"]


@dataclass
class TrajectoryBuffer:
    """Listener-relative Cartesian XYZ trajectory (Multi-ACCDOA convention)."""

    id: str
    sample_rate: int
    frame_count: int
    points: list[dict[str, float]]
    source: TrajectorySource = "authored"
    object_id: str = "obj_0"
    path: str | None = None
    source_node_type: str | None = None
    spatial_meta: dict = field(default_factory=dict)

    def to_meta(self) -> dict:
        return {
            "id": self.id,
            "type": "TRAJECTORY",
            "sample_rate": self.sample_rate,
            "frame_count": self.frame_count,
            "point_count": len(self.points),
            "source": self.source,
            "object_id": self.object_id,
            "source_node_type": self.source_node_type,
            "spatial_meta": self.spatial_meta,
            "created_at": datetime.now(UTC).isoformat(),
        }

    def to_api(self) -> dict[str, Any]:
        duration = self.frame_count / max(self.sample_rate, 1)
        return {
            **self.to_meta(),
            "duration": duration,
            "points": self.points,
        }

    @classmethod
    def from_points(
        cls,
        points: list[dict[str, float]],
        *,
        sample_rate: int,
        frame_count: int | None = None,
        source: TrajectorySource = "authored",
        object_id: str = "obj_0",
        source_node_type: str = "TrajectoryAuthor",
        spatial_meta: dict | None = None,
    ) -> TrajectoryBuffer:
        cleaned = _normalize_points(points)
        if frame_count is None:
            if cleaned:
                frame_count = max(2, int(math.ceil(cleaned[-1]["t_sec"] * sample_rate)))
            else:
                frame_count = sample_rate
        return cls(
            id=str(uuid.uuid4()),
            sample_rate=int(sample_rate),
            frame_count=int(frame_count),
            points=cleaned,
            source=source,
            object_id=object_id,
            source_node_type=source_node_type,
            spatial_meta=dict(spatial_meta or {}),
        )

    def sample_at(self, t_sec: float) -> tuple[float, float, float]:
        """Piecewise-linear XYZ at absolute time (seconds), unit-normalized."""
        if not self.points:
            return (0.0, 0.0, 1.0)
        if len(self.points) == 1:
            return _unit_xyz(float(self.points[0]["x"]), float(self.points[0]["y"]), float(self.points[0]["z"]))
        times = [float(p["t_sec"]) for p in self.points]
        if t_sec <= times[0]:
            p = self.points[0]
            return _unit_xyz(float(p["x"]), float(p["y"]), float(p["z"]))
        if t_sec >= times[-1]:
            p = self.points[-1]
            return _unit_xyz(float(p["x"]), float(p["y"]), float(p["z"]))
        for i in range(len(times) - 1):
            t0, t1 = times[i], times[i + 1]
            if t0 <= t_sec <= t1:
                alpha = 0.0 if t1 <= t0 else (t_sec - t0) / (t1 - t0)
                a, b = self.points[i], self.points[i + 1]
                return _unit_xyz(
                    float(a["x"]) + alpha * (float(b["x"]) - float(a["x"])),
                    float(a["y"]) + alpha * (float(b["y"]) - float(a["y"])),
                    float(a["z"]) + alpha * (float(b["z"]) - float(a["z"])),
                )
        p = self.points[-1]
        return _unit_xyz(float(p["x"]), float(p["y"]), float(p["z"]))

    def resample_xyz(self, frame_count: int) -> np.ndarray:
        """Return (3, frame_count) XYZ samples spanning [0, duration]."""
        frame_count = max(2, int(frame_count))
        duration = self.frame_count / max(self.sample_rate, 1)
        times = np.linspace(0.0, duration, frame_count)
        out = np.zeros((3, frame_count), dtype=np.float64)
        for i, t in enumerate(times):
            x, y, z = self.sample_at(float(t))
            out[0, i] = x
            out[1, i] = y
            out[2, i] = z
        return out


def _normalize_points(points: Any) -> list[dict[str, float]]:
    raw = points
    if isinstance(raw, str):
        text = raw.strip()
        if text:
            try:
                raw = json.loads(text)
            except json.JSONDecodeError:
                raw = None
        else:
            raw = None
    parsed: list[dict[str, float]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                t_sec = float(item.get("t_sec", item.get("t", 0.0)))
                x = float(item.get("x", 0.0))
                y = float(item.get("y", 0.0))
                z = float(item.get("z", 1.0))
            except (TypeError, ValueError):
                continue
            parsed.append({"t_sec": max(0.0, t_sec), "x": x, "y": y, "z": z})
    if not parsed:
        return [{"t_sec": 0.0, "x": 0.707, "y": 0.0, "z": 0.707}, {"t_sec": 1.0, "x": -0.707, "y": 0.0, "z": 0.707}]
    parsed.sort(key=lambda p: p["t_sec"])
    deduped: list[dict[str, float]] = []
    for p in parsed:
        if deduped and abs(deduped[-1]["t_sec"] - p["t_sec"]) < 1e-9:
            deduped[-1] = p
        else:
            deduped.append(p)
    return deduped


def rescale_trajectory_points(points: Any, duration_sec: float) -> list[dict[str, float]]:
    """Stretch/compress keyframe times so the path spans ``duration_sec`` (audio lock)."""
    duration_sec = max(0.05, float(duration_sec))
    parsed = _normalize_points(points)
    if len(parsed) < 2:
        return parsed
    t_max = float(parsed[-1]["t_sec"])
    if t_max <= 1e-9:
        n = len(parsed)
        return [
            {**p, "t_sec": duration_sec * (i / max(n - 1, 1))}
            for i, p in enumerate(parsed)
        ]
    scale = duration_sec / t_max
    if abs(scale - 1.0) < 1e-6:
        return parsed
    return [{**p, "t_sec": float(p["t_sec"]) * scale} for p in parsed]


def _unit_xyz(x: float, y: float, z: float) -> tuple[float, float, float]:
    norm = math.sqrt(x * x + y * y + z * z)
    if norm < 1e-12:
        return (0.0, 0.0, 1.0)
    return (x / norm, y / norm, z / norm)


def xyz_to_azimuth_elevation(x: float, y: float, z: float) -> tuple[float, float]:
    """Convert Cartesian DOA to azimuth/elevation degrees (0° = front, +az = left)."""
    az = math.degrees(math.atan2(x, z))
    horiz = math.hypot(x, z)
    el = math.degrees(math.atan2(y, horiz)) if horiz > 1e-12 or abs(y) > 1e-12 else 0.0
    return az, el


def azimuth_elevation_to_xyz(azimuth_deg: float, elevation_deg: float = 0.0) -> tuple[float, float, float]:
    """Azimuth degrees: 0 = front, + = left, − = right (Multi-ACCDOA x)."""
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    cos_el = math.cos(el)
    x = cos_el * math.sin(az)
    y = math.sin(el)
    z = cos_el * math.cos(az)
    return x, y, z


def build_linear_trajectory(
    *,
    start_xyz: tuple[float, float, float],
    end_xyz: tuple[float, float, float],
    duration_sec: float,
    sample_rate: int,
    source_node_type: str = "TrajectoryAuthor",
) -> TrajectoryBuffer:
    """Build a dense unit-sphere path so panel paths match FOA encode normalization."""
    duration_sec = max(0.05, float(duration_sec))
    frame_count = max(2, int(round(duration_sec * sample_rate)))
    sx, sy, sz = _unit_xyz(*start_xyz)
    ex, ey, ez = _unit_xyz(*end_xyz)
    # Dense keypoints (~50 Hz) so SVG path follows the unit arc, not a chord.
    steps = max(2, int(round(duration_sec * 50)))
    points: list[dict[str, float]] = []
    for i in range(steps):
        alpha = i / (steps - 1)
        t_sec = duration_sec * alpha
        ux, uy, uz = _unit_xyz(
            sx + alpha * (ex - sx),
            sy + alpha * (ey - sy),
            sz + alpha * (ez - sz),
        )
        points.append({"t_sec": t_sec, "x": ux, "y": uy, "z": uz})
    return TrajectoryBuffer.from_points(
        points,
        sample_rate=sample_rate,
        frame_count=frame_count,
        source="authored",
        source_node_type=source_node_type,
    )
