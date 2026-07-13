from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from groovy.registry.agent.curator import draft_from_discover, save_discover_draft
from groovy.registry.discover import discover_models

SAMPLE_HF = [
    {
        "id": "DeepFilterNet/DeepFilterNet3",
        "author": "DeepFilterNet",
        "downloads": 1200,
        "likes": 42,
        "lastModified": "2025-03-01T00:00:00.000Z",
        "tags": ["audio", "speech-enhancement", "pytorch"],
        "pipeline_tag": "audio-to-audio",
        "cardData": {"license": "MIT", "description": "Speech denoising model."},
    }
]


def test_discover_models_normalizes_hf_payload() -> None:
    results = discover_models("podcast", task_type="denoise", fetch_json=lambda _url: SAMPLE_HF)
    assert len(results) == 1
    entry = results[0]
    assert entry["external_id"] == "hf:DeepFilterNet/DeepFilterNet3"
    assert entry["trust"] == "external"
    assert "denoise" in entry["task_types"]
    assert entry["suggested_compatible_nodes"] == ["Denoise"]
    assert entry["source_url"].startswith("https://huggingface.co/")


def test_save_discover_draft(tmp_path: Path) -> None:
    entry = discover_models(fetch_json=lambda _url: SAMPLE_HF)[0]
    manifest, created = save_discover_draft(tmp_path / "drafts", entry)
    assert created is True
    assert manifest.status == "draft"
    assert manifest.trust == "draft"
    assert manifest.id.endswith("-draft")
    saved = json.loads((tmp_path / "drafts" / f"{manifest.id}.json").read_text())
    assert saved["source"] == entry["external_id"]


def test_save_discover_draft_is_idempotent(tmp_path: Path) -> None:
    entry = discover_models(fetch_json=lambda _url: SAMPLE_HF)[0]
    save_discover_draft(tmp_path / "drafts", entry)
    _, created = save_discover_draft(tmp_path / "drafts", entry)
    assert created is False


def test_draft_from_discover_uses_external_id_slug() -> None:
    manifest = draft_from_discover(
        {
            "external_id": "hf:org/cool-denoise-model",
            "name": "Cool Denoise",
            "description": "Test",
            "task_types": ["denoise"],
            "license": {"spdx": "MIT", "commercial_ok": True, "confidence": 0.5},
            "suggested_compatible_nodes": ["Denoise"],
        }
    )
    assert manifest.id == "org-cool-denoise-model-draft"


def test_install_blocked_for_draft(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import groovy.server.main as main

    monkeypatch.setenv("GROOVY_PROJECT_DIR", str(tmp_path))
    main.PROJECT_DIR = tmp_path
    main._registry = main.ModelRegistry(tmp_path)
    main._install_threads.clear()

    entry = discover_models(fetch_json=lambda _url: SAMPLE_HF)[0]
    manifest, _ = save_discover_draft(main._registry.draft_dir, entry)

    client = TestClient(main.app)
    response = client.post(f"/api/models/{manifest.id}/install")
    assert response.status_code == 400
    assert "Draft" in response.json()["detail"]


def test_discover_endpoint_returns_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import groovy.server.main as main

    monkeypatch.setenv("GROOVY_PROJECT_DIR", str(tmp_path))
    main.PROJECT_DIR = tmp_path
    main._registry = main.ModelRegistry(tmp_path)
    monkeypatch.setattr(
        main,
        "discover_models",
        lambda *args, **kwargs: discover_models(fetch_json=lambda _url: SAMPLE_HF),
    )

    client = TestClient(main.app)
    response = client.get("/api/models/discover", params={"query": "denoise", "task_type": "denoise"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1


def test_search_includes_saved_drafts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import groovy.server.main as main

    monkeypatch.setenv("GROOVY_PROJECT_DIR", str(tmp_path))
    main.PROJECT_DIR = tmp_path
    main._registry = main.ModelRegistry(tmp_path)

    entry = discover_models(fetch_json=lambda _url: SAMPLE_HF)[0]
    save_discover_draft(main._registry.draft_dir, entry)

    client = TestClient(main.app)
    response = client.post("/api/models/search", json={"query": "deepfilter", "task_type": "denoise"})
    assert response.status_code == 200
    ids = {model["id"] for model in response.json()["models"]}
    assert any(model_id.endswith("-draft") for model_id in ids)
