from __future__ import annotations

from pathlib import Path

from groovy.registry.agent.workflow_suggester import suggest_workflows
import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


def test_suggest_podcast_denoise() -> None:
    result = suggest_workflows("clean up my podcast with denoise", TEMPLATES)
    assert result["results"]
    assert result["results"][0]["template_id"] == "podcast-denoise"


def test_suggest_midi_automation() -> None:
    from template_fixtures import find_template_path

    if find_template_path("midi-automation-demo") is None:
        pytest.skip("midi-automation-demo is a local/dev template")
    result = suggest_workflows("apply midi cc automation curve to dialogue", TEMPLATES)
    ids = [item["template_id"] for item in result["results"]]
    assert "midi-automation-demo" in ids


def test_suggest_self_playing_neural_rack() -> None:
    from template_fixtures import find_template_path

    if find_template_path("self-playing-neural-rack") is None:
        pytest.skip("self-playing-neural-rack is a local/dev template")
    result = suggest_workflows("self-playing neural rack with ace as oscillator", TEMPLATES)
    assert result["results"]
    assert result["results"][0]["template_id"] == "self-playing-neural-rack"


def test_suggest_neural_modular_rack() -> None:
    from template_fixtures import find_template_path

    if find_template_path("neural-modular-rack") is None:
        pytest.skip("neural-modular-rack is a local/dev template")
    result = suggest_workflows("neural modular mix rack with probability saw", TEMPLATES)
    assert result["results"]
    assert result["results"][0]["template_id"] == "neural-modular-rack"
