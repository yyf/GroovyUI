from __future__ import annotations

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


def test_content_credentials_mode_and_status_are_optional_by_default(
    api_client: TestClient,
) -> None:
    settings = api_client.get("/api/settings/studio")
    assert settings.status_code == 200
    assert settings.json()["content_credentials_mode"] == "off"
    assert settings.json()["content_credentials_effective"] == "off"

    status = api_client.get("/api/c2pa/status")
    assert status.status_code == 200
    assert status.json()["configured"] is False
    assert status.json()["provider"] == "none"
    assert status.json()["effective_mode"] == "off"

    updated = api_client.post(
        "/api/settings/studio",
        json={"content_credentials_mode": "sign_if_configured"},
    )
    assert updated.status_code == 200
    assert updated.json()["content_credentials_effective"] == "sign_if_configured"
    status = api_client.get("/api/c2pa/status")
    assert status.json()["effective_mode"] == "sign_if_configured"

    bad = api_client.post(
        "/api/settings/studio",
        json={"content_credentials_mode": "pretend_signed"},
    )
    assert bad.status_code == 400


def test_c2pa_environment_mode_overrides_project_setting(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    api_client.post(
        "/api/settings/studio",
        json={"content_credentials_mode": "sign_if_configured"},
    )
    monkeypatch.setenv("GROOVY_C2PA_MODE", "required")

    status = api_client.get("/api/c2pa/status")

    assert status.json()["mode"] == "sign_if_configured"
    assert status.json()["effective_mode"] == "required"
    assert status.json()["effective_source"] == "environment"


def test_clear_render_cache(api_client: TestClient, tmp_path: Path) -> None:
    cache = tmp_path / ".groovy" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "deadbeef.f64").write_bytes(b"x")
    (cache / "deadbeef.meta.json").write_text("{}")
    state = cache / "node_state" / "wf"
    state.mkdir(parents=True)
    (state / "n1.json").write_text("{}")
    res = api_client.post("/api/cache/clear")
    assert res.status_code == 200
    assert res.json()["removed"] == 3
    assert list(cache.iterdir()) == []


def test_studio_settings_hf_token_api_roundtrip(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    fake = "hf_test_not_a_real_token"

    post = api_client.post("/api/settings/studio", json={"hf_token": fake})
    assert post.status_code == 200
    body = post.json()
    assert body["hf_token_set"] is True
    assert body["hf_token_source"] == "settings"
    assert "hf_token" not in body

    get_res = api_client.get("/api/settings/studio")
    assert get_res.status_code == 200
    assert get_res.json()["hf_token_set"] is True
    assert get_res.json()["hf_token_source"] == "settings"
    assert "hf_token" not in get_res.json()

    cleared = api_client.post("/api/settings/studio", json={"hf_token": None})
    assert cleared.status_code == 200
    assert cleared.json()["hf_token_set"] is False
    assert cleared.json()["hf_token_source"] is None
