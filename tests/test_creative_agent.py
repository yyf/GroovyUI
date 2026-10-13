"""Creative Agent — sanitize + plan gates (no Anthropic call)."""

from __future__ import annotations

import json

from groovy.registry.agent.creative_agent import (
    plan_creative_agent,
    sanitize_creative_steps,
)


def test_plan_needs_api_key() -> None:
    result = plan_creative_agent(prompt="add a denoise hop", api_key=None)
    assert result["mode"] == "needs_api_key"
    assert result["steps"] == []
    assert result["human_in_the_loop"] is True
    assert result["experimental"] is True


def test_plan_maps_anthropic_401_to_auth_error(monkeypatch) -> None:
    from groovy.registry.agent import creative_agent

    def boom(*, api_key: str, system: str, user: str, model: str) -> str:
        raise RuntimeError(
            'Anthropic API HTTP 401: {"type":"error","error":{"type":"authentication_error",'
            '"message":"invalid x-api-key"}}'
        )

    monkeypatch.setattr(creative_agent, "_call_claude", boom)
    result = plan_creative_agent(prompt="denoise", api_key="sk-ant-test-not-a-real-key")
    assert result["mode"] == "auth_error"
    assert result["steps"] == []
    assert "401" in (result.get("notes") or "")


def test_plan_maps_invalid_json_to_friendly_error(monkeypatch) -> None:
    from groovy.registry.agent import creative_agent

    def bad_json(*, api_key: str, system: str, user: str, model: str) -> str:
        return '{"goal":"x","notes":"n","steps":[{"id":"s1","title":"t","rationale":"bad "quote","action":{}}]}'

    monkeypatch.setattr(creative_agent, "_call_claude", bad_json)
    result = plan_creative_agent(prompt="denoise", api_key="sk-ant-test-not-a-real-key")
    assert result["mode"] == "error"
    assert result["steps"] == []
    assert "invalid JSON" in (result.get("notes") or "")


def test_extract_json_object_nested_fence_and_trailing_comma() -> None:
    from groovy.registry.agent.llm_planner import _extract_json_object

    fenced = (
        "Sure:\n```json\n"
        '{"goal":"g","notes":"n","steps":[{"id":"s1","title":"t",'
        '"rationale":"why","action":{"type":"propose_note","message":"hi"}}]}\n'
        "```\n"
    )
    assert _extract_json_object(fenced)["goal"] == "g"
    trailing = (
        '{"goal":"g","notes":"n","steps":[{"id":"s1","title":"t",'
        '"rationale":"r","action":{"type":"propose_note","message":"m"}},],}'
    )
    assert _extract_json_object(trailing)["goal"] == "g"


def test_sanitize_steps_allowlist_and_lock_unknown() -> None:
    steps, skipped = sanitize_creative_steps(
        [
            {
                "id": "s1",
                "title": "Add Denoise",
                "rationale": "clean speech",
                "action": {
                    "type": "add_node",
                    "node": {"id": "n2", "type": "Denoise", "widgets": {"model": "deepfilternet"}},
                },
            },
            {
                "id": "s2",
                "title": "Wire it",
                "action": {
                    "type": "connect",
                    "from": ["n1", 0],
                    "to": ["n2", 0],
                    "link_type": "AUDIO",
                },
            },
            {
                "id": "s3",
                "title": "Bad",
                "action": {"type": "launch_missiles", "target": "moon"},
            },
            {
                "id": "s4",
                "title": "Fantasy node",
                "action": {
                    "type": "add_node",
                    "node": {"id": "nx", "type": "QuantumFoley9000", "widgets": {}},
                },
            },
            {
                "id": "s5",
                "title": "Note",
                "action": {"type": "propose_note", "message": "Try A/B next"},
            },
        ],
        known_node_types={"Denoise", "LoadAudio", "Preview"},
        catalog=None,
    )
    assert any("unsupported" in s for s in skipped)
    types = [s["action"]["type"] for s in steps]
    assert "add_node" in types
    assert "connect" in types
    assert "propose_note" in types
    # Unknown fantasy types degrade to an approvable note — not a locked dead-end.
    fantasy = next(s for s in steps if s.get("remapped_from") == "QuantumFoley9000")
    assert fantasy["action"]["type"] == "propose_note"
    assert fantasy["apply_locked"] is False
    # Public aliases remap onto local types.
    aliased, _ = sanitize_creative_steps(
        [
            {
                "id": "a1",
                "title": "DeepFilter",
                "action": {
                    "type": "add_node",
                    "node": {"id": "nd", "type": "DeepFilterNet", "widgets": {}},
                },
            }
        ],
        known_node_types={"Denoise", "LoadAudio", "Preview"},
    )
    assert aliased[0]["action"]["node"]["type"] == "Denoise"
    assert aliased[0]["remapped_from"] == "DeepFilterNet"
    assert aliased[0]["apply_locked"] is False
    denoise = next(s for s in steps if s["action"]["type"] == "add_node" and s["action"]["node"]["type"] == "Denoise")
    assert denoise["apply_locked"] is False


def test_plan_parses_claude_json(monkeypatch) -> None:
    from groovy.registry.agent import creative_agent

    def fake_call(*, api_key: str, system: str, user: str, model: str) -> str:
        assert "no_model_catalog" in user
        assert "catalog" not in json.loads(user)
        return json.dumps(
            {
                "goal": "denoise path",
                "notes": "keep it minimal",
                "steps": [
                    {
                        "id": "step-1",
                        "title": "Explain",
                        "rationale": "state check",
                        "action": {"type": "propose_note", "message": "Start from LoadAudio"},
                    },
                    {
                        "id": "step-2",
                        "title": "Add denoise",
                        "rationale": "clean",
                        "action": {
                            "type": "add_node",
                            "node": {"id": "n2", "type": "Denoise", "widgets": {}},
                        },
                    },
                ],
            }
        )

    monkeypatch.setattr(creative_agent, "_call_claude", fake_call)
    result = plan_creative_agent(
        prompt="clean this podcast",
        api_key="sk-ant-test-not-a-real-key",
        canvas={"nodes": [{"id": "n1", "type": "LoadAudio"}], "links": []},
        known_node_types={"LoadAudio", "Denoise", "Preview"},
    )
    assert result["mode"] == "plan"
    assert len(result["steps"]) == 2
    assert result["steps"][0]["action"]["type"] == "propose_note"
    assert result["human_in_the_loop"] is True
