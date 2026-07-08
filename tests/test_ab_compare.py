from __future__ import annotations

from pathlib import Path

import numpy as np
from groovy.executor.ab_compare import (
    analyze_signal_pair,
    compare_metrics,
    compare_pcm,
    compare_waveform_peaks,
    measure_clip,
    synthesize_verdict,
)
from groovy.executor.cache import CacheStore
from groovy.executor.audio import AudioBuffer


def _write_clip(cache: CacheStore, pcm: np.ndarray, sample_rate: int = 48000) -> str:
    buffer = AudioBuffer.from_planar(pcm, sample_rate, source_node_type="Test")
    cache.write_audio(buffer, pcm)
    return buffer.id


def test_compare_waveform_peaks_identical() -> None:
    peaks = [0.1, 0.5, 0.2, 0.8]
    stats = compare_waveform_peaks(peaks, peaks)
    assert stats["mean_abs_diff"] == 0.0
    assert stats["correlation"] == 1.0


def test_compare_pcm_detects_processing(tmp_path: Path) -> None:
    cache = CacheStore(tmp_path)
    sr = 48000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    clean = 0.2 * np.sin(2 * np.pi * 440 * t)
    noisy = clean + 0.05 * np.random.default_rng(0).standard_normal(sr)
    stats = compare_pcm(clean.reshape(1, -1), noisy.reshape(1, -1))
    assert stats["identical"] is False
    assert stats["max_sample_diff"] > 0.01


def test_analyze_signal_pair_detects_level_change(tmp_path: Path) -> None:
    cache = CacheStore(tmp_path)
    sr = 48000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    quiet = 0.1 * np.sin(2 * np.pi * 440 * t)
    loud = 0.4 * np.sin(2 * np.pi * 440 * t)
    id_a = _write_clip(cache, quiet.reshape(1, -1), sr)
    id_b = _write_clip(cache, loud.reshape(1, -1), sr)

    result = analyze_signal_pair(
        cache,
        cache_id_a=id_a,
        cache_id_b=id_b,
        label_a="Quiet",
        label_b="Loud",
        question="How loud is B compared to A?",
    )

    assert result["mode"] == "signal"
    assert result["verdict"] in {"moderate", "substantial"}
    assert result["difference_count"] >= 1
    assert result["comparison"]["peak_delta_db"] > 6.0
    assert any("Peak level differs" in item for item in result["differences"])


def test_same_cache_reports_no_difference(tmp_path: Path) -> None:
    cache = CacheStore(tmp_path)
    sr = 48000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    tone = 0.2 * np.sin(2 * np.pi * 440 * t)
    clip_id = _write_clip(cache, tone.reshape(1, -1), sr)
    metrics = measure_clip(cache, clip_id, label="A")
    _, pcm = cache.load_audio(clip_id)
    comparison = compare_metrics(metrics, metrics, pcm_a=pcm, pcm_b=pcm)
    verdict, summary = synthesize_verdict(comparison)
    assert verdict == "no_difference"
    assert "same cached audio" in summary
