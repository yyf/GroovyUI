"""Featured ship-gate templates with real inference (portfolio order).

    GROOVY_INFERENCE_STUB=0 uv run pytest tests/test_featured_real_inference.py -q -m integration
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.ai.inference_env import (
    basic_pitch_available,
    deepfilternet_available,
    demucs_available,
    kokoro_available,
    musicgen_melody_available,
    musicgen_small_available,
    whisper_available,
)
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
DIALOGUE_FIXTURE = ROOT / "assets" / "samples" / "dialogue_48k.wav"

FEATURED = [
    "podcast-denoise",
    "stem-separation",
    "transcribe-dialogue",
    "transcribe-and-diarize",
    "text-to-music",
    "transcribe-and-regenerate",
    "hello-groovy",
]

MODELS_BY_TEMPLATE: dict[str, tuple[str, ...]] = {
    "podcast-denoise": ("deepfilternet-v3",),
    "stem-separation": ("demucs-v4",),
    "transcribe-dialogue": ("whisper-large-v3-turbo",),
    "transcribe-and-diarize": ("whisper-large-v3-turbo",),
    "text-to-music": ("musicgen-small",),
    "transcribe-and-regenerate": ("basic-pitch", "musicgen-melody-small"),
    "hello-groovy": ("kokoro-82m",),
}

RUNTIME_READY = {
    "deepfilternet-v3": deepfilternet_available,
    "demucs-v4": demucs_available,
    "whisper-large-v3-turbo": whisper_available,
    "kokoro-82m": kokoro_available,
    "musicgen-small": musicgen_small_available,
    "basic-pitch": basic_pitch_available,
    "musicgen-melody-small": musicgen_melody_available,
}

pytestmark = pytest.mark.integration


def _stub_forced() -> bool:
    return os.environ.get("GROOVY_INFERENCE_STUB", "").lower() in ("1", "true", "yes")


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    if _stub_forced():
        pytest.skip("Set GROOVY_INFERENCE_STUB=0 to run featured real-inference ship gate")
    if not shutil.which("uv"):
        pytest.skip("uv is required for Model Browser python_deps install")

    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48_000
    t = np.linspace(0, 1.0, int(sr), endpoint=False)
    tone = 0.22 * np.sin(2 * np.pi * 440 * t)
    noise = 0.02 * np.random.default_rng(0).standard_normal(t.size)
    sf.write(assets / "podcast_denoise_demo.wav", tone + noise, sr)
    sf.write(assets / "Knockout_41k_mono.wav", tone + noise, sr)
    if DIALOGUE_FIXTURE.is_file():
        shutil.copy(DIALOGUE_FIXTURE, assets / "dialogue_48k.wav")
    return tmp_path


def _load(template_id: str, *, sample: str | None = None) -> Workflow:
    path = TEMPLATES / f"{template_id}.groovy.json"
    workflow = Workflow.model_validate(json.loads(path.read_text()))
    if sample is not None:
        for node in workflow.nodes:
            if node.type == "LoadAudio":
                node.widgets["path"] = sample
    return workflow


def _ensure_models(project_dir: Path, model_ids: tuple[str, ...]) -> None:
    registry = ModelRegistry(project_dir)
    for model_id in model_ids:
        state = registry.installer.install(model_id)
        assert state.status == "ready", f"{model_id} install failed: {state.error}"
        checker = RUNTIME_READY.get(model_id)
        if checker is not None and not checker():
            pytest.skip(f"{model_id} imports unavailable after install")


@pytest.mark.parametrize("template_id", FEATURED, ids=FEATURED)
def test_featured_template_real_inference(project_dir: Path, template_id: str) -> None:
    models = MODELS_BY_TEMPLATE[template_id]
    _ensure_models(project_dir, models)

    sample = "assets/samples/podcast_denoise_demo.wav"
    if template_id == "stem-separation":
        sample = "assets/samples/Knockout_41k_mono.wav"
    if template_id in {"transcribe-dialogue", "transcribe-and-diarize"} and (
        project_dir / "assets" / "samples" / "dialogue_48k.wav"
    ).is_file():
        sample = "assets/samples/dialogue_48k.wav"
    if template_id in {"text-to-music", "hello-groovy"}:
        sample = None

    workflow = _load(template_id, sample=sample)
    executor = Executor(project_dir)
    result = executor.execute(workflow, force_rebuild=True)
    assert result.status == "completed", f"{template_id}: {result.error}"

    audio_outs = [
        out for out in result.outputs.values() if out.get("type") == "AUDIO" and out.get("cache_id")
    ]
    text_outs = [out for out in result.outputs.values() if out.get("type") == "TEXT"]

    if template_id == "hello-groovy":
        assert audio_outs, "hello-groovy should produce AUDIO"
        _, pcm = executor.cache.load_audio(audio_outs[0]["cache_id"])
        duration = pcm.shape[-1] / 48_000
        assert duration >= 0.4
        assert float(np.max(np.abs(pcm))) > 0.05
        return

    if template_id in {"transcribe-dialogue", "transcribe-and-diarize"}:
        assert text_outs, f"{template_id}: expected TEXT"
        text = (text_outs[0].get("text") or "").strip()
        assert text and "[dev transcript" not in text.lower()
        if template_id == "transcribe-and-diarize":
            assert "SPEAKER_" in text or "speaker" in text.lower() or "[" in text

    if template_id == "text-to-music":
        assert audio_outs
        _, pcm = executor.cache.load_audio(audio_outs[0]["cache_id"])
        duration = pcm.shape[-1] / 48_000
        # Real MusicGen small with 512 tokens is typically several seconds, not the 2s stub.
        assert duration >= 2.5, f"text-to-music duration {duration:.2f}s looks like stub"
        assert float(np.max(np.abs(pcm))) > 0.01

    if template_id in {"podcast-denoise", "stem-separation", "transcribe-and-regenerate"}:
        assert audio_outs or any(o.get("type") == "MULTI" for o in result.outputs.values())
