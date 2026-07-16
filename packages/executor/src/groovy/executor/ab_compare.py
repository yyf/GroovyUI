from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from groovy.executor.cache import CacheStore


@dataclass
class ClipMetrics:
    cache_id: str
    label: str
    duration_sec: float
    sample_rate: int
    channels: int
    channel_layout: str
    peak: float
    rms: float
    lufs: float | None
    source_node_type: str | None
    peaks: list[float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mono(pcm: np.ndarray) -> np.ndarray:
    if pcm.ndim == 1:
        return pcm.astype(np.float64)
    return pcm.mean(axis=0).astype(np.float64)


def _integrated_lufs(pcm: np.ndarray, sample_rate: int) -> float | None:
    try:
        import pyloudnorm as pyln
    except ImportError:
        return None
    if pcm.size == 0:
        return None
    if pcm.ndim == 1:
        interleaved = pcm.astype(np.float64)
    else:
        interleaved = pcm.T.reshape(-1).astype(np.float64)
    meter = pyln.Meter(sample_rate)
    return float(meter.integrated_loudness(interleaved))


def measure_clip(cache: CacheStore, cache_id: str, *, label: str, peak_width: int = 256) -> ClipMetrics:
    meta = cache.read_meta(cache_id)
    _, pcm = cache.load_audio(cache_id)
    mono = _mono(pcm)
    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(mono)))) if mono.size else 0.0
    waveform = cache.waveform_peaks(cache_id, width=peak_width)
    return ClipMetrics(
        cache_id=cache_id,
        label=label,
        duration_sec=float(waveform.get("duration", 0.0)),
        sample_rate=int(meta.get("sample_rate", 0)),
        channels=int(meta.get("channels", 1)),
        channel_layout=str(meta.get("channel_layout", "mono")),
        peak=peak,
        rms=rms,
        lufs=_integrated_lufs(pcm, int(meta.get("sample_rate", 48000))),
        source_node_type=meta.get("source_node_type"),
        peaks=[float(v) for v in waveform.get("peaks", [])],
    )


def _resample_peaks(peaks: list[float], width: int) -> np.ndarray:
    if not peaks:
        return np.zeros(width, dtype=np.float64)
    arr = np.asarray(peaks, dtype=np.float64)
    if arr.size == width:
        return arr
    indices = np.linspace(0, arr.size - 1, width)
    return np.interp(indices, np.arange(arr.size), arr)


def compare_waveform_peaks(peaks_a: list[float], peaks_b: list[float]) -> dict[str, float]:
    width = 256
    a = _resample_peaks(peaks_a, width)
    b = _resample_peaks(peaks_b, width)
    max_val = max(float(np.max(a)), float(np.max(b)), 1e-9)
    a_norm = a / max_val
    b_norm = b / max_val
    residual = a_norm - b_norm
    raw_peak_a = float(np.max(a))
    raw_peak_b = float(np.max(b))
    return {
        "mean_abs_diff": float(np.mean(np.abs(residual))),
        "max_abs_diff": float(np.max(np.abs(residual))),
        "correlation": float(np.corrcoef(a_norm, b_norm)[0, 1]) if width > 1 else 1.0,
        "raw_peak_delta_db": round(_to_db(raw_peak_b) - _to_db(raw_peak_a), 2),
    }


def compare_pcm(pcm_a: np.ndarray, pcm_b: np.ndarray) -> dict[str, Any]:
    a = _mono(pcm_a)
    b = _mono(pcm_b)
    n = min(len(a), len(b))
    if n == 0:
        return {
            "identical": True,
            "aligned_frames": 0,
            "max_sample_diff": 0.0,
            "rms_residual": 0.0,
            "snr_db": None,
            "changed_sample_pct": 0.0,
            "duration_delta_frames": len(b) - len(a),
        }
    a_aligned = a[:n]
    b_aligned = b[:n]
    residual = b_aligned - a_aligned
    max_sample_diff = float(np.max(np.abs(residual)))
    rms_residual = float(np.sqrt(np.mean(np.square(residual))))
    rms_a = float(np.sqrt(np.mean(np.square(a_aligned)))) or 1e-12
    snr_db = float(20.0 * np.log10(rms_a / max(rms_residual, 1e-12)))
    identical = max_sample_diff < 1e-7
    changed_sample_pct = float(np.mean(np.abs(residual) > 1e-5) * 100.0)
    return {
        "identical": identical,
        "aligned_frames": n,
        "max_sample_diff": max_sample_diff,
        "rms_residual": rms_residual,
        "snr_db": snr_db,
        "changed_sample_pct": round(changed_sample_pct, 2),
        "duration_delta_frames": len(b) - len(a),
    }


def compare_pcm_with_rate(
    pcm_a: np.ndarray,
    pcm_b: np.ndarray,
    *,
    sample_rate_a: int,
    sample_rate_b: int,
) -> dict[str, Any]:
    stats = compare_pcm(pcm_a, pcm_b)
    frames_delta = stats.pop("duration_delta_frames")
    rate = sample_rate_a or sample_rate_b or 48000
    stats["duration_delta_sec"] = round(frames_delta / rate, 3)
    return stats


def compare_metrics(
    a: ClipMetrics,
    b: ClipMetrics,
    *,
    pcm_a: np.ndarray,
    pcm_b: np.ndarray,
) -> dict[str, Any]:
    waveform = compare_waveform_peaks(a.peaks, b.peaks)
    pcm = compare_pcm_with_rate(pcm_a, pcm_b, sample_rate_a=a.sample_rate, sample_rate_b=b.sample_rate)
    return {
        "same_cache": a.cache_id == b.cache_id,
        "duration_delta_sec": round(b.duration_sec - a.duration_sec, 3),
        "peak_delta_db": round(_to_db(b.peak) - _to_db(a.peak), 2),
        "rms_delta_db": round(_to_db(b.rms) - _to_db(a.rms), 2),
        "lufs_delta": None if a.lufs is None or b.lufs is None else round(b.lufs - a.lufs, 2),
        "waveform": waveform,
        "pcm": pcm,
        "same_layout": a.channel_layout == b.channel_layout,
        "same_sample_rate": a.sample_rate == b.sample_rate,
    }


def _to_db(value: float) -> float:
    return 20.0 * np.log10(max(value, 1e-12))


def _fmt_db(value: float) -> str:
    return f"{value:.2f} dBFS"


def _fmt_lufs(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f} LUFS"


def synthesize_verdict(comparison: dict[str, Any]) -> tuple[str, str]:
    if comparison.get("same_cache"):
        return (
            "no_difference",
            "No difference found — both nodes point to the same cached audio. "
            "Preview nodes pass audio through without a new render; compare upstream nodes "
            "(e.g. LoadAudio vs Denoise, or Denoise vs Normalize).",
        )
    pcm = comparison["pcm"]
    if pcm["identical"]:
        return ("no_difference", "No difference found — the aligned samples are identical.")

    bullets = collect_difference_bullets(comparison)
    if not bullets:
        return (
            "subtle",
            "Only subtle differences detected — levels and shape are very close; changes may be hard to hear.",
        )
    if pcm["changed_sample_pct"] > 25 or abs(comparison["peak_delta_db"]) > 3 or pcm["max_sample_diff"] > 0.05:
        return ("substantial", f"Found {len(bullets)} clear difference(s) between A and B.")
    return ("moderate", f"Found {len(bullets)} difference(s) between A and B.")


def collect_difference_bullets(comparison: dict[str, Any]) -> list[str]:
    bullets: list[str] = []
    if comparison.get("same_cache"):
        return bullets

    pcm = comparison["pcm"]
    if pcm["identical"]:
        return bullets

    if abs(comparison["duration_delta_sec"]) >= 0.01:
        bullets.append(f"Duration differs by {comparison['duration_delta_sec']:+.2f}s.")
    if abs(comparison["peak_delta_db"]) >= 0.3:
        bullets.append(f"Peak level differs by {comparison['peak_delta_db']:+.1f} dB.")
    if abs(comparison["rms_delta_db"]) >= 0.3:
        bullets.append(f"RMS level differs by {comparison['rms_delta_db']:+.1f} dB.")
    lufs_delta = comparison.get("lufs_delta")
    if lufs_delta is not None and abs(lufs_delta) >= 0.3:
        bullets.append(f"Integrated loudness differs by {lufs_delta:+.1f} LU.")
    if pcm["max_sample_diff"] >= 1e-5:
        bullets.append(f"Max sample delta is {pcm['max_sample_diff']:.4f} ({pcm['changed_sample_pct']:.1f}% of samples changed).")
    if pcm.get("snr_db") is not None and pcm["snr_db"] < 45:
        bullets.append(f"Residual SNR is {pcm['snr_db']:.1f} dB — waveforms diverge audibly.")

    wf = comparison["waveform"]
    if wf["mean_abs_diff"] >= 0.08:
        bullets.append(
            f"Waveform envelope differs (correlation {wf['correlation']:.2f}, mean abs diff {wf['mean_abs_diff']:.3f})."
        )
    elif abs(wf["raw_peak_delta_db"]) >= 0.3:
        bullets.append(f"Waveform peak envelope differs by {wf['raw_peak_delta_db']:+.1f} dB.")

    if not comparison["same_sample_rate"]:
        bullets.append("Sample rates differ.")
    if not comparison["same_layout"]:
        bullets.append("Channel layouts differ.")
    return bullets


def build_signal_facts(
    a: ClipMetrics,
    b: ClipMetrics,
    comparison: dict[str, Any],
    *,
    difference_bullets: list[str] | None = None,
    verdict: str | None = None,
    verdict_summary: str | None = None,
) -> list[str]:
    # Measurement rows only — verdict / difference bullets are returned separately.
    _ = (difference_bullets, verdict, verdict_summary)
    facts: list[str] = []
    facts.append(
        f"Duration: A {a.duration_sec:.2f}s → B {b.duration_sec:.2f}s "
        f"({comparison['duration_delta_sec']:+.2f}s)"
    )
    facts.append(f"Peak level: A {_fmt_db(_to_db(a.peak))}, B {_fmt_db(_to_db(b.peak))}")
    facts.append(f"RMS level: A {_fmt_db(_to_db(a.rms))}, B {_fmt_db(_to_db(b.rms))}")
    if a.lufs is not None and b.lufs is not None:
        facts.append(f"Integrated loudness: A {_fmt_lufs(a.lufs)}, B {_fmt_lufs(b.lufs)}")
    pcm = comparison["pcm"]
    facts.append(
        f"Sample comparison: max delta {pcm['max_sample_diff']:.6f}, "
        f"{pcm['changed_sample_pct']:.1f}% samples changed"
    )
    wf = comparison["waveform"]
    facts.append(
        f"Waveform shape: correlation {wf['correlation']:.2f}, "
        f"mean abs diff {wf['mean_abs_diff']:.3f}"
    )
    if a.source_node_type or b.source_node_type:
        facts.append(f"Source nodes: A {a.source_node_type or 'unknown'}, B {b.source_node_type or 'unknown'}")
    if a.cache_id == b.cache_id:
        facts.append(f"Same cache id: {a.cache_id}")
    return facts


def build_transcript_facts(text_a: str, text_b: str) -> list[str]:
    facts: list[str] = []
    facts.append(f"Transcript A: {text_a.strip() or '(empty)'}")
    facts.append(f"Transcript B: {text_b.strip() or '(empty)'}")
    if text_a.strip() == text_b.strip():
        facts.append("Transcripts match — spoken wording appears unchanged (audio may still differ).")
    elif text_a.strip() and text_b.strip():
        facts.append("Transcripts differ — wording or content changed between A and B.")
    return facts


def format_compare_answer(
    *,
    question: str | None,
    label_a: str,
    label_b: str,
    model_name: str,
    facts: list[str],
    verdict_summary: str,
    differences: list[str] | None = None,
) -> str:
    prompt = (question or "What are the differences between A and B?").strip()
    lines = [
        prompt,
        "",
        verdict_summary,
        "",
        f"Analysis model: {model_name}",
        f"Clips: {label_a} (A) vs {label_b} (B)",
    ]
    if differences:
        lines.extend(["", "Detected differences:"])
        lines.extend(f"• {bullet}" for bullet in differences)
    if facts:
        lines.extend(["", "Measurements:"])
        lines.extend(facts)
    return "\n".join(lines)


def analyze_signal_pair(
    cache: CacheStore,
    *,
    cache_id_a: str,
    cache_id_b: str,
    label_a: str,
    label_b: str,
    question: str | None = None,
    model_name: str = "Groovy Signal Diff",
) -> dict[str, Any]:
    metrics_a = measure_clip(cache, cache_id_a, label=label_a)
    metrics_b = measure_clip(cache, cache_id_b, label=label_b)
    _, pcm_a = cache.load_audio(cache_id_a)
    _, pcm_b = cache.load_audio(cache_id_b)
    comparison = compare_metrics(metrics_a, metrics_b, pcm_a=pcm_a, pcm_b=pcm_b)
    verdict, verdict_summary = synthesize_verdict(comparison)
    difference_bullets = collect_difference_bullets(comparison)
    facts = build_signal_facts(
        metrics_a,
        metrics_b,
        comparison,
        difference_bullets=difference_bullets,
        verdict=verdict,
        verdict_summary=verdict_summary,
    )
    narrative = format_compare_answer(
        question=question,
        label_a=label_a,
        label_b=label_b,
        model_name=model_name,
        facts=facts,
        verdict_summary=verdict_summary,
        differences=difference_bullets,
    )
    return {
        "mode": "signal",
        "verdict": verdict,
        "verdict_summary": verdict_summary,
        "difference_count": len(difference_bullets),
        "differences": difference_bullets,
        "narrative": narrative,
        "facts": facts,
        "clip_a": metrics_a.to_dict(),
        "clip_b": metrics_b.to_dict(),
        "comparison": comparison,
    }
