"""L4 — per-template end-to-end sample-accuracy verification (input, output, AI hops)."""

from __future__ import annotations

from pathlib import Path

import pytest
from groovy.executor import (
    ALL_TEMPLATE_INTEGRITY_SPECS,
    Executor,
    TemplateIntegritySpec,
    load_manifest,
    load_template_workflow,
    prepare_template_project,
)
from groovy.executor.template_sample_accuracy import _iter_audio_caches, audit_sample_accuracy
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.node import NODE_REGISTRY

register_core()
register_ai()


@pytest.fixture(params=ALL_TEMPLATE_INTEGRITY_SPECS, ids=lambda spec: spec.template_id)
def sample_accuracy_spec(request: pytest.FixtureRequest) -> TemplateIntegritySpec:
    return request.param


@pytest.fixture
def prepared_sample_accuracy_project(
    sample_accuracy_spec: TemplateIntegritySpec,
    tmp_path: Path,
) -> tuple[Path, TemplateIntegritySpec]:
    return prepare_template_project(tmp_path, sample_accuracy_spec), sample_accuracy_spec


def test_l4_template_sample_accuracy_e2e(
    prepared_sample_accuracy_project: tuple[Path, TemplateIntegritySpec],
) -> None:
    project_dir, spec = prepared_sample_accuracy_project
    workflow = load_template_workflow(spec)
    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=list(spec.target_nodes))
    assert result.status == "completed", result.error
    assert result.manifest_path

    manifest = load_manifest(result.manifest_path)
    errors, report = audit_sample_accuracy(
        spec,
        manifest,
        workflow,
        executor.cache,
        node_registry=NODE_REGISTRY,
    )
    assert not errors, errors

    load_nodes = [node for node in workflow.nodes if node.type == "LoadAudio"]
    if load_nodes:
        assert report.input_records, f"{spec.template_id}: expected LoadAudio input verification"
        assert all(record.hash_match for record in report.input_records)
        assert all(record.ok for record in report.input_records)

    audio_terminals = [
        (node_id, output_type)
        for node_id, output_type in spec.required_outputs
        if output_type in {"AUDIO", "MULTI", "STEMS"}
    ]
    if audio_terminals:
        assert report.output_records, f"{spec.template_id}: expected terminal output verification"
        assert all(record.hash_match for record in report.output_records)
        assert all(record.ok for record in report.output_records)

    manifest_outputs = {
        entry["node_id"]: entry["output"]
        for entry in manifest.get("nodes", [])
        if entry.get("output")
    }
    for node in workflow.nodes:
        node_cls = NODE_REGISTRY.get(node.type)
        if node_cls is None or node_cls.DETERMINISTIC is not False:
            continue
        if not any(
            output.get("type") in {"AUDIO", "MULTI", "STEMS"}
            for output in node_cls.describe().get("outputs", [])
        ):
            continue
        manifest_output = manifest_outputs.get(node.id)
        if not manifest_output or not _iter_audio_caches(manifest_output):
            continue
        ai_records = [record for record in report.ai_records if record.node_id == node.id]
        assert ai_records, f"{spec.template_id}: expected AI hop verification for {node.id} ({node.type})"
        assert all(record.deterministic is False for record in ai_records)
        assert all(record.sample_accurate is True for record in ai_records)
        assert all(record.hash_match for record in ai_records)
