from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.executor.batch import run_batch_render
from groovy.nodes.core import register_all
from groovy.registry import ModelRegistry
from groovy.registry.agent.license_scanner import scan_workflow_licenses
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata

register_all()


def test_license_scan_flags_nc_model(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="license-scan-test",
        metadata=WorkflowMetadata(title="NC model test"),
        nodes=[
            NodeInstance(
                id="n1",
                type="GenerateAudio",
                widgets={"model": "musicgen-small", "prompt": "test"},
            )
        ],
        links=[],
    )
    result = scan_workflow_licenses(workflow, registry)
    assert result["scan_ok"] is False
    assert any(flag["code"] == "NC_MODEL" for flag in result["flags"])
    # MusicGen currently has no commercial GenerateAudio peer in the seed catalog.
    # Prefer an empty suggestion list over an incompatible task-peer swap.
    for swap in result["swap_suggestions"]:
        assert all(
            alt["model_id"] != "diffsinger-opencpop" for alt in swap["alternatives"]
        )


def test_license_scan_swaps_require_node_compatibility(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="midi-musicgen-scan",
        metadata=WorkflowMetadata(title="MIDI MusicGen license"),
        nodes=[
            NodeInstance(
                id="n1",
                type="MIDIToAudio",
                widgets={"model": "musicgen-melody-small", "prompt": "test"},
            )
        ],
        links=[],
    )
    result = scan_workflow_licenses(workflow, registry)
    assert result["scan_ok"] is False
    for swap in result["swap_suggestions"]:
        assert swap["node_type"] == "MIDIToAudio"
        for alt in swap["alternatives"]:
            manifest = registry.catalog.get(alt["model_id"])
            assert manifest is not None
            assert "MIDIToAudio" in manifest.compatible_nodes


def test_license_optimizer_previews_explicit_commercial_chain_swap(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="tts-optimizer",
        metadata=WorkflowMetadata(title="TTS optimizer"),
        nodes=[
            NodeInstance(
                id="n1",
                type="TTS",
                widgets={"model": "f5-tts-base", "text": "hello"},
            )
        ],
        links=[],
    )
    result = scan_workflow_licenses(workflow, registry)
    plan = result["optimization_plan"]
    assert plan["can_optimize"] is True
    assert plan["unresolved"] == []
    assert len(plan["swaps"]) == 1
    swap = plan["swaps"][0]
    assert swap["from_model_id"] == "f5-tts-base"
    replacement = registry.catalog.get(swap["to_model_id"])
    assert replacement is not None
    assert replacement.license.commercial_ok is True
    assert "TTS" in replacement.compatible_nodes


def test_preflight_estimates_missing_only_download_and_peak_vram(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="preflight-estimate",
        metadata=WorkflowMetadata(title="Preflight estimate"),
        nodes=[
            NodeInstance(id="n1", type="Denoise", widgets={"model": "deepfilternet-v3"}),
            NodeInstance(id="n2", type="WhisperSTT", widgets={"model": "whisper-small-en"}),
        ],
        links=[],
    )
    first = scan_workflow_licenses(workflow, registry)["preflight"]
    assert first["download"]["known_mb"] == 550.0
    assert first["peak_vram_gb"] == 1.0
    assert first["render_time"]["low_seconds"] > 0
    assert first["render_time"]["high_seconds"] > first["render_time"]["low_seconds"]
    assert "disk_free_mb" in first["machine"]
    assert isinstance(first["checks"], list)
    assert first["checks"]

    registry.store.mark_ready("deepfilternet-v3")
    second = scan_workflow_licenses(workflow, registry)["preflight"]
    assert second["download"]["known_mb"] == 500.0
    assert "deepfilternet-v3" in second["download"]["already_installed"]


def test_batch_render_multiple_files(tmp_path: Path) -> None:
    assets = tmp_path / "assets" / "batch_in"
    assets.mkdir(parents=True)
    sr = 48000
    for index, freq in enumerate((220, 330), start=1):
        tone = 0.2 * np.sin(2 * np.pi * freq * np.linspace(0, 0.25, int(sr * 0.25), endpoint=False))
        sf.write(assets / f"clip_{index}.wav", tone, sr)

    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="batch-test",
        metadata=WorkflowMetadata(title="Batch test"),
        nodes=[
            NodeInstance(id="n1", type="LoadAudio", widgets={"path": "assets/batch_in/clip_1.wav"}),
            NodeInstance(id="n2", type="Preview", widgets={}),
        ],
        links=[
            Link(id="l1", from_=["n1", 0], to=["n2", 0], type="AUDIO"),
        ],
    )
    executor = Executor(tmp_path)
    result = run_batch_render(
        executor,
        workflow,
        input_dir="assets/batch_in",
        file_glob="*.wav",
        target_nodes=["n2"],
    )
    assert result["total"] == 2
    assert result["completed"] == 2
    assert all(run["status"] == "completed" for run in result["runs"])
