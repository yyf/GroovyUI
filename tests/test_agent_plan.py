from __future__ import annotations

from pathlib import Path

from groovy.registry import ModelRegistry
from groovy.registry.agent.planner import plan_agent_request

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


def test_plan_podcast_returns_actions(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    result = plan_agent_request(
        registry.catalog,
        registry.store,
        registry,
        prompt="commercial podcast denoise cleanup",
        templates_dir=TEMPLATES,
        commercial_ok=True,
    )
    assert result["agent"] == "plan_v1"
    assert result["mode"] == "plan"
    assert "recommend_models" in result["tools_used"]
    assert "suggest_workflows" in result["tools_used"]
    types = {action["type"] for action in result["actions"]}
    assert "install_model" in types
    assert "apply_template" in types
    assert all(
        action["type"] in {"install_model", "drop_node", "apply_template", "open_compliance"}
        for action in result["actions"]
    )
    assert "Deterministic" in result["notes"]


def test_plan_empty_prompt(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    result = plan_agent_request(
        registry.catalog,
        registry.store,
        registry,
        prompt="   ",
        templates_dir=TEMPLATES,
    )
    assert result["actions"] == []
    assert result["mode"] == "empty"
