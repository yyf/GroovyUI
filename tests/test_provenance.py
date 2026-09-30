from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.executor.cache import CacheStore
from groovy.executor.provenance import (
    apply_record_integrity,
    build_lineage_chain,
    build_lineage_graph,
    disclosure_summary,
    sanitize_widgets,
    summarize_workflow_outputs,
    verify_record_integrity,
)
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow

register_all()
register_ai()

ROOT = Path(__file__).resolve().parents[1]
from template_fixtures import require_template
TEMPLATE = require_template("podcast-denoise")


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    duration = 0.5
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "dialogue_48k.wav", tone, sr)
    registry = ModelRegistry(tmp_path)
    registry.installer.install("deepfilternet-v3")
    return tmp_path


def test_provenance_chain_has_parents(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/dialogue_48k.wav"

    executor = Executor(project_dir)
    result = executor.execute(workflow, target_nodes=["n4"])
    assert result.status == "completed", result.error

    preview_id = result.outputs["n4"]["cache_id"]
    chain = build_lineage_chain(executor.cache, preview_id)
    assert len(chain) >= 2
    assert chain[0]["node"]["node_type"] in {"Normalize", "Preview"}
    disclosure = disclosure_summary(chain)
    assert "AI" in disclosure or "ai" in disclosure.lower()

    summary = summarize_workflow_outputs(executor.cache, result.outputs, target_node_id="n4")
    assert summary["contains_ai"] is True
    assert summary["focus_disclosure"]


def test_save_audio_writes_provenance_sidecar(project_dir: Path) -> None:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/dialogue_48k.wav"

    executor = Executor(
        project_dir,
        model_metadata_resolver=lambda model_id: {
            "name": "DeepFilterNet v3",
            "version": "0.5.6",
            "task_types": ["denoise"],
            "license": {"spdx": "MIT", "commercial_ok": True},
            "weights": [{"filename": "model.tar.gz", "sha256": "sha256:abc"}],
        }
        if model_id == "deepfilternet-v3"
        else None,
    )
    result = executor.execute(workflow, target_nodes=["n2"])
    assert result.status == "completed"

    cache_id = result.outputs["n2"]["cache_id"]
    from groovy.nodes.core.nodes import SaveAudio

    node = SaveAudio()
    from groovy.executor.engine import JobContext

    ctx = JobContext(project_dir=project_dir, cache=executor.cache, job_id="test")
    node.bind_context(ctx)
    buffer, _ = executor.cache.load_audio(cache_id)
    written, = node.run(audio=buffer, filename="exports/test-out.wav")
    out = Path(written)
    sidecar = out.with_name(f"{out.stem}.provenance.json")
    assert out.name.startswith("test-out-")
    assert sidecar.exists()
    record = json.loads(sidecar.read_text())
    audio_digest = hashlib.sha256(out.read_bytes()).hexdigest()
    assert record["artifact"]["filename"] == out.name
    assert record["artifact"]["format"] == "WAV"
    assert record["artifact"]["sample_rate"] == 48000
    assert record["artifact"]["file_hash"] == f"sha256:{audio_digest}"
    assert record["artifact"]["source_audio_content_hash"].startswith("sha256:")
    assert len(record["lineage"]["nodes"]) >= 2
    assert record["lineage"]["edges"]
    assert "AI" in record["disclosure"]["summary"]
    assert record["disclosure"]["not_legal_advice"] is True
    assert record["compliance"]["review_required"] is True
    assert record["compliance"]["models"][0]["license"]["spdx"] == "MIT"
    assert verify_record_integrity(record) is True
    model = record["models"][0]
    assert model["registry_id"] == "deepfilternet-v3"
    assert model["version"] == "0.5.6"
    assert model["license"]["spdx"] == "MIT"
    assert str(project_dir) not in sidecar.read_text()


def test_provenance_redacts_prompts_secrets_and_absolute_paths() -> None:
    widgets, conditioning = sanitize_widgets(
        {
            "prompt": "private client prompt",
            "api_token": "hf_secret",
            "source_path": "/Users/client/private.wav",
            "relative_path": "assets/reference.wav",
            "seed": 42,
        }
    )

    payload = json.dumps(widgets)
    assert "private client prompt" not in payload
    assert "hf_secret" not in payload
    assert "/Users/client" not in payload
    assert widgets["prompt"]["sha256"].startswith("sha256:")
    assert widgets["api_token"] == "[redacted]"
    assert widgets["source_path"] == {
        "path_redacted": True,
        "basename": "private.wav",
    }
    assert widgets["relative_path"] == "assets/reference.wav"
    assert conditioning["prompts_redacted"] is True

    record = apply_record_integrity({"schema_version": "1.0.0", "parents": []})
    assert verify_record_integrity(record) is True
    record["schema_version"] = "tampered"
    assert verify_record_integrity(record) is False


def test_export_lineage_preserves_branching_dag(tmp_path: Path) -> None:
    cache = CacheStore(tmp_path)
    for cache_id in ("left", "right"):
        cache.write_provenance(
            cache_id,
            apply_record_integrity(
                {
                    "schema_version": "1.1.0",
                    "cache_id": cache_id,
                    "node": {"node_id": cache_id, "node_type": "LoadAudio"},
                    "contribution": {"class": "human_recorded"},
                    "models": [],
                    "parents": [],
                }
            ),
        )
    cache.write_provenance(
        "mix",
        apply_record_integrity(
            {
                "schema_version": "1.1.0",
                "cache_id": "mix",
                "node": {"node_id": "mix", "node_type": "Mix"},
                "contribution": {"class": "mixed"},
                "models": [],
                "parents": [
                    {"cache_id": "left"},
                    {"cache_id": "right"},
                ],
            }
        ),
    )

    lineage = build_lineage_graph(cache, "mix")

    assert {node["cache_id"] for node in lineage["nodes"]} == {
        "left",
        "right",
        "mix",
    }
    assert {
        (edge["from_cache_id"], edge["to_cache_id"])
        for edge in lineage["edges"]
    } == {("left", "mix"), ("right", "mix")}
