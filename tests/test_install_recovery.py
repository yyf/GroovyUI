from __future__ import annotations

from groovy.registry import ModelRegistry
from groovy.registry.agent.install_recovery import install_recovery


def test_install_recovery_includes_explain_and_ranked_similar(tmp_path) -> None:
    registry = ModelRegistry(tmp_path)
    registry.store.mark_failed("deepfilternet-v3", "Network connection reset while downloading")
    result = install_recovery(
        registry.catalog, registry.store, registry.installer, "deepfilternet-v3"
    )
    assert result["agent"] == "install_recovery_v1"
    assert result["explain"]
    assert result["suggested_fixes"]
    assert result["similar_models"]
    assert any(card.get("similar_rationale") for card in result["similar_models"])


def test_install_recovery_inference_runtime_not_ready(tmp_path) -> None:
    registry = ModelRegistry(tmp_path)
    registry.store.mark_failed(
        "demucs-v4",
        "Inference runtime not ready for demucs-v4. Reinstall from Model Browser.",
    )
    result = install_recovery(
        registry.catalog, registry.store, registry.installer, "demucs-v4"
    )
    assert result["agent"] == "install_recovery_v1"
    joined = " ".join(result["suggested_fixes"]).lower()
    assert "reinstall" in joined or "python" in joined or "deps" in joined
