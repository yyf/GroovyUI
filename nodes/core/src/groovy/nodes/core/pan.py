"""Layout-agnostic equal-power panner (mono / stereo / surround beds)."""

from __future__ import annotations

import numpy as np

from groovy.executor.audio_meta import STANDARD_CHANNEL_MAPS, channel_layout_for_channels, channel_map_for_layout

# Horizontal azimuth degrees: 0 = front, negative = left, positive = right (ITU-ish).
# LFE is None — excluded from imaging, kept silent for mono drive or passed through lightly.
SPEAKER_AZIMUTH_DEG: dict[str, float | None] = {
    "M": 0.0,
    "FL": -30.0,
    "FR": 30.0,
    "FC": 0.0,
    "LFE": None,
    "BL": -135.0,
    "BR": 135.0,
    "SL": -90.0,
    "SR": 90.0,
    "TFL": -30.0,
    "TFR": 30.0,
    "TBL": -135.0,
    "TBR": 135.0,
    "L": -30.0,
    "C": 0.0,
    "R": 30.0,
}


def resolve_output_layout(
    *,
    input_layout: str,
    input_channels: int,
    output_layout: str,
) -> str:
    """Pick the render layout; ``auto`` promotes mono → stereo for panning."""
    requested = str(output_layout or "auto").strip().lower()
    if requested in {"", "auto", "same"}:
        if input_channels == 1 or input_layout == "mono":
            return "stereo"
        return input_layout if input_layout in STANDARD_CHANNEL_MAPS else channel_layout_for_channels(
            input_channels
        )
    if requested not in STANDARD_CHANNEL_MAPS and requested != "binaural":
        raise ValueError(
            f"Pan output_layout must be auto/same or a known bed layout, not {output_layout!r}"
        )
    if requested == "binaural":
        return "stereo"
    return requested


def pan_pcm(
    pcm: np.ndarray,
    *,
    pan: float | np.ndarray,
    input_layout: str,
    output_layout: str,
) -> np.ndarray:
    """Distribute a mono drive into ``output_layout`` with equal-power gains.

    ``pan`` is scalar or per-frame array in ``[-1, 1]`` (−1 = left, +1 = right).
    Multichannel inputs collapse to a mono mid (LFE omitted from the mid).
    """
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    frames = pcm.shape[1]
    pan_vec = _as_pan_vector(pan, frames)
    drive = _mono_drive(pcm, layout=input_layout)
    labels = channel_map_for_layout(output_layout, _layout_channel_count(output_layout))
    gains = _gains_for_layout(labels, pan_vec)  # (ch, frames) or (ch, 1)
    out = gains * drive.reshape(1, -1)
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > 1.0:
        out = out / peak
    return out


def _layout_channel_count(layout: str) -> int:
    mapped = STANDARD_CHANNEL_MAPS.get(layout)
    if mapped:
        return len(mapped)
    raise ValueError(f"Unknown layout {layout!r}")


def _as_pan_vector(pan: float | np.ndarray, frames: int) -> np.ndarray:
    if np.isscalar(pan):
        value = float(np.clip(float(pan), -1.0, 1.0))
        return np.full(frames, value, dtype=np.float64)
    arr = np.asarray(pan, dtype=np.float64).reshape(-1)
    if arr.size == 1:
        return np.full(frames, float(np.clip(arr[0], -1.0, 1.0)), dtype=np.float64)
    if arr.size != frames:
        # Linear resample automation to audio length.
        x_old = np.linspace(0.0, 1.0, num=arr.size)
        x_new = np.linspace(0.0, 1.0, num=frames)
        arr = np.interp(x_new, x_old, arr)
    return np.clip(arr, -1.0, 1.0)


def _mono_drive(pcm: np.ndarray, *, layout: str) -> np.ndarray:
    if pcm.shape[0] == 1:
        return np.asarray(pcm[0], dtype=np.float64)
    labels = channel_map_for_layout(layout, pcm.shape[0])
    weights = []
    for index, label in enumerate(labels):
        if index >= pcm.shape[0]:
            break
        if SPEAKER_AZIMUTH_DEG.get(label) is None and label == "LFE":
            continue
        weights.append(pcm[index])
    if not weights:
        return np.asarray(pcm.mean(axis=0), dtype=np.float64)
    return np.asarray(np.mean(weights, axis=0), dtype=np.float64)


def _gains_for_layout(labels: list[str], pan_vec: np.ndarray) -> np.ndarray:
    """Return (channels, frames) equal-power gains for each speaker label."""
    n = len(labels)
    frames = pan_vec.shape[0]

    # Stereo / binaural: classic equal-power constant-power pan law.
    if labels == ["FL", "FR"] or labels == ["L", "R"]:
        theta = (pan_vec + 1.0) * (np.pi / 4.0)
        left = np.cos(theta)
        right = np.sin(theta)
        return np.vstack([left, right])

    if labels == ["M"]:
        return np.ones((1, frames), dtype=np.float64)

    # Surround / LRC / quad: map pan → target azimuth, cosine lobes, L2-normalize.
    # pan −1..+1 → −90°..+90° (front hemisphere); keeps dialogue imaging natural.
    target_az = pan_vec * 90.0
    gains = np.zeros((n, frames), dtype=np.float64)
    for index, label in enumerate(labels):
        az = SPEAKER_AZIMUTH_DEG.get(label)
        if az is None:
            continue  # LFE stays silent for mono drive
        # Angular distance with wrap to [-180, 180]
        delta = (az - target_az + 180.0) % 360.0 - 180.0
        lobe = np.cos(np.deg2rad(delta))
        gains[index] = np.maximum(lobe, 0.0) ** 2

    # Ensure some energy if all lobes collapsed (extreme pan on sparse layouts).
    energy = np.sqrt(np.sum(gains * gains, axis=0, keepdims=True))
    energy = np.maximum(energy, 1e-12)
    gains = gains / energy

    # Prefer nearest pair when nearly silent frames (shouldn't happen after normalize).
    return gains
