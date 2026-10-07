"""TranslateText node + isolate-vocals-to-transcribe-translate template."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
from groovy.executor import Executor
from groovy.node import NODE_REGISTRY
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow
from groovy.schema.validate import validate_workflow

register_core()
register_ai()

from template_fixtures import require_template


def test_translate_text_node_schema() -> None:
    spec = NODE_REGISTRY["TranslateText"].describe()
    assert any(s["name"] == "text" and s["type"] == "TEXT" for s in spec["inputs"])
    widgets = {w["name"]: w for w in spec.get("widgets", [])}
    assert widgets["model"]["type"] == "MODEL_REF"
    assert widgets["model"]["default"] == "m2m100-418m"
    assert "src_lang" in widgets and "tgt_lang" in widgets
    assert spec["outputs"][0]["type"] == "TEXT"


def test_text_mt_lang_normalize() -> None:
    from groovy.nodes.ai.backends.text_mt_runner import normalize_lang_iso2

    assert normalize_lang_iso2("en") == "en"
    assert normalize_lang_iso2("ENG") == "en"
    assert normalize_lang_iso2("spa") == "es"
    assert normalize_lang_iso2("fra") == "fr"


def test_kokoro_zh_voice_resolve() -> None:
    from groovy.nodes.ai.backends.kokoro_runner import resolve_kokoro_voice

    assert resolve_kokoro_voice("zh") == ("z", "zf_xiaobei")
    assert resolve_kokoro_voice("zh", "zm_yunxi") == ("z", "zm_yunxi")
    assert resolve_kokoro_voice("en") == ("a", "af_heart")


def test_translate_text_stub() -> None:
    from groovy.nodes.ai.inference import _translate_text_stub

    out = _translate_text_stub(
        "Hello world",
        model_id="m2m100-418m",
        src_lang="en",
        tgt_lang="zh",
    )
    assert out.startswith("[m2m100-418m|en->zh]")
    assert "Hello world" in out


def test_license_clear_text_mt_models_in_seed() -> None:
    from groovy.registry.catalog import ModelCatalog

    catalog = ModelCatalog()
    for model_id, spdx, commercial in (
        ("m2m100-418m", "MIT", True),
        ("madlad400-3b-mt", "Apache-2.0", True),
        ("opus-mt-en-es", "CC-BY-4.0", True),
        ("opus-mt-en-fr", "CC-BY-4.0", True),
    ):
        card = catalog.get(model_id)
        assert card is not None, model_id
        assert card.license.spdx == spdx, model_id
        assert card.license.commercial_ok is commercial, model_id
        assert "TranslateText" in card.compatible_nodes, model_id


def test_isolate_transcribe_translate_template_schema_and_stub_render(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("isolate-vocals-to-transcribe-translate")
    data = json.loads(path.read_text())
    mt = next(node for node in data["nodes"] if node["type"] == "TranslateText")
    assert mt["widgets"]["model"] == "m2m100-418m"
    assert mt["widgets"]["src_lang"] == "en"
    assert mt["widgets"]["tgt_lang"] == "zh"
    tts = next(node for node in data["nodes"] if node["type"] == "TTS")
    assert tts["widgets"]["model"] == "kokoro-82m"
    assert tts["widgets"]["language"] == "zh"
    assert tts["widgets"]["voice"] == "zf_xiaobei"

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    sample = tmp_path / "assets" / "samples" / "stem_separation_demo.wav"
    sample.parent.mkdir(parents=True)
    sr = 48000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    sf.write(sample, 0.2 * np.sin(2 * np.pi * 220 * t), sr)

    registry = ModelRegistry(tmp_path)
    registry.installer.install("demucs-v4")
    registry.installer.install("whisper-large-v3-turbo")
    registry.installer.install("m2m100-418m")
    registry.installer.install("kokoro-82m")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n5", "n7", "n9"])
    assert out.status == "completed", out.error
    assert out.outputs["n5"]["type"] == "TEXT"
    assert out.outputs["n7"]["type"] == "TEXT"
    assert out.outputs["n9"]["type"] == "AUDIO"
    translated = out.outputs["n7"]["text"]
    assert "m2m100-418m" in translated
    assert "en->zh" in translated
