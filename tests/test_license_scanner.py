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
    if result["swap_suggestions"]:
        alts = result["swap_suggestions"][0]["alternatives"]
        assert len(alts) >= 1


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
