from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np


def normalize_curve_points(
    points: Any,
    *,
    start_value: float = 0.0,
    end_value: float = 1.0,
) -> list[tuple[float, float]]:
    """Return sorted (t, v) pairs in [0,1]×ℝ. Falls back to start→end when empty."""
    parsed: list[tuple[float, float]] = []
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
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                try:
                    t = float(item.get("t", item.get("x", 0.0)))
                    v = float(item.get("v", item.get("y", 0.0)))
                except (TypeError, ValueError):
                    continue
                parsed.append((min(1.0, max(0.0, t)), float(v)))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    parsed.append((min(1.0, max(0.0, float(item[0]))), float(item[1])))
                except (TypeError, ValueError):
                    continue
    if len(parsed) < 2:
        return [(0.0, float(start_value)), (1.0, float(end_value))]
    parsed.sort(key=lambda p: p[0])
    # Ensure endpoints at 0 and 1 so the curve spans the full duration.
    if parsed[0][0] > 0.0:
        parsed.insert(0, (0.0, parsed[0][1]))
    if parsed[-1][0] < 1.0:
        parsed.append((1.0, parsed[-1][1]))
    # Collapse duplicate t by keeping last value at that t.
    deduped: list[tuple[float, float]] = []
    for t, v in parsed:
        if deduped and abs(deduped[-1][0] - t) < 1e-9:
            deduped[-1] = (t, v)
        else:
            deduped.append((t, v))
    if len(deduped) < 2:
        return [(0.0, float(start_value)), (1.0, float(end_value))]
    return deduped


def values_from_curve_points(
    points: Any,
    frame_count: int,
    *,
    start_value: float = 0.0,
    end_value: float = 1.0,
) -> np.ndarray:
    """Piecewise-linear automation samples from normalized control points."""
    frame_count = max(2, int(frame_count))
    pairs = normalize_curve_points(points, start_value=start_value, end_value=end_value)
    xs = np.asarray([p[0] for p in pairs], dtype=np.float64)
    ys = np.asarray([p[1] for p in pairs], dtype=np.float64)
    x_new = np.linspace(0.0, 1.0, frame_count)
    return np.interp(x_new, xs, ys)


@dataclass
class AutomationBuffer:
    id: str
    sample_rate: int
    frame_count: int
    values: np.ndarray
    path: str | None = None
    source_node_type: str | None = None

    def to_meta(self) -> dict:
        return {
            "id": self.id,
            "type": "AUTOMATION",
            "sample_rate": self.sample_rate,
            "frame_count": self.frame_count,
            "source_node_type": self.source_node_type,
            "created_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def from_values(
        cls,
        values: np.ndarray,
        *,
        sample_rate: int,
        source_node_type: str = "ControlCurve",
    ) -> AutomationBuffer:
        values = np.asarray(values, dtype=np.float64).reshape(-1)
        return cls(
            id=str(uuid.uuid4()),
            sample_rate=sample_rate,
            frame_count=len(values),
            values=values,
            source_node_type=source_node_type,
        )

    def resample_to(self, frame_count: int) -> np.ndarray:
        if self.frame_count == frame_count:
            return self.values.copy()
        if self.frame_count == 0:
            return np.zeros(frame_count, dtype=np.float64)
        x_old = np.linspace(0, 1, self.frame_count)
        x_new = np.linspace(0, 1, frame_count)
        return np.interp(x_new, x_old, self.values)
