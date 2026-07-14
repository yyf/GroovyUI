"""Hero templates with real inference — tolerance-based signal contracts (not stubs).

Run locally (CI keeps ``GROOVY_INFERENCE_STUB=1`` and skips these):

    GROOVY_INFERENCE_STUB=0 uv run pytest tests/test_hero_real_inference.py -q -m integration
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from audio_tolerance import assert_peak_sane, duration_delta_sec, mono, snr_db
from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.ai.inference_env import (
    deepfilternet_available,
    demucs_available,
    whisper_available,
)
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[1]
PODCAST = ROOT / "templates" / "podcast-denoise.groovy.json"
STEMS = ROOT / "templates" / "stem-split-vocals.groovy.json"
DIALOGUE = ROOT / "templates" / "transcribe-dialogue.groovy.json"
DIALOGUE_FIXTURE = ROOT / "assets" / "samples" / "dialogue_48k.wav"

# EXECUTOR_SPEC: Demucs verify SNR ≥ 40 dB. Short synthetic tones are looser.
DEMUCS_RECONSTRUCTION_SNR_DB = 20.0
# LUFS Normalize target in the podcast-denoise template.
NORMALIZE_TARGET_LUFS = -16.0
NORMALIZE_LUFS_TOLERANCE_DB = 1.5
# Sample-accurate hop: DeepFilter pads/trims to input length; Demucs may drift slightly.
MAX_DURATION_DELTA_SEC = 0.05
# Denoise must actually change noisy input (not stub passthrough).
DENOISE_MIN_MEAN_ABS_DIFF = 1e-4
DENOISE_MAX_MEAN_ABS_DIFF = 0.5
DENOISE_RMS_RATIO_MIN = 0.05
DENOISE_RMS_RATIO_MAX = 4.0


pytestmark = pytest.mark.integration


def _stub_forced() -> bool:
    return os.environ.get("GROOVY_INFERENCE_STUB", "").lower() in ("1", "true", "yes")


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    if _stub_forced():
        pytest.skip("Set GROOVY_INFERENCE_STUB=0 to run hero real-inference tolerance tests")
    if not shutil.which("uv"):
        pytest.skip("uv is required for Model Browser python_deps install")

    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48_000
    # 1s tone + light noise — enough for demucs/DeepFilter without long GPU time.
    t = np.linspace(0, 1.0, int(sr), endpoint=False)
    tone = 0.22 * np.sin(2 * np.pi * 440 * t)
    noise = 0.02 * np.random.default_rng(0).standard_normal(t.size)
    sf.write(assets / "male-1.wav", tone + noise, sr)
    if DIALOGUE_FIXTURE.is_file():
        shutil.copy(DIALOGUE_FIXTURE, assets / "dialogue_48k.wav")
    return tmp_path


def _load_template(path: Path, *, sample: str = "assets/samples/male-1.wav") -> Workflow:
    workflow = Workflow.model_validate(json.loads(path.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = sample
    return workflow


def _ensure_model(project_dir: Path, model_id: str) -> None:
    registry = ModelRegistry(project_dir)
    state = registry.installer.install(model_id)
    assert state.status == "ready", f"{model_id} install failed: {state.error}"


def test_podcast_denoise_real_inference_tolerance(project_dir: Path) -> None:
    _ensure_model(project_dir, "deepfilternet-v3")
    if not deepfilternet_available():
        pytest.skip("deepfilternet imports unavailable after install")

    workflow = _load_template(PODCAST)
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n4", "n5"], force_rebuild=True)
    assert result.status == "completed", result.error

    load_meta = executor.cache.read_meta(result.outputs["n1"]["cache_id"])
    denoise_meta = executor.cache.read_meta(result.outputs["n2"]["cache_id"])
    norm_meta = executor.cache.read_meta(result.outputs["n4"]["cache_id"])

    assert load_meta["sample_rate"] == denoise_meta["sample_rate"] == 48_000
    assert duration_delta_sec(
        int(load_meta["frame_count"]),
        int(denoise_meta["frame_count"]),
        int(load_meta["sample_rate"]),
    ) <= MAX_DURATION_DELTA_SEC
    assert denoise_meta.get("content_hash")
    assert norm_meta.get("content_hash")

    _, load_pcm = executor.cache.load_audio(result.outputs["n1"]["cache_id"])
    _, denoise_pcm = executor.cache.load_audio(result.outputs["n2"]["cache_id"])
    assert_peak_sane(denoise_pcm, label="Denoise")

    load_m = mono(load_pcm)
    denoise_m = mono(denoise_pcm)
    n = min(load_m.size, denoise_m.size)
    mean_abs = float(np.mean(np.abs(denoise_m[:n] - load_m[:n])))
    assert DENOISE_MIN_MEAN_ABS_DIFF <= mean_abs <= DENOISE_MAX_MEAN_ABS_DIFF, (
        f"Denoise mean_abs_diff {mean_abs:.6f} outside "
        f"[{DENOISE_MIN_MEAN_ABS_DIFF}, {DENOISE_MAX_MEAN_ABS_DIFF}]"
    )
    load_rms = float(np.sqrt(np.mean(np.square(load_m[:n]))))
    denoise_rms = float(np.sqrt(np.mean(np.square(denoise_m[:n]))))
    ratio = denoise_rms / max(load_rms, 1e-12)
    assert DENOISE_RMS_RATIO_MIN <= ratio <= DENOISE_RMS_RATIO_MAX, (
        f"Denoise RMS ratio {ratio:.3f} outside [{DENOISE_RMS_RATIO_MIN}, {DENOISE_RMS_RATIO_MAX}]"
    )

    _, norm_pcm = executor.cache.load_audio(result.outputs["n4"]["cache_id"])
    try:
        import pyloudnorm as pyln

        meter = pyln.Meter(int(norm_meta["sample_rate"]))
        lufs = float(meter.integrated_loudness(mono(norm_pcm)))
        assert abs(lufs - NORMALIZE_TARGET_LUFS) <= NORMALIZE_LUFS_TOLERANCE_DB, (
            f"Normalize LUFS {lufs:.2f} not within {NORMALIZE_LUFS_TOLERANCE_DB} of {NORMALIZE_TARGET_LUFS}"
        )
    except ImportError:
        pass

    saved = project_dir / "exports" / "podcast-denoised.wav"
    assert saved.exists() and saved.stat().st_size > 1_000

    # Cache rerun must be stable (sample-accurate offline path).
    again = executor.execute(workflow, target_nodes=["n4", "n5"])
    assert again.status == "completed", again.error
    assert again.outputs["n2"]["cache_id"] == result.outputs["n2"]["cache_id"]


def test_stem_split_vocals_real_inference_tolerance(project_dir: Path) -> None:
    _ensure_model(project_dir, "demucs-v4")
    if not demucs_available():
        pytest.skip("demucs/torch imports unavailable after install")

    workflow = _load_template(STEMS)
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n3", "n4"], force_rebuild=True)
    assert result.status == "completed", result.error

    multi = result.outputs["n2"]
    assert multi["type"] == "MULTI"
    assert len(multi["outputs"]) == 4
    names = {slot.get("name") for slot in multi["outputs"]}
    assert names == {"vocals", "drums", "bass", "other"}

    load_id = result.outputs["n1"]["cache_id"]
    load_meta = executor.cache.read_meta(load_id)
    _, load_pcm = executor.cache.load_audio(load_id)
    sr = int(load_meta["sample_rate"])

    stem_sum: np.ndarray | None = None
    for slot in multi["outputs"]:
        cache_id = slot["cache_id"]
        meta = executor.cache.read_meta(cache_id)
        assert int(meta["sample_rate"]) == sr, f"{slot['name']}: sample rate drift"
        assert (
            duration_delta_sec(int(load_meta["frame_count"]), int(meta["frame_count"]), sr)
            <= MAX_DURATION_DELTA_SEC
        ), f"{slot['name']}: duration drifted vs load"
        assert meta.get("content_hash")
        _, stem_pcm = executor.cache.load_audio(cache_id)
        assert_peak_sane(stem_pcm, label=str(slot["name"]))
        mono_stem = stem_pcm.mean(axis=0) if stem_pcm.ndim > 1 else stem_pcm
        if stem_sum is None:
            stem_sum = mono_stem.astype(np.float64)
        else:
            n = min(stem_sum.size, mono_stem.size)
            stem_sum = stem_sum[:n] + mono_stem[:n]

    assert stem_sum is not None
    recon_snr = snr_db(load_pcm, stem_sum.reshape(1, -1))
    assert recon_snr >= DEMUCS_RECONSTRUCTION_SNR_DB, (
        f"stem reconstruction SNR {recon_snr:.2f} dB below {DEMUCS_RECONSTRUCTION_SNR_DB}"
    )

    vocals_id = next(slot["cache_id"] for slot in multi["outputs"] if slot.get("name") == "vocals")
    assert result.outputs["n3"]["cache_id"] == vocals_id

    saved = project_dir / "exports" / "vocals.wav"
    assert saved.exists() and saved.stat().st_size > 1_000

    again = executor.execute(workflow, target_nodes=["n3", "n4"])
    assert again.status == "completed", again.error
    assert again.outputs["n2"]["outputs"][0]["cache_id"] == multi["outputs"][0]["cache_id"]


def test_transcribe_dialogue_real_inference_tolerance(project_dir: Path) -> None:
    if not (project_dir / "assets" / "samples" / "dialogue_48k.wav").is_file():
        pytest.skip("dialogue_48k.wav fixture missing from assets/samples")

    _ensure_model(project_dir, "whisper-large-v3-turbo")
    if not whisper_available():
        pytest.skip("faster_whisper unavailable after install")

    workflow = _load_template(DIALOGUE, sample="assets/samples/dialogue_48k.wav")
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n2", "n3", "n4", "n5"], force_rebuild=True)
    assert result.status == "completed", result.error

    text_out = result.outputs["n2"]
    assert text_out["type"] == "TEXT"
    text = (text_out.get("text") or "").strip()
    assert text, "Whisper returned empty transcript on dialogue fixture"
    assert "[dev transcript" not in text.lower()

    text_preview = result.outputs["n3"]
    assert text_preview["type"] == "TEXT"
    assert (text_preview.get("text") or "").strip() == text

    audio_preview = result.outputs["n4"]
    assert audio_preview["type"] == "AUDIO"
    assert audio_preview["cache_id"] == result.outputs["n1"]["cache_id"]

    load_meta = executor.cache.read_meta(result.outputs["n1"]["cache_id"])
    assert int(load_meta["sample_rate"]) == 48_000
    assert int(load_meta["frame_count"]) > 0

    saved = project_dir / "exports" / "dialogue-source.wav"
    assert saved.exists() and saved.stat().st_size > 1_000

    again = executor.execute(workflow, target_nodes=["n2", "n3", "n4", "n5"])
    assert again.status == "completed", again.error
    assert again.outputs["n2"]["text"] == text_out["text"]
    assert again.outputs["n3"]["text"] == text_preview["text"]
    assert again.outputs["n4"]["cache_id"] == audio_preview["cache_id"]
