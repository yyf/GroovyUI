"""Generate* run log (behavior / performance / hardware) for SaveGenerateLog."""

from __future__ import annotations

import platform
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class GenerateLogReport:
    """Structured GENERATE_LOG payload from a GenerateVideo / GenerateImage / GenerateMidi run."""

    id: str
    record: dict[str, Any] = field(default_factory=dict)
    socket_type: str = "GENERATE_LOG"

    def to_meta(self) -> dict[str, Any]:
        return {"id": self.id, "type": "GENERATE_LOG", **self.record}

    @classmethod
    def create(cls, record: dict[str, Any]) -> GenerateLogReport:
        report_id = str(uuid.uuid4())
        payload = {
            "schema_version": "1.0.0",
            "cache_id": report_id,
            "created_at": datetime.now(UTC).isoformat(),
            **record,
        }
        return cls(id=report_id, record=payload)


def probe_hardware() -> dict[str, Any]:
    """Best-effort host / accelerator snapshot for generation logs."""
    info: dict[str, Any] = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "python": platform.python_version(),
        "accelerator": "cpu",
        "device": "cpu",
    }
    try:
        import mlx.core as mx

        info["accelerator"] = "mlx/metal"
        info["device"] = str(mx.default_device())
        return info
    except Exception:
        pass
    try:
        import torch

        if torch.cuda.is_available():
            info["accelerator"] = "cuda"
            info["device"] = torch.cuda.get_device_name(0)
            info["cuda_device_count"] = int(torch.cuda.device_count())
            return info
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            info["accelerator"] = "mps"
            info["device"] = "mps"
            return info
    except Exception:
        pass
    return info


def image_file_info(path: Path | None, *, project_relative: str | None = None) -> dict[str, Any] | None:
    if path is None:
        return None
    info: dict[str, Any] = {
        "path": project_relative or str(path),
        "exists": path.is_file(),
        "format": path.suffix.lstrip(".").lower() or None,
    }
    if path.is_file():
        st = path.stat()
        info["bytes"] = int(st.st_size)
        try:
            from groovy.executor.image import probe_image_dimensions

            dims = probe_image_dimensions(path)
            if dims:
                info["width"], info["height"] = dims
        except Exception:
            pass
    return info


def video_file_info(path: Path | None, *, project_relative: str | None = None) -> dict[str, Any] | None:
    """Reference / conditioning VIDEO metadata (optional inlet)."""
    if path is None:
        return None
    rel = project_relative or str(path)
    info: dict[str, Any] = {
        "path": rel,
        "exists": path.is_file(),
        "format": path.suffix.lstrip(".").lower() or None,
        "media_type": (
            "video/mp4"
            if path.suffix.lower() == ".mp4"
            else (f"video/{path.suffix.lstrip('.')}" if path.suffix else None)
        ),
    }
    if path.is_file():
        info["bytes"] = int(path.stat().st_size)
        try:
            from groovy.executor.media_io import probe_video_dimensions

            dims = probe_video_dimensions(path)
            if dims:
                info["width"], info["height"] = dims
        except Exception:
            pass
    return info


def video_output_info(path: Path, *, project_relative: str) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": project_relative,
        "format": path.suffix.lstrip(".").lower() or "mp4",
        "media_type": "video/mp4" if path.suffix.lower() == ".mp4" else f"video/{path.suffix.lstrip('.')}",
        "exists": path.is_file(),
    }
    if path.is_file():
        info["bytes"] = int(path.stat().st_size)
        try:
            from groovy.executor.media_io import probe_video_dimensions

            dims = probe_video_dimensions(path)
            if dims:
                info["width"], info["height"] = dims
        except Exception:
            pass
    return info
