from __future__ import annotations

from groovy.registry import ModelRegistry
from groovy.registry.agent.install_recovery import install_recovery
from groovy.registry.store import InstallStore


def test_install_recovery_includes_explain_and_ranked_similar(tmp_path) -> None:
    registry = ModelRegistry(tmp_path)
    store = InstallStore(tmp_path)
    store.mark_failed("deepfilternet-v3", "Network connection reset while downloading")
    result = install_recovery(registry.catalog, store, registry.installer, "deepfilternet-v3")
    assert result["agent"] == "install_recovery_v1"
    assert result["explain"]
    assert result["suggested_fixes"]
    assert result["similar_models"]
    assert any(card.get("similar_rationale") for card in result["similar_models"])
