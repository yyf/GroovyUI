from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
from groovy.executor import Executor
from groovy.executor.node_cache import compute_node_signature
from groovy.nodes.core import register_all as register_core
from groovy.schema.models import Workflow

register_core()

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "hello-groovy.groovy.json"


def test_compute_node_signature_stable() -> None:
    sig_a = compute_node_signature("Normalize", {"target_lufs": -16.0}, {"audio": type("Buf", (), {"id": "abc"})()})
    sig_b = compute_node_signature("Normalize", {"target_lufs": -16.0}, {"audio": type("Buf", (), {"id": "abc"})()})
    sig_c = compute_node_signature("Normalize", {"target_lufs": -14.0}, {"audio": type("Buf", (), {"id": "abc"})()})
    assert sig_a == sig_b
    assert sig_a != sig_c


def test_executor_skips_unchanged_nodes(tmp_path: Path) -> None:
    assets = tmp_path / "assets" / "samples"
    assets.mkdir(parents=True)
    sr = 48000
    tone = 0.25 * np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, int(sr * 0.5), endpoint=False))
    sf.write(assets / "dialogue_48k.wav", tone, sr)

    workflow = Workflow.model_validate(json.loads(TEMPLATE.read_text()))
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            node.widgets["path"] = "assets/samples/dialogue_48k.wav"

    executor = Executor(tmp_path)
    first = executor.execute(workflow, target_nodes=["n3"])
    assert first.status == "completed", first.error
    second = executor.execute(workflow, target_nodes=["n3"])
    assert second.status == "completed", second.error

    manifest = json.loads(Path(first.manifest_path).read_text())
    hits = [n for n in manifest["nodes"] if n.get("cache_hit")]
    assert len(hits) == 0

    manifest2 = json.loads(Path(second.manifest_path).read_text())
    hits2 = [n for n in manifest2["nodes"] if n.get("cache_hit")]
    assert len(hits2) >= 2
