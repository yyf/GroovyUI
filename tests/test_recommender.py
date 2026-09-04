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


def test_recommender_respects_node_type_filter(tmp_path) -> None:
    registry = ModelRegistry(tmp_path)
    result = recommend_models(
        registry.catalog,
        registry.store,
        prompt="denoise podcast speech",
        node_type="Denoise",
    )
    assert result["results"]
    for item in result["results"]:
        assert "Denoise" in item["model"]["compatible_nodes"]
    assert result.get("workflow_handoff_hint")


def test_catalog_similar_ranks_task_peers_when_seed_empty(tmp_path) -> None:
    registry = ModelRegistry(tmp_path)
    # demucs-v4 seed peers may be short; ranking should still surface HT / objects peers.
    peers = registry.catalog.similar("demucs-v4", limit=4)
    assert peers
    assert all(m.id != "demucs-v4" for m in peers)
    assert any(
        "stem-separation" in m.task_types or "SeparateStems" in m.compatible_nodes for m in peers
    )
