from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow
from groovy.server.compare import analyze_ab_pair

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "ab-compare-demo.groovy.json"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "male-1.wav", tone, sr)
    registry = ModelRegistry(tmp_path)
    registry.installer.install("deepfilternet-v3")
    return tmp_path


def _workflow(project_dir: Path) -> Workflow:
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/male-1.wav"
    return workflow


def test_ab_compare_demo_template_renders(project_dir: Path) -> None:
    executor = Executor(project_dir)
    result = executor.execute(_workflow(project_dir), target_nodes=["n4"])
    assert result.status == "completed", result.error
    assert set(result.outputs) == {"n1", "n2", "n3", "n4"}


def test_ab_compare_demo_hops(project_dir: Path) -> None:
    executor = Executor(project_dir)
    registry = ModelRegistry(project_dir)
    workflow = _workflow(project_dir)
    result = executor.execute(workflow, target_nodes=["n4"])
    assert result.status == "completed", result.error

    outputs = result.outputs
    assert outputs["n3"]["cache_id"] == outputs["n4"]["cache_id"]

    cache = executor.cache
    pairs = {
        ("n1", "n2"): "substantial",
        ("n2", "n3"): "substantial",
        ("n1", "n3"): "substantial",
        ("n3", "n4"): "no_difference",
    }
    for (left, right), expected_verdict in pairs.items():
        analysis = analyze_ab_pair(
            cache,
            registry,
            cache_id_a=outputs[left]["cache_id"],
            cache_id_b=outputs[right]["cache_id"],
            label_a=left,
            label_b=right,
            model_id="groovy-signal-diff",
        )
        assert analysis["verdict"] == expected_verdict, (
            f"{left} vs {right}: expected {expected_verdict}, got {analysis['verdict']} "
            f"({analysis['verdict_summary']})"
        )

    redirected = analyze_ab_pair(
        cache,
        registry,
        cache_id_a=outputs["n2"]["cache_id"],
        cache_id_b=outputs["n3"]["cache_id"],
        label_a="Denoise (n2)",
        label_b="Normalize (n3)",
        model_id="groovy-signal-diff",
        question="What changed between denoise and normalize?",
    )
    assert redirected["verdict"] in {"moderate", "substantial"}
    assert redirected["difference_count"] >= 1
