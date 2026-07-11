from __future__ import annotations

from pathlib import Path

from groovy.registry import ModelRegistry
from groovy.registry.studio_settings import StudioSettingsStore
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
