from __future__ import annotations

import json
from pathlib import Path

import pytest
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
    assert result["planner"] == "deterministic"
    assert result["deterministic"] is True
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
    assert result["deterministic"] is True


def test_plan_llm_needs_api_key(tmp_path: Path) -> None:
    from groovy.registry.agent.llm_planner import plan_agent_request_llm

    registry = ModelRegistry(tmp_path)
    result = plan_agent_request_llm(
        registry.catalog,
        registry.store,
        registry,
        prompt="podcast denoise",
        templates_dir=TEMPLATES,
        api_key=None,
    )
    assert result["planner"] == "llm"
    assert result["deterministic"] is False
    assert result["mode"] == "needs_api_key"
    assert result["actions"] == []
    assert result["experimental"] is True


def test_plan_llm_composes_workflow_without_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from groovy.registry.agent import llm_planner

    registry = ModelRegistry(tmp_path)
    known = {"LoadAudio", "Denoise", "Preview", "SaveAudio"}

    def fake_call(*, api_key: str, system: str, user: str, model: str) -> str:
        assert api_key == "sk-ant-test-not-a-real-key"
        payload = json.loads(user)
        assert "models" not in payload
        assert "templates" not in payload
        assert payload["constraints"]["no_model_catalog"] is True
        assert payload["constraints"]["no_template_catalog"] is True
        assert payload["constraints"]["no_node_type_catalog"] is True
        assert payload["constraints"]["prefer_public_ai_models"] is True
        assert "allowed_node_types" not in payload
        assert "models" not in payload
        assert "templates" not in payload
        assert "patch-bay" in system.lower()
        assert "public" in system.lower()
        return json.dumps(
            {
                "inferred_task": "denoise",
                "notes": "Claude draft",
                "workflows": [
                    {
                        "summary": "Denoise then preview",
                        "rationale": "DeepFilterNet-style denoise hop",
                        "nodes": [
                            {"id": "n1", "type": "LoadAudio", "widgets": {}},
                            {
                                "id": "n2",
                                "type": "Denoise",
                                "widgets": {"model": "deepfilternet-v3"},
                            },
                            {"id": "n3", "type": "FantasyStemAI", "widgets": {}},
                            {"id": "n4", "type": "Preview", "widgets": {}},
                        ],
                        "links": [
                            {"id": "e1", "from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"},
                            {"id": "e2", "from": ["n2", 0], "to": ["n3", 0], "type": "AUDIO"},
                            {"id": "e3", "from": ["n3", 0], "to": ["n4", 0], "type": "AUDIO"},
                        ],
                    }
                ],
            }
        )

    monkeypatch.setattr(llm_planner, "_call_claude", fake_call)
    result = llm_planner.plan_agent_request_llm(
        registry.catalog,
        registry.store,
        registry,
        prompt="commercial podcast denoise",
        templates_dir=TEMPLATES,
        api_key="sk-ant-test-not-a-real-key",
        commercial_ok=True,
        known_node_types=known,
    )
    assert result["mode"] == "plan"
    assert result["agent"] == "plan_llm_v5"
    assert result["deterministic"] is False
    assert result["experimental"] is True
    assert len(result["actions"]) == 1
    action = result["actions"][0]
    assert action["type"] == "propose_workflow"
    assert action["summary"] == "Denoise then preview"
    assert action["unknown_node_types"] == ["FantasyStemAI"]
    assert len(action["workflow"]["nodes"]) == 4
    assert len(action["workflow"]["links"]) == 3
    denoise = next(n for n in action["workflow"]["nodes"] if n["type"] == "Denoise")
    assert denoise["widgets"]["model"] == "deepfilternet-v3"
    assert "Highlighted nodes" in result["notes"]


def test_remap_public_model_ref_to_local_registry(tmp_path: Path) -> None:
    from groovy.registry.agent.llm_planner import hydrate_composed_workflow

    registry = ModelRegistry(tmp_path)
    workflow, unknown, remaps, reason = hydrate_composed_workflow(
        {
            "summary": "TTS draft",
            "nodes": [
                {"id": "n1", "type": "Prompt", "widgets": {"text": "hi"}},
                {"id": "n3", "type": "TTS", "widgets": {"model": "coqui/XTTS-v2"}},
                {"id": "n4", "type": "Preview", "widgets": {}},
            ],
            "links": [
                {"id": "e1", "from": ["n1", 0], "to": ["n3", 0], "type": "TEXT"},
                {"id": "e2", "from": ["n3", 0], "to": ["n4", 0], "type": "AUDIO"},
            ],
        },
        index=0,
        known_node_types={"Prompt", "TTS", "Preview"},
        catalog=registry.catalog,
        node_model_defaults={"TTS": "kokoro-82m"},
    )
    assert reason == ""
    assert workflow is not None
    assert unknown == []
    tts = next(n for n in workflow["nodes"] if n["id"] == "n3")
    assert tts["widgets"]["model"] == "kokoro-82m"
    assert remaps
    assert remaps[0]["from"] == "coqui/XTTS-v2"
    assert remaps[0]["to"] == "kokoro-82m"


def test_fill_empty_load_audio_path(tmp_path: Path) -> None:
    from groovy.registry.agent.llm_planner import (
        DEFAULT_PLAN_LOAD_AUDIO_PATH,
        hydrate_composed_workflow,
    )

    registry = ModelRegistry(tmp_path)
    workflow, unknown, remaps, reason = hydrate_composed_workflow(
        {
            "summary": "Load draft",
            "nodes": [
                {"id": "n1", "type": "LoadAudio", "widgets": {}},
                {"id": "n2", "type": "Preview", "widgets": {}},
            ],
            "links": [{"id": "e1", "from": ["n1", 0], "to": ["n2", 0], "type": "AUDIO"}],
        },
        index=0,
        known_node_types={"LoadAudio", "Preview"},
        catalog=registry.catalog,
    )
    assert reason == ""
    assert workflow is not None
    assert unknown == []
    load = next(n for n in workflow["nodes"] if n["id"] == "n1")
    assert load["widgets"]["path"] == DEFAULT_PLAN_LOAD_AUDIO_PATH
    assert any(row.get("reason") == "default_demo_sample" for row in remaps)


def test_hydrate_composed_workflow_rejects_empty() -> None:
    from groovy.registry.agent.llm_planner import hydrate_composed_workflow

    workflow, unknown, remaps, reason = hydrate_composed_workflow(
        {"nodes": [], "links": []},
        index=0,
        known_node_types={"LoadAudio"},
    )
    assert workflow is None
    assert unknown == []
    assert remaps == []
    assert "no nodes" in reason
