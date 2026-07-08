from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow
import groovy.server.main as main

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "ab-compare-demo.groovy.json"


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(assets / "male-1.wav", tone, sr)

    monkeypatch.setenv("GROOVY_PROJECT_DIR", str(tmp_path))
    main.PROJECT_DIR = tmp_path
    main._executor = Executor(tmp_path)
    main._registry = ModelRegistry(tmp_path)
    return TestClient(main.app)


def _render_demo(api_client: TestClient, tmp_path: Path) -> dict[str, dict]:
    registry = ModelRegistry(tmp_path)
    registry.installer.install("deepfilternet-v3")
    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/male-1.wav"

    executor = Executor(tmp_path)
    result = executor.execute(workflow, target_nodes=["n4"])
    assert result.status == "completed", result.error
    return result.outputs


def test_health_exposes_compare_api(api_client: TestClient) -> None:
    health = api_client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["compare_api"] is True


def test_compare_analyze_route(api_client: TestClient, tmp_path: Path) -> None:
    outputs = _render_demo(api_client, tmp_path)
    cache_id_a = outputs["n2"]["cache_id"]
    cache_id_b = outputs["n3"]["cache_id"]

    waveform = api_client.get(f"/api/cache/{cache_id_a}/waveform")
    assert waveform.status_code == 200

    analysis = api_client.post(
        "/api/compare/analyze",
        json={
            "cache_id_a": cache_id_a,
            "cache_id_b": cache_id_b,
            "model_id": "groovy-signal-diff",
            "label_a": "Denoise",
            "label_b": "Normalize",
            "question": "What changed?",
        },
    )
    assert analysis.status_code == 200, analysis.text
    body = analysis.json()
    assert body["verdict"] in {"moderate", "substantial"}
    assert body["difference_count"] >= 1


def test_compare_analyze_whisper_stub(api_client: TestClient, tmp_path: Path) -> None:
    outputs = _render_demo(api_client, tmp_path)
    analysis = api_client.post(
        "/api/compare/analyze",
        json={
            "cache_id_a": outputs["n1"]["cache_id"],
            "cache_id_b": outputs["n2"]["cache_id"],
            "model_id": "whisper-ab-compare",
        },
    )
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["mode"] == "transcript"
