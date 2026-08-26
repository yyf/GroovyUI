from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from groovy.executor import Executor
from groovy.node import NODE_REGISTRY
from groovy.nodes.core import register_all as register_core
from groovy.nodes.core.beat_track import track_beats_from_mono
from groovy.schema.models import Workflow

register_core()


def _click_track(sr: int, bpm: float, duration_sec: float) -> np.ndarray:
    n = int(sr * duration_sec)
    period = int(round(sr * 60.0 / bpm))
    audio = np.zeros(n, dtype=np.float64)
    click_n = 256
    click = np.sin(2.0 * np.pi * np.arange(click_n) * 1000.0 / sr) * np.hanning(click_n)
    for start in range(0, n, period):
        end = min(n, start + click_n)
        audio[start:end] += click[: end - start]
    return audio.astype(np.float32)


def test_beat_track_registered() -> None:
    assert "BeatTrack" in NODE_REGISTRY
    schema = NODE_REGISTRY["BeatTrack"].describe()
    assert [item["name"] for item in schema["inputs"]] == ["audio", "fallback_clock"]
    assert [item["name"] for item in schema["outputs"]] == ["beats", "half"]


def test_track_beats_recovers_click_tempo() -> None:
    sr = 48000
    bpm = 120.0
    audio = _click_track(sr, bpm, 4.0)
    result = track_beats_from_mono(audio, sr, min_bpm=80.0, max_bpm=160.0, tightness=0.4)
    assert result.used_fallback is False
    assert abs(result.bpm - bpm) < 4.0
    period = sr * 60.0 / bpm
    spacings = np.diff(result.beat_samples)
    assert spacings.size >= 4
    assert abs(float(np.median(spacings)) - period) < period * 0.08


def test_track_beats_falls_back_on_silence() -> None:
    sr = 48000
    n = sr * 2
    fallback = np.arange(0, n, sr // 2, dtype=int)
    result = track_beats_from_mono(
        np.zeros(n, dtype=np.float64),
        sr,
        fallback_starts=fallback,
        fallback_bpm=90.0,
    )
    assert result.used_fallback is True
    assert np.array_equal(result.beat_samples, fallback)


def test_beat_track_node_click_and_fallback(tmp_path: Path) -> None:
    sr = 48000
    rel = "assets/samples/beat-clicks.wav"
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, _click_track(sr, 100.0, 3.0), sr)

    workflow = Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": "test-beat-track",
            "metadata": {"title": "beat-track", "description": ""},
            "nodes": [
                {"id": "load", "type": "LoadAudio", "widgets": {"path": rel}},
                {
                    "id": "clk",
                    "type": "Clock",
                    "widgets": {"bpm": 80.0, "pulse_ms": 20.0, "duration_sec": 3.0, "sample_rate": sr},
                },
                {
                    "id": "bt",
                    "type": "BeatTrack",
                    "widgets": {
                        "fallback_bpm": 80.0,
                        "pulse_ms": 20.0,
                        "min_bpm": 80.0,
                        "max_bpm": 130.0,
                        "tightness": 0.35,
                    },
                },
            ],
            "links": [
                {"id": "l1", "from": ["load", 0], "to": ["bt", 0], "type": "AUDIO"},
                {"id": "l2", "from": ["clk", 0], "to": ["bt", 1], "type": "AUTOMATION"},
            ],
            "groups": [],
        }
    )
    result = Executor(tmp_path).execute(workflow, target_nodes=["bt"])
    assert result.status == "completed", result.error
    assert result.outputs["bt"]["type"] == "MULTI"
    assert [slot["type"] for slot in result.outputs["bt"]["outputs"]] == ["AUTOMATION", "AUTOMATION"]

    silent = tmp_path / "assets/samples/beat-silent.wav"
    sf.write(silent, np.zeros(sr, dtype=np.float32), sr)
    quiet = Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": "test-beat-track-fallback",
            "metadata": {"title": "beat-track-fallback", "description": ""},
            "nodes": [
                {"id": "load", "type": "LoadAudio", "widgets": {"path": "assets/samples/beat-silent.wav"}},
                {
                    "id": "clk",
                    "type": "Clock",
                    "widgets": {"bpm": 90.0, "pulse_ms": 15.0, "duration_sec": 1.0, "sample_rate": sr},
                },
                {
                    "id": "bt",
                    "type": "BeatTrack",
                    "widgets": {"fallback_bpm": 90.0, "pulse_ms": 15.0},
                },
            ],
            "links": [
                {"id": "l1", "from": ["load", 0], "to": ["bt", 0], "type": "AUDIO"},
                {"id": "l2", "from": ["clk", 0], "to": ["bt", 1], "type": "AUTOMATION"},
            ],
            "groups": [],
        }
    )
    out = Executor(tmp_path).execute(quiet, target_nodes=["bt"])
    assert out.status == "completed", out.error
