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
    monkeypatch.delenv("GROOVY_INFERENCE_STUB", raising=False)
    monkeypatch.setenv("GROOVY_PROJECT_DIR", str(tmp_path))
    main.PROJECT_DIR = tmp_path
    main._executor = Executor(tmp_path)
    main._registry = ModelRegistry(tmp_path)
    main._studio_settings = StudioSettingsStore(tmp_path)
    return TestClient(main.app)


def test_studio_settings_inference_roundtrip(api_client: TestClient) -> None:
    get_res = api_client.get("/api/settings/studio")
    assert get_res.status_code == 200
    body = get_res.json()
    assert body["inference_mode"] == "real"
    assert body["inference_stub_active"] is False
    assert "project_dir" in body
    assert "cache_dir" in body

    post = api_client.post("/api/settings/studio", json={"inference_mode": "stub"})
    assert post.status_code == 200
    assert post.json()["inference_stub_active"] is True

    health = api_client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["inference_stub_active"] is True
    assert health.json()["inference_effective"] == "stub"

    bad = api_client.post("/api/settings/studio", json={"inference_mode": "live"})
    assert bad.status_code == 400


def test_clear_render_cache(api_client: TestClient, tmp_path: Path) -> None:
    cache = tmp_path / ".groovy" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "deadbeef.f64").write_bytes(b"x")
    (cache / "deadbeef.meta.json").write_text("{}")
    res = api_client.post("/api/cache/clear")
    assert res.status_code == 200
    assert res.json()["removed"] == 2
    assert list(cache.iterdir()) == []
