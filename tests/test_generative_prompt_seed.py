from __future__ import annotations

from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.node import get_node_class

register_core()
register_ai()


def test_generate_audio_exposes_prompt_and_seed_widgets() -> None:
    schema = get_node_class("GenerateAudio").describe()
    widget_names = {w["name"] for w in schema["widgets"]}
    assert "model" in widget_names
    assert "prompt" in widget_names
    assert "seed" in widget_names
    prompt = next(w for w in schema["widgets"] if w["name"] == "prompt")
    assert prompt["type"] == "STRING"
    seed = next(w for w in schema["widgets"] if w["name"] == "seed")
    assert seed["type"] == "INT"
    assert seed.get("default") == -1
    input_names = {i["name"] for i in schema["inputs"]}
    assert "text" in input_names
    assert "prompt" not in input_names


def test_generative_nodes_expose_seed() -> None:
    for node_type in ("TTS", "MIDIToAudio", "SingFromMIDI", "GenerateAudio", "Video2Audio"):
        schema = get_node_class(node_type).describe()
        assert any(w["name"] == "seed" for w in schema["widgets"]), node_type


def test_video2audio_exposes_path_prompt_and_seed() -> None:
    schema = get_node_class("Video2Audio").describe()
    widget_names = {w["name"] for w in schema["widgets"]}
    assert {"model", "path", "prompt", "seed", "duration"} <= widget_names
    input_names = {i["name"] for i in schema["inputs"]}
    assert "text" in input_names
    assert "path" not in input_names
