from __future__ import annotations

from groovy.registry import ModelRegistry
from groovy.registry.agent.recommender import recommend_models


def test_recommender_podcast_denoise(tmp_path) -> None:
    registry = ModelRegistry(tmp_path)
    result = recommend_models(
        registry.catalog,
        registry.store,
        prompt="commercial-friendly podcast denoise",
        commercial_ok=True,
    )
    assert result["inferred_task"] == "denoise"
    assert len(result["results"]) >= 1
    top = result["results"][0]
    assert top["model"]["id"]
    assert top["rationale"]


def test_recommender_stem_separation(tmp_path) -> None:
    registry = ModelRegistry(tmp_path)
    result = recommend_models(
        registry.catalog,
        registry.store,
        prompt="separate vocals from instrumental",
    )
    assert result["inferred_task"] == "stem-separation"
    ids = [item["model"]["id"] for item in result["results"]]
    assert any("demucs" in mid or "stem" in mid for mid in ids)
