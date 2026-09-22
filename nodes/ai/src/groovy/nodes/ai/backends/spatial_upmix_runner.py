"""Binaural / Atmos-bed upmix — stereo2spatial Real path + deterministic stubs."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

from groovy.nodes.ai.inference_env import inference_stub_enabled

STUB_BINAURAL_IDS = frozenset({"hrtf-binaural-v0"})
STUB_ATMOS_IDS = frozenset({"stereo-atmos-bed-v0"})
REAL_BINAURAL_IDS = frozenset({"stereo2spatial-v2-binaural"})
REAL_ATMOS_IDS = frozenset({"stereo2spatial-v1"})

_MODEL_SAMPLE_RATE = 48_000


def binaural_render_pcm(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str,
    project_dir: Path,
    strength: float = 0.45,
) -> tuple[np.ndarray, str]:
    """Return (2, frames) binaural PCM and renderer label."""
    if model_id in STUB_BINAURAL_IDS or inference_stub_enabled():
        return (
            stereo_to_binaural_crossfeed(pcm, sample_rate=sample_rate, strength=strength),
            "crossfeed-stub",
        )
    if model_id in REAL_BINAURAL_IDS and _stereo2spatial_weights_ready(
        project_dir, model_id
    ):
        try:
            out = _stereo2spatial_infer(
                pcm,
                sample_rate=sample_rate,
                model_id=model_id,
                project_dir=project_dir,
                expected_channels=2,
            )
            return out, "stereo2spatial-v2-binaural"
        except Exception:
            pass
    return (
        stereo_to_binaural_crossfeed(pcm, sample_rate=sample_rate, strength=strength),
        "crossfeed-stub-fallback",
    )


def spatial_upmix_pcm(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str,
    project_dir: Path,
    layout: str = "7.1.4",
) -> tuple[np.ndarray, str]:
    """Return multichannel bed PCM and upmix label for the requested layout."""
    layout = str(layout or "7.1.4").strip().lower()
    if model_id in STUB_ATMOS_IDS or inference_stub_enabled():
        bed = stereo_to_atmos_bed_714(pcm, sample_rate=sample_rate)
        return _fold_bed_layout(bed, layout), "stereo-atmos-bed-stub"

    if model_id in REAL_ATMOS_IDS and _stereo2spatial_weights_ready(project_dir, model_id):
        try:
            bed = _stereo2spatial_infer(
                pcm,
                sample_rate=sample_rate,
                model_id=model_id,
                project_dir=project_dir,
                expected_channels=12,
            )
            return _fold_bed_layout(bed, layout), "stereo2spatial-v1"
        except Exception:
            pass

    bed = stereo_to_atmos_bed_714(pcm, sample_rate=sample_rate)
    return _fold_bed_layout(bed, layout), "stereo-atmos-bed-stub-fallback"


def stereo_to_binaural_crossfeed(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    strength: float = 0.45,
    delay_ms: float = 0.35,
) -> np.ndarray:
    """Bauer-style crossfeed → 2ch buffer labeled binaural (stub HRTF stand-in).

    Not a measured HRTF — enough for headphone spatial audition + provenance.
    """
    if pcm.ndim == 1:
        pcm = np.vstack([pcm, pcm])
    elif pcm.shape[0] == 1:
        pcm = np.vstack([pcm[0], pcm[0]])
    elif pcm.shape[0] > 2:
        pcm = pcm[:2]

    left = np.asarray(pcm[0], dtype=np.float64)
    right = np.asarray(pcm[1], dtype=np.float64)
    delay = max(1, int(round(sample_rate * max(0.0, delay_ms) * 0.001)))
    strength = float(np.clip(strength, 0.0, 0.95))

    def _delay(x: np.ndarray) -> np.ndarray:
        if delay <= 0:
            return x
        out = np.zeros_like(x)
        out[delay:] = x[:-delay]
        return out

    # Mild HF shelf on contralateral path (cheap HRTF-ish coloration).
    b, a = signal.butter(1, min(0.45, 3000.0 / max(sample_rate / 2, 1)), btype="low")
    cross_l = signal.lfilter(b, a, _delay(right))
    cross_r = signal.lfilter(b, a, _delay(left))
    out_l = left + strength * cross_l
    out_r = right + strength * cross_r
    peak = max(float(np.max(np.abs(out_l))), float(np.max(np.abs(out_r))), 1e-12)
    if peak > 1.0:
        out_l /= peak
        out_r /= peak
    return np.vstack([out_l, out_r])


def stereo_to_atmos_bed_714(pcm: np.ndarray, *, sample_rate: int) -> np.ndarray:
    """Heuristic stereo → 7.1.4 Atmos bed (12ch) — neural-upmix stub.

    Channel order matches ``audio_meta`` / Meter: FL FR FC LFE BL BR SL SR TFL TFR TBL TBR.
    """
    if pcm.ndim == 1:
        left = right = np.asarray(pcm, dtype=np.float64)
    elif pcm.shape[0] == 1:
        left = right = np.asarray(pcm[0], dtype=np.float64)
    else:
        left = np.asarray(pcm[0], dtype=np.float64)
        right = np.asarray(pcm[1], dtype=np.float64)

    mid = 0.5 * (left + right)
    # Simple LFE: low-passed mid at reduced gain.
    b, a = signal.butter(2, min(0.2, 120.0 / max(sample_rate / 2, 1)), btype="low")
    lfe = 0.35 * signal.lfilter(b, a, mid)

    fl, fr = left, right
    fc = 0.70710678 * mid
    bl, br = 0.55 * left, 0.55 * right
    sl, sr = 0.45 * left, 0.45 * right
    tfl, tfr = 0.35 * left, 0.35 * right
    tbl, tbr = 0.28 * left, 0.28 * right

    bed = np.vstack([fl, fr, fc, lfe, bl, br, sl, sr, tfl, tfr, tbl, tbr])
    peak = float(np.max(np.abs(bed))) if bed.size else 0.0
    if peak > 1.0:
        bed = bed / peak
    return bed


def _fold_bed_layout(bed: np.ndarray, layout: str) -> np.ndarray:
    if layout == "7.1.4":
        return bed
    if layout == "5.1":
        return bed[:6]
    if layout == "7.1":
        return bed[:8]
    raise ValueError(f"SpatialUpmix supports 7.1.4, 7.1, or 5.1 — not {layout}")


def _stereo2spatial_weights_ready(project_dir: Path, model_id: str) -> bool:
    root = project_dir / ".groovy" / "models" / model_id
    if not (root / "config.json").is_file():
        return False
    if not (root / "model.safetensors").is_file():
        return False
    if model_id in REAL_ATMOS_IDS:
        vae_w = root / "vae" / "ear_vae_v2_48k.pyt"
        vae_c = root / "vae" / "ear_vae_v2.json"
        if not vae_w.is_file() or not vae_c.is_file():
            return False
    return True


def _stereo2spatial_infer(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    model_id: str,
    project_dir: Path,
    expected_channels: int,
) -> np.ndarray:
    """Run stereo2spatial bundle inference via temp WAV I/O."""
    from stereo2spatial.inference.export_bundle import (
        build_train_config_from_bundle_payload,
        load_inference_bundle_payload,
        resolve_bundle_vae_paths,
        resolve_inference_config_path,
    )
    from stereo2spatial.inference.runner import run_inference

    checkpoint = project_dir / ".groovy" / "models" / model_id
    config_path = resolve_inference_config_path(checkpoint)
    if config_path is None:
        raise RuntimeError(f"{model_id}: missing inference config.json")

    payload = load_inference_bundle_payload(config_path)
    config = build_train_config_from_bundle_payload(
        payload,
        bundle_root=checkpoint,
    )
    vae_ckpt, vae_cfg = resolve_bundle_vae_paths(checkpoint)

    inference_section = payload.get("inference") if isinstance(payload, dict) else None
    if not isinstance(inference_section, dict):
        inference_section = {}

    target_sr = int(inference_section.get("sample_rate", _MODEL_SAMPLE_RATE))
    chunk_seconds = inference_section.get("chunk_seconds", 10.0)
    if chunk_seconds is not None:
        chunk_seconds = float(chunk_seconds)
    overlap_seconds = float(inference_section.get("overlap_seconds", 2.0))
    solver = str(inference_section.get("solver", "heun"))
    solver_steps = inference_section.get("solver_steps")
    if solver_steps is not None:
        solver_steps = int(solver_steps)
    sampling_order = str(inference_section.get("sampling_order", "timestep_major"))
    seed = int(inference_section.get("seed", 1337))

    working = _ensure_stereo_planar(pcm)
    if sample_rate != target_sr:
        working = _resample_planar(working, sample_rate, target_sr)

    with tempfile.TemporaryDirectory(prefix="groovy-s2s-") as tmp:
        tmp_path = Path(tmp)
        in_wav = tmp_path / "input.wav"
        out_wav = tmp_path / "output.wav"
        sf.write(in_wav, working.T.astype(np.float32), target_sr)

        run_inference(
            config=config,
            checkpoint=checkpoint,
            input_audio_path=in_wav,
            output_audio_path=out_wav,
            sample_rate=target_sr,
            chunk_seconds=chunk_seconds,
            overlap_seconds=overlap_seconds,
            solver=solver,  # type: ignore[arg-type]
            solver_steps=solver_steps,
            solver_rtol=float(inference_section.get("solver_rtol", 1e-5)),
            solver_atol=float(inference_section.get("solver_atol", 1e-5)),
            seed=seed,
            device=None,
            show_progress=False,
            normalize_peak=True,
            mix_style=None,
            mix_style_preset=None,
            vae_checkpoint_path=vae_ckpt,
            vae_config_path=vae_cfg,
            sampling_order=sampling_order,  # type: ignore[arg-type]
        )

        rendered, out_sr = sf.read(out_wav, always_2d=True)
        out = np.asarray(rendered.T, dtype=np.float64)
        if out.shape[0] != expected_channels:
            raise RuntimeError(
                f"{model_id}: expected {expected_channels}ch, got {out.shape[0]}"
            )
        if int(out_sr) != sample_rate:
            out = _resample_planar(out, int(out_sr), sample_rate)
        # Match input length when resampling drifts by a few samples.
        target_frames = pcm.shape[-1] if pcm.ndim > 1 else len(pcm)
        if out.shape[1] != target_frames:
            if out.shape[1] > target_frames:
                out = out[:, :target_frames]
            else:
                pad = np.zeros((out.shape[0], target_frames - out.shape[1]), dtype=out.dtype)
                out = np.hstack([out, pad])
        return out


def _ensure_stereo_planar(pcm: np.ndarray) -> np.ndarray:
    if pcm.ndim == 1:
        return np.vstack([pcm, pcm]).astype(np.float64)
    if pcm.shape[0] == 1:
        return np.vstack([pcm[0], pcm[0]]).astype(np.float64)
    return np.asarray(pcm[:2], dtype=np.float64)


def _resample_planar(pcm: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return pcm
    channels = []
    for ch in pcm:
        channels.append(signal.resample_poly(ch, to_rate, from_rate))
    return np.vstack(channels)
