from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.registry.studio_settings import StudioSettingsStore
import groovy.server.main as main
from groovy.executor import Executor

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
