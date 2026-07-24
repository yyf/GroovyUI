from __future__ import annotations

import json
from pathlib import Path

import pytest
from groovy.executor import (
    ALL_TEMPLATE_INTEGRITY_SPECS,
    Executor,
    SIGNAL_INTEGRITY_V1_TEMPLATES,
    TemplateIntegritySpec,
    audit_manifest,
    audit_output_contract,
    load_manifest,
    load_template_workflow,
    prepare_template_project,
)
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.node import NODE_REGISTRY
from groovy.registry import ModelRegistry
from groovy.schema.validate import validate_workflow
from groovy.server.compare import analyze_ab_pair

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[1]


def test_stem_split_template_defaults_are_ci_safe_wav() -> None:
    """v1 stem-split must not require ffmpeg (SaveAudio mp4) on CI runners."""
    data = json.loads((ROOT / "templates" / "stem-split-vocals.groovy.json").read_text())
    load = next(node for node in data["nodes"] if node["type"] == "LoadAudio")
    save = next(node for node in data["nodes"] if node["type"] == "SaveAudio")
    assert str(load["widgets"]["path"]).endswith(".wav")
    assert save["widgets"]["format"] == "wav"
    assert str(save["widgets"]["filename"]).endswith(".wav")


@pytest.fixture(params=ALL_TEMPLATE_INTEGRITY_SPECS, ids=lambda s: s.template_id)
def integrity_spec(request: pytest.FixtureRequest) -> TemplateIntegritySpec:
    return request.param


@pytest.fixture
def prepared_project(integrity_spec: TemplateIntegritySpec, tmp_path: Path) -> tuple[Path, TemplateIntegritySpec]:
    return prepare_template_project(tmp_path, integrity_spec), integrity_spec


def test_l0_schema_valid(integrity_spec: TemplateIntegritySpec) -> None:
    workflow = load_template_workflow(integrity_spec)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [error.message for error in result.errors]


def test_l1_render_smoke(prepared_project: tuple[Path, TemplateIntegritySpec]) -> None:
    project_dir, spec = prepared_project
    workflow = load_template_workflow(spec)
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=list(spec.target_nodes))
    assert result.status == "completed", result.error
    for node_id, expected_type in spec.required_outputs:
        assert node_id in result.outputs, f"missing output for {node_id}"
        assert result.outputs[node_id]["type"] == expected_type
    for output in result.outputs.values():
        if output.get("type") == "AUDIO" and output.get("cache_id"):
            meta = executor.cache.read_meta(output["cache_id"])
            assert int(meta["frame_count"]) > 0


def test_l2_manifest_audit(prepared_project: tuple[Path, TemplateIntegritySpec]) -> None:
    project_dir, spec = prepared_project
    workflow = load_template_workflow(spec)
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=list(spec.target_nodes))
    assert result.status == "completed", result.error
    assert result.manifest_path
    manifest = load_manifest(result.manifest_path)
    errors = audit_manifest(manifest, workflow, executor.cache)
    assert not errors, errors


def test_l3_output_contract(prepared_project: tuple[Path, TemplateIntegritySpec]) -> None:
    project_dir, spec = prepared_project
    workflow = load_template_workflow(spec)
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=list(spec.target_nodes))
    assert result.status == "completed", result.error
    manifest = load_manifest(result.manifest_path)
    errors = audit_output_contract(spec, workflow, manifest, executor.cache)
    assert not errors, errors


def test_ab_compare_demo_spot_check(tmp_path: Path) -> None:
    spec = next(s for s in ALL_TEMPLATE_INTEGRITY_SPECS if s.template_id == "ab-compare-demo")
    project_dir = prepare_template_project(tmp_path, spec)
    workflow = load_template_workflow(spec)
    executor = Executor(project_dir)
    registry = ModelRegistry(project_dir)
    result = executor.execute(workflow, target_nodes=list(spec.target_nodes))
    assert result.status == "completed", result.error
    outputs = result.outputs
    assert outputs["n3"]["cache_id"] == outputs["n4"]["cache_id"]
    pairs = {
        ("n1", "n2"): "substantial",
        ("n2", "n3"): "substantial",
        ("n1", "n3"): "substantial",
        ("n3", "n4"): "no_difference",
    }
    for (left, right), expected_verdict in pairs.items():
        analysis = analyze_ab_pair(
            executor.cache,
            registry,
            cache_id_a=outputs[left]["cache_id"],
            cache_id_b=outputs[right]["cache_id"],
            label_a=left,
            label_b=right,
            model_id="groovy-signal-diff",
        )
        assert analysis["verdict"] == expected_verdict


def test_hello_groovy_manifest_cache_rerun_stable(tmp_path: Path) -> None:
    spec = next(s for s in SIGNAL_INTEGRITY_V1_TEMPLATES if s.template_id == "hello-groovy")
    project_dir = prepare_template_project(tmp_path, spec)
    workflow = load_template_workflow(spec)
    executor = Executor(project_dir)

    first = executor.execute(workflow, target_nodes=list(spec.target_nodes))
    assert first.status == "completed", first.error
    second = executor.execute(workflow, target_nodes=list(spec.target_nodes))
    assert second.status == "completed", second.error

    first_manifest = load_manifest(first.manifest_path)
    second_manifest = load_manifest(second.manifest_path)
    n3_first = next(n for n in first_manifest["nodes"] if n["node_id"] == "n3")
    n3_second = next(n for n in second_manifest["nodes"] if n["node_id"] == "n3")
    assert n3_second["cache_hit"] is True
    assert n3_first["output"].get("content_hash") == n3_second["output"].get("content_hash")
    assert n3_first["output"].get("content_hash")
