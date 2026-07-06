from __future__ import annotations

from pathlib import Path

import pytest
from groovy.registry import ModelRegistry
from groovy.registry.catalog import ModelCatalog


def test_catalog_search_denoise() -> None:
    catalog = ModelCatalog()
    results = catalog.search("denoise podcast")
    ids = {m.id for m in results}
    assert "deepfilternet-v3" in ids


def test_model_install_dev_stub(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    state = registry.installer.install("deepfilternet-v3")
    assert state.status == "ready"
    marker = tmp_path / ".groovy" / "models" / "deepfilternet-v3" / "installed.json"
    assert marker.exists()


def test_similar_models_on_failure(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    registry.store.mark_failed("demucs-v4", "checksum mismatch")
    recovery = registry.installer.recovery_suggestions("demucs-v4")
    assert recovery["error"]
    assert len(recovery["similar_models"]) >= 1
