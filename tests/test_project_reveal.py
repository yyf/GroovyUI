from __future__ import annotations

import json
from pathlib import Path

import groovy.server.main as main
import pytest
from fastapi.testclient import TestClient
from groovy.executor import Executor
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.registry.studio_settings import StudioSettingsStore

register_core()
register_ai()


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("GROOVY_PROJECT_DIR", str(tmp_path))
    main.PROJECT_DIR = tmp_path
    main._executor = Executor(tmp_path)
    main._registry = ModelRegistry(tmp_path)
    main._studio_settings = StudioSettingsStore(tmp_path)
    return TestClient(main.app)


def test_reveal_rejects_path_outside_project(api_client: TestClient, tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-reveal.txt"
    outside.write_text("nope")
    res = api_client.post("/api/project/reveal", json={"path": str(outside)})
    assert res.status_code == 400


def test_reveal_missing_file(api_client: TestClient, tmp_path: Path) -> None:
    res = api_client.post("/api/project/reveal", json={"path": "exports/missing.wav"})
    assert res.status_code == 404


def test_reveal_opens_existing_file(
    api_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "exports" / "take.wav"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x")
    calls: list[list[str]] = []

    def fake_popen(cmd, **kwargs):
        calls.append(list(cmd))

        class Proc:
            pass

        return Proc()

    monkeypatch.setattr(main.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(main.platform, "system", lambda: "Darwin")
    res = api_client.post("/api/project/reveal", json={"path": str(target)})
    assert res.status_code == 200
    assert calls and calls[0][:2] == ["open", "-R"]


def test_share_workflow_writes_project_share_file(
    api_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = {
        "schema_version": "1.0.0",
        "groovy_version": "0.1.0",
        "id": "share-test",
        "metadata": {"title": "My Shared Patch"},
        "nodes": [],
        "links": [],
        "groups": [],
    }
    destination = tmp_path / "share" / "custom-name.groovy.json"
    picker_args: list[tuple[Path, str]] = []

    def fake_picker(share_dir: Path, suggested_name: str) -> Path:
        picker_args.append((share_dir, suggested_name))
        return destination

    monkeypatch.setattr(main, "_choose_workflow_share_destination", fake_picker)

    res = api_client.post("/api/project/share", json={"workflow": workflow})

    assert res.status_code == 200
    assert picker_args == [(tmp_path / "share", "my-shared-patch.groovy.json")]
    assert res.json()["relative_path"] == "share/custom-name.groovy.json"
    assert destination.exists()
    assert json.loads(destination.read_text(encoding="utf-8")) == workflow


def test_model_provenance_metadata_includes_license_and_hash_status(
    api_client: TestClient,
) -> None:
    metadata = main._model_provenance_metadata("deepfilternet-v3")

    assert metadata is not None
    assert metadata["name"] == "DeepFilterNet v3"
    assert metadata["task_types"] == ["denoise"]
    assert metadata["license"]["spdx"] == "MIT"
    assert metadata["weights_hash_status"] == "unavailable"
