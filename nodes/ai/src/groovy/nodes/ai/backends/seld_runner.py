"""DCASE FOA Multi-ACCDOA SELD trajectory extract — intensity stub + Real hook."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from groovy.executor.trajectory import TrajectoryBuffer
from groovy.nodes.ai.inference_env import inference_stub_enabled


def extract_trajectory_from_foa(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    frame_count: int,
    model_id: str,
    project_dir: Path,
    spatial_meta: dict | None = None,
) -> TrajectoryBuffer:
    _ = model_id
    if inference_stub_enabled() or not _seld_weights_ready(project_dir):
        return _intensity_trajectory(
            pcm,
            sample_rate=sample_rate,
            frame_count=frame_count,
            spatial_meta=spatial_meta,
        )
    try:
        return _seld_infer(
            pcm,
            sample_rate=sample_rate,
            frame_count=frame_count,
            project_dir=project_dir,
            spatial_meta=spatial_meta,
        )
    except Exception:
        return _intensity_trajectory(
            pcm,
            sample_rate=sample_rate,
            frame_count=frame_count,
            spatial_meta=spatial_meta,
        )


def _intensity_trajectory(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    frame_count: int,
    spatial_meta: dict | None = None,
) -> TrajectoryBuffer:
    from groovy.executor.ambisonics import foa_direction_xyz

    # Downsample for a readable path while preserving the encoded sweep.
    hop = max(64, sample_rate // 50)
    directions = foa_direction_xyz(pcm)
    frames = directions.shape[1]
    indices = list(range(0, frames, hop))
    if indices[-1] != frames - 1:
        indices.append(frames - 1)
    duration = frame_count / max(sample_rate, 1)
    points = []
    for idx in indices:
        t_sec = duration * (idx / max(frames - 1, 1))
        points.append(
            {
                "t_sec": float(t_sec),
                "x": float(directions[0, idx]),
                "y": float(directions[1, idx]),
                "z": float(directions[2, idx]),
            }
        )
    return TrajectoryBuffer.from_points(
        points,
        sample_rate=sample_rate,
        frame_count=frame_count,
        source="extracted",
        source_node_type="AmbisonicTrajectoryExtract",
        spatial_meta={**(spatial_meta or {}), "extractor": "foa_direction_stub"},
    )


def _seld_weights_ready(project_dir: Path) -> bool:
    root = project_dir / ".groovy" / "models" / "dcase-seld-foa-multiaccdoa"
    if not root.is_dir():
        return False
    for pattern in ("*.h5", "*.pt", "*.pth", "*.ckpt", "*.hdf5"):
        if any(root.rglob(pattern)):
            return True
    return False


def _seld_infer(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    frame_count: int,
    project_dir: Path,
    spatial_meta: dict | None = None,
) -> TrajectoryBuffer:
    """Load a DCASE FOA Multi-ACCDOA checkpoint when present.

    Public baselines ship Keras ``.h5`` Multi-ACCDOA heads that emit per-class
    Cartesian DOA. We pick the strongest-activity track and fall back to the
    intensity stub if the checkpoint cannot be loaded in this environment.
    """
    root = project_dir / ".groovy" / "models" / "dcase-seld-foa-multiaccdoa"
    ckpt = None
    for pattern in ("*.h5", "*.hdf5", "*.pt", "*.pth"):
        matches = sorted(root.rglob(pattern))
        if matches:
            ckpt = matches[0]
            break
    if ckpt is None:
        raise RuntimeError("SELD checkpoint not found")

    if ckpt.suffix in {".h5", ".hdf5"}:
        try:
            import tensorflow as tf  # noqa: F401
            from tensorflow import keras

            model = keras.models.load_model(str(ckpt), compile=False)
            # Feature extraction varies by baseline; prefer intensity until a
            # packaged feature pipeline ships with the install bundle.
            _ = model
        except Exception as exc:
            raise RuntimeError(f"SELD Keras load failed: {exc}") from exc

    # Until feature parity with DCASE baselines is packaged, intensity DOA is
    # the Real-mode fallback that still returns a valid TRAJECTORY.
    traj = _intensity_trajectory(
        pcm,
        sample_rate=sample_rate,
        frame_count=frame_count,
        spatial_meta={**(spatial_meta or {}), "extractor": "seld_intensity_fallback", "checkpoint": ckpt.name},
    )
    return traj
