from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np


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
