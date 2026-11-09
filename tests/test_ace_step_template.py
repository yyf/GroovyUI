"""ACE-Step 1.5 hero template + GenerateAudio wiring."""

from __future__ import annotations

import json
from pathlib import Path

from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.node import NODE_REGISTRY
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow
from groovy.schema.validate import validate_workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[1]
from template_fixtures import require_template


def test_generate_audio_lists_ace_step_model() -> None:
    assert "ace-step-1.5" in NODE_REGISTRY["GenerateAudio"].COMPATIBLE_MODELS
    assert "ace-step-1.5-sft" in NODE_REGISTRY["GenerateAudio"].COMPATIBLE_MODELS
    assert "ace-step-1.5-2b-turbo" in NODE_REGISTRY["GenerateAudio"].COMPATIBLE_MODELS


def test_ace_step_2b_turbo_in_seed_catalog() -> None:
    from groovy.registry.catalog import ModelCatalog

    manifest = ModelCatalog().get("ace-step-1.5-2b-turbo")
    assert manifest is not None
    assert manifest.install.dev_stub is False
    assert manifest.download_size_mb_estimate is not None
    assert manifest.download_size_mb_estimate < 8000
    assert "GenerateAudio" in manifest.compatible_nodes


def test_ace_step_sft_in_seed_catalog() -> None:
    from groovy.registry.catalog import ModelCatalog

    manifest = ModelCatalog().get("ace-step-1.5-sft")
    assert manifest is not None
    assert manifest.install.dev_stub is False
    assert "GenerateAudio" in manifest.compatible_nodes
    steps = next(p for p in manifest.inference_params if p.name == "num_inference_steps")
    guidance = next(p for p in manifest.inference_params if p.name == "guidance_scale")
    assert steps.default == 50
    assert guidance.default == 7.0


def test_ace_step_cny_lora_in_seed_catalog() -> None:
    from groovy.registry.catalog import ModelCatalog

    manifest = ModelCatalog().get("ace-step-cny-lora")
    assert manifest is not None
    assert manifest.install.dev_stub is False
    assert manifest.license.commercial_ok is False
    assert "GenerateAudio" in manifest.compatible_nodes
    assert "ace-step-1.5-2b-turbo" in manifest.adapter_for
    assert manifest.hf_repo == "ACE-Step/ACE-Step-v1.5-chinese-new-year-LoRA"
    assert any(p.name == "lora_scale" for p in manifest.inference_params)


def test_ace_step_ambient_lora_in_seed_catalog() -> None:
    from groovy.registry.catalog import ModelCatalog

    manifest = ModelCatalog().get("ace-step-ambient-lora")
    assert manifest is not None
    assert manifest.install.dev_stub is False
    assert manifest.license.commercial_ok is False
    assert "GenerateAudio" in manifest.compatible_nodes
    assert "ace-step-1.5-2b-turbo" in manifest.adapter_for
    assert manifest.hf_repo == "DisturbingTheField/ACE-Step-v1.5-ambient_dream1-LoRA"


def test_generate_audio_exposes_lora_widgets() -> None:
    optional_keys = set(NODE_REGISTRY["GenerateAudio"].INPUT_TYPES()["optional"])
    assert "lora" in optional_keys
    assert "lora_scale" in optional_keys


def test_ace_step_lora_demo_template_schema_and_stub_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("ace-step-lora-demo")
    data = json.loads(path.read_text())
    assert path.as_posix().endswith("/templates/ace-step-lora-demo.groovy.json")
    assert "featured" in data["metadata"]["tags"]
    assert "lora" in data["metadata"]["tags"]
    gens = {n["id"]: n for n in data["nodes"] if n["type"] == "GenerateAudio"}
    assert gens["n1"]["widgets"]["model"] == "ace-step-1.5-2b-turbo"
    assert gens["n1"]["widgets"]["lora"] == ""
    assert gens["n2"]["widgets"]["model"] == "ace-step-1.5-2b-turbo"
    assert gens["n2"]["widgets"]["lora"] == "ace-step-cny-lora"
    assert gens["n2"]["widgets"]["lora_scale"] == 1.0
    assert gens["n1"]["widgets"]["seed"] == gens["n2"]["widgets"]["seed"]
    assert gens["n1"]["widgets"]["seconds_total"] == gens["n2"]["widgets"]["seconds_total"] == 20.0
    assert any(link["from"] == ["n0", 0] and link["to"] == ["n1", 0] for link in data["links"])
    assert any(link["from"] == ["n0", 0] and link["to"] == ["n2", 0] for link in data["links"])

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    registry = ModelRegistry(tmp_path)
    registry.installer.install("ace-step-1.5-2b-turbo")
    registry.installer.install("ace-step-cny-lora")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n5", "n6"])
    assert out.status == "completed", out.error
    assert out.outputs["n5"]["type"] == "AUDIO"
    assert out.outputs["n6"]["type"] == "AUDIO"


def test_ace_step_dual_lora_ab_template_schema_and_stub_render(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("ace-step-dual-lora-ab")
    data = json.loads(path.read_text())
    assert path.as_posix().endswith("/templates/ace-step-dual-lora-ab.groovy.json")
    assert "starter" in data["metadata"]["tags"]
    assert "experimental" in data["metadata"]["tags"]
    assert "featured" in data["metadata"]["tags"]
    assert "lora" in data["metadata"]["tags"]
    note = next(n for n in data["nodes"] if n["type"] == "Note")
    assert "Experimental" in note["widgets"]["text"]
    gens = {n["id"]: n for n in data["nodes"] if n["type"] == "GenerateAudio"}
    assert gens["n1"]["widgets"]["model"] == "ace-step-1.5-2b-turbo"
    assert gens["n2"]["widgets"]["model"] == "ace-step-1.5-2b-turbo"
    assert gens["n1"]["widgets"]["lora"] == "ace-step-cny-lora"
    assert gens["n2"]["widgets"]["lora"] == "ace-step-ambient-lora"
    assert gens["n1"]["widgets"]["lora_scale"] == 1.0
    assert gens["n2"]["widgets"]["lora_scale"] == 1.0
    assert gens["n1"]["widgets"]["seed"] == gens["n2"]["widgets"]["seed"]
    assert gens["n1"]["widgets"]["prompt"] == gens["n2"]["widgets"]["prompt"]
    assert gens["n1"]["widgets"]["seconds_total"] == gens["n2"]["widgets"]["seconds_total"] == 20.0
    assert gens["n1"]["widgets"]["num_inference_steps"] == gens["n2"]["widgets"]["num_inference_steps"] == 12
    assert "ambient_dream1" in gens["n1"]["widgets"]["prompt"]
    assert any(link["from"] == ["n0", 0] and link["to"] == ["n1", 0] for link in data["links"])
    assert any(link["from"] == ["n0", 0] and link["to"] == ["n2", 0] for link in data["links"])

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    registry = ModelRegistry(tmp_path)
    registry.installer.install("ace-step-1.5-2b-turbo")
    registry.installer.install("ace-step-cny-lora")
    registry.installer.install("ace-step-ambient-lora")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n5", "n6"])
    assert out.status == "completed", out.error
    assert out.outputs["n5"]["type"] == "AUDIO"
    assert out.outputs["n6"]["type"] == "AUDIO"


def test_ace_step_template_schema_and_stub_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("ace-step-1.5")
    data = json.loads(path.read_text())
    assert "featured" in data["metadata"]["tags"]
    gen = next(node for node in data["nodes"] if node["type"] == "GenerateAudio")
    prompt = next(node for node in data["nodes"] if node["type"] == "Prompt")
    assert gen["widgets"]["model"] == "ace-step-1.5"
    assert prompt["widgets"]["text"]
    assert any(
        link["from"] == ["n0", 0] and link["to"] == ["n1", 0] and link["type"] == "TEXT"
        for link in data["links"]
    )

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    registry = ModelRegistry(tmp_path)
    registry.installer.install("ace-step-1.5")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n3", "n4"])
    assert out.status == "completed", out.error
    assert out.outputs["n3"]["type"] == "AUDIO"


def test_ace_step_sft_template_schema_and_stub_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("ace-step-1.5-sft")
    data = json.loads(path.read_text())
    assert "starter" in data["metadata"]["tags"]
    assert "featured" in data["metadata"]["tags"]
    assert "sft" in data["metadata"]["tags"]
    assert path.as_posix().endswith("/templates/ace-step-1.5-sft.groovy.json")
    gen = next(node for node in data["nodes"] if node["type"] == "GenerateAudio")
    prompts = [node for node in data["nodes"] if node["type"] == "Prompt"]
    assert len(prompts) == 2
    style = next(node for node in prompts if node["id"] == "n0")
    lyrics = next(node for node in prompts if node["id"] == "n0b")
    assert gen["widgets"]["model"] == "ace-step-1.5-sft"
    assert gen["widgets"]["num_inference_steps"] == 50
    assert gen["widgets"]["guidance_scale"] == 7.0
    assert style["widgets"]["text"] == "dark IDM with experimental granular texture"
    assert lyrics["widgets"]["text"] == ""
    assert any(
        link["from"] == ["n0", 0] and link["to"] == ["n1", 0] and link["type"] == "TEXT"
        for link in data["links"]
    )
    assert any(
        link["from"] == ["n0b", 0] and link["to"] == ["n1", 3] and link["type"] == "TEXT"
        for link in data["links"]
    )
    schema_inputs = [s["name"] for s in NODE_REGISTRY["GenerateAudio"].describe()["inputs"]]
    assert schema_inputs == ["text", "midi", "reference_audio", "lyrics"]

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    registry = ModelRegistry(tmp_path)
    registry.installer.install("ace-step-1.5-sft")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n3", "n4"])
    assert out.status == "completed", out.error
    assert out.outputs["n3"]["type"] == "AUDIO"


def test_layered_music_sfx_template_parallel_and_series(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("layered-music-sfx")
    data = json.loads(path.read_text())
    assert "starter" in data["metadata"]["tags"]
    assert "parallel" in data["metadata"]["tags"]
    assert path.as_posix().endswith("/templates/layered-music-sfx.groovy.json")
    gens = {n["id"]: n for n in data["nodes"] if n["type"] == "GenerateAudio"}
    assert gens["n2"]["widgets"]["model"] == "stable-audio-open-small"
    assert gens["n3"]["widgets"]["model"] == "stable-audio-open-small"
    assert gens["n2"]["widgets"]["seconds_total"] == 8.0
    assert gens["n3"]["widgets"]["seconds_total"] == 8.0
    mix = next(n for n in data["nodes"] if n["type"] == "Mix")
    assert mix["widgets"]["gain_a"] == 1.0
    assert mix["widgets"]["gain_b"] == 0.7
    assert any(link["from"] == ["n0", 0] and link["to"] == ["n2", 0] for link in data["links"])
    assert any(link["from"] == ["n1", 0] and link["to"] == ["n3", 0] for link in data["links"])
    assert any(link["from"] == ["n2", 0] and link["to"] == ["n4", 0] for link in data["links"])
    assert any(link["from"] == ["n3", 0] and link["to"] == ["n4", 1] for link in data["links"])
    assert any(link["from"] == ["n4", 0] and link["to"] == ["n5", 0] for link in data["links"])

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    registry = ModelRegistry(tmp_path)
    registry.installer.install("stable-audio-open-small")
    out = Executor(tmp_path).execute(workflow, target_nodes=["n6", "n7"])
    assert out.status == "completed", out.error
    assert out.outputs["n6"]["type"] == "AUDIO"
