from __future__ import annotations

from pathlib import Path

from groovy.registry.agent.workflow_suggester import suggest_workflows

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


def test_suggest_podcast_denoise() -> None:
    result = suggest_workflows("clean up my podcast with denoise", TEMPLATES)
    assert result["results"]
    assert result["results"][0]["template_id"] == "podcast-denoise"


def test_suggest_midi_automation() -> None:
    result = suggest_workflows("apply midi cc automation curve to dialogue", TEMPLATES)
    ids = [item["template_id"] for item in result["results"]]
    assert "midi-automation-demo" in ids
