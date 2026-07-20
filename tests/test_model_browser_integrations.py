from __future__ import annotations

from pathlib import Path

from groovy.registry import ModelRegistry
from groovy.registry.studio_settings import StudioSettingsStore, inference_stub_active
from groovy.registry.workflow_models import missing_models_for_workflow
from groovy.schema.models import Workflow


def test_studio_settings_hf_token_priority(monkeypatch, tmp_path: Path) -> None:
    store = StudioSettingsStore(tmp_path)
    store.save({"hf_token": "from-settings"})
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert store.hf_token() == "from-settings"

    monkeypatch.setenv("HF_TOKEN", "from-env")
    assert store.hf_token() == "from-env"

    view = store.public_view()
    assert view["hf_token_set"] is True
    assert view["hf_token_source"] == "environment"


def test_studio_settings_inference_mode_default_real(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GROOVY_INFERENCE_STUB", raising=False)
    store = StudioSettingsStore(tmp_path)
    view = store.public_view()
    assert view["inference_mode"] == "real"
    assert view["inference_effective"] == "real"
    assert view["inference_stub_active"] is False
    assert view["project_dir"] == str(tmp_path.resolve())
    assert view["cache_dir"].endswith(".groovy/cache")


def test_studio_settings_inference_mode_persist(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GROOVY_INFERENCE_STUB", raising=False)
    store = StudioSettingsStore(tmp_path)
    view = store.save({"inference_mode": "stub"})
    assert view["inference_mode"] == "stub"
    assert view["inference_effective"] == "stub"
    assert view["inference_stub_active"] is True
    assert inference_stub_active(project_dir=tmp_path) is True

    view = store.save({"inference_mode": "real"})
    assert view["inference_stub_active"] is False
    assert inference_stub_active(project_dir=tmp_path) is False


def test_inference_stub_env_overrides_settings(monkeypatch, tmp_path: Path) -> None:
    store = StudioSettingsStore(tmp_path)
    store.save({"inference_mode": "stub"})

    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "0")
    view = store.public_view()
    assert view["inference_mode"] == "stub"
    assert view["inference_effective"] == "real"
    assert view["inference_effective_source"] == "environment"
    assert inference_stub_active(project_dir=tmp_path) is False

    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    store.save({"inference_mode": "real"})
    view = store.public_view()
    assert view["inference_mode"] == "real"
    assert view["inference_effective"] == "stub"
    assert inference_stub_active(project_dir=tmp_path) is True


def test_missing_models_for_workflow(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    workflow = Workflow.model_validate(
        {
            "schema_version": "1.0.0",
            "groovy_version": "0.1.0",
            "id": "wf-missing",
            "metadata": {"title": "Missing models"},
            "nodes": [
                {
                    "id": "n1",
                    "type": "SeparateStems",
                    "pos": {"x": 0, "y": 0},
                    "widgets": {"model": "demucs-v4"},
                }
            ],
            "links": [],
            "groups": [],
        }
    )
    missing = missing_models_for_workflow(workflow, registry.catalog, registry.store)
    assert any(entry["model_id"] == "demucs-v4" and entry["reason"] == "not_installed" for entry in missing)
