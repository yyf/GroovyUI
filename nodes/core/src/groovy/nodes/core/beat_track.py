"""Offline beat tracker: AUDIO → pulse-train AUTOMATION (DSP analyzer, not a model)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal as scipy_signal

DEFAULT_HOP = 512
DEFAULT_N_FFT = 2048


@dataclass(frozen=True)
class BeatTrackResult:
    bpm: float
    beat_samples: np.ndarray
    used_fallback: bool


def onset_strength(
    mono: np.ndarray,
    sample_rate: int,
    hop: int = DEFAULT_HOP,
    n_fft: int = DEFAULT_N_FFT,
) -> np.ndarray:
    """Spectral-flux novelty curve, peak-normalized to 0–1."""
    samples = np.asarray(mono, dtype=np.float64).reshape(-1)
    if samples.size < n_fft:
        return np.zeros(1, dtype=np.float64)
    _, _, spec = scipy_signal.stft(
        samples,
        fs=int(sample_rate),
        nperseg=n_fft,
        noverlap=n_fft - hop,
        boundary=None,
        padded=False,
    )
    mag = np.abs(spec)
    flux = np.mean(np.maximum(np.diff(mag, axis=1, prepend=mag[:, :1]), 0.0), axis=0)
    flux = np.maximum(flux - float(np.median(flux)), 0.0)
    peak = float(np.max(flux))
    if peak > 0:
        flux = flux / peak
    return flux.astype(np.float64)


def estimate_bpm(
    onset: np.ndarray,
    sample_rate: int,
    hop: int,
    min_bpm: float,
    max_bpm: float,
) -> float | None:
    if onset.size < 8:
        return None
    centered = onset - float(np.mean(onset))
    if float(np.max(np.abs(centered))) < 1e-9:
        return None
    corr = np.correlate(centered, centered, mode="full")
    corr = corr[corr.size // 2 :]
    min_lag = max(1, int(np.floor(sample_rate * 60.0 / max_bpm / hop)))
    max_lag = min(corr.size - 1, int(np.ceil(sample_rate * 60.0 / min_bpm / hop)))
    if max_lag <= min_lag:
        return None
    lag = min_lag + int(np.argmax(corr[min_lag : max_lag + 1]))
    if corr[lag] <= 0:
        return None
    bpm = 60.0 * sample_rate / (lag * hop)
    return float(np.clip(bpm, min_bpm, max_bpm))


def beat_frames(
    onset: np.ndarray,
    bpm: float,
    sample_rate: int,
    hop: int,
    tightness: float,
) -> np.ndarray:
    period = sample_rate * 60.0 / max(bpm, 1e-6) / hop
    n = onset.size
    n_phase = max(1, int(round(period)))
    best_phase = 0
    best_score = -1.0
    for phase in range(n_phase):
        idx = np.round(np.arange(phase, n, period)).astype(int)
        idx = idx[(idx >= 0) & (idx < n)]
        if idx.size == 0:
            continue
        score = float(onset[idx].sum())
        if score > best_score:
            best_score = score
            best_phase = phase
    raw = np.round(np.arange(best_phase, n, period)).astype(int)
    raw = raw[(raw >= 0) & (raw < n)]
    tightness = float(np.clip(tightness, 0.0, 1.0))
    if tightness <= 0.01 or raw.size == 0:
        return raw.astype(int)
    window = max(1, int(round(period * 0.4 * tightness)))
    snapped = np.empty(raw.size, dtype=int)
    for i, frame in enumerate(raw):
        lo = max(0, int(frame) - window)
        hi = min(n, int(frame) + window + 1)
        snapped[i] = lo + int(np.argmax(onset[lo:hi]))
    return snapped


def frames_to_samples(frames: np.ndarray, hop: int, frame_count: int) -> np.ndarray:
    samples = np.round(np.asarray(frames, dtype=np.float64) * hop).astype(int)
    return samples[(samples >= 0) & (samples < frame_count)]


def rising_edge_samples(gate: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    values = np.asarray(gate, dtype=np.float64).reshape(-1)
    high = values >= threshold
    edges = np.zeros(high.size, dtype=bool)
    if high.size == 0:
        return np.zeros(0, dtype=int)
    edges[0] = bool(high[0])
    edges[1:] = high[1:] & ~high[:-1]
    return np.flatnonzero(edges).astype(int)


def render_pulse_train(frame_count: int, starts: np.ndarray, pulse_samples: int) -> np.ndarray:
    values = np.zeros(max(1, int(frame_count)), dtype=np.float64)
    width = max(1, int(pulse_samples))
    for start in np.asarray(starts, dtype=int).reshape(-1):
        if start < 0 or start >= values.size:
            continue
        values[start : min(values.size, start + width)] = 1.0
    return values


def metronome_starts(frame_count: int, sample_rate: int, bpm: float) -> np.ndarray:
    period = max(1, int(round(sample_rate * 60.0 / max(bpm, 1e-6))))
    return np.arange(0, max(1, int(frame_count)), period, dtype=int)


def detection_confident(
    onset: np.ndarray,
    beat_fr: np.ndarray,
    bpm: float,
    duration_sec: float,
) -> bool:
    if onset.size < 8 or beat_fr.size < 2:
        return False
    peakiness = float(np.max(onset)) / (float(np.mean(onset)) + 1e-9)
    expected = duration_sec * bpm / 60.0
    if expected >= 2 and beat_fr.size < max(3, expected * 0.45):
        return False
    return peakiness >= 2.5


def track_beats_from_mono(
    mono: np.ndarray,
    sample_rate: int,
    *,
    min_bpm: float = 70.0,
    max_bpm: float = 140.0,
    tightness: float = 0.55,
    fallback_starts: np.ndarray | None = None,
    fallback_bpm: float = 120.0,
    hop: int = DEFAULT_HOP,
) -> BeatTrackResult:
    samples = np.asarray(mono, dtype=np.float64).reshape(-1)
    n = max(1, samples.size)
    duration_sec = n / max(int(sample_rate), 1)
    onset = onset_strength(samples, sample_rate, hop=hop)
    bpm = estimate_bpm(onset, sample_rate, hop, min_bpm, max_bpm)
    fallback = (
        np.asarray(fallback_starts, dtype=int).reshape(-1)
        if fallback_starts is not None and np.asarray(fallback_starts).size
        else metronome_starts(n, sample_rate, fallback_bpm)
    )
    if bpm is None:
        return BeatTrackResult(bpm=float(fallback_bpm), beat_samples=fallback, used_fallback=True)
    frames = beat_frames(onset, bpm, sample_rate, hop, tightness)
    if not detection_confident(onset, frames, bpm, duration_sec):
        return BeatTrackResult(bpm=float(fallback_bpm), beat_samples=fallback, used_fallback=True)
    starts = frames_to_samples(frames, hop, n)
    if starts.size < 2:
        return BeatTrackResult(bpm=float(fallback_bpm), beat_samples=fallback, used_fallback=True)
    return BeatTrackResult(bpm=float(bpm), beat_samples=starts, used_fallback=False)
