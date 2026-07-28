"""Contracts that back the public 'sample-accurate offline render' claim."""

from __future__ import annotations

from groovy.node import NODE_REGISTRY
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core

register_core()
register_ai()


def test_sample_accurate_flag_exposed_on_describe() -> None:
    schema = NODE_REGISTRY["Normalize"].describe()
    assert schema["sample_accurate"] is True
    assert schema["deterministic"] is True
    assert schema["duration_locked"] is True

    ai = NODE_REGISTRY["GenerateAudio"].describe()
    assert ai["sample_accurate"] is True  # offline frame bus
    assert ai["deterministic"] is False
    assert ai["duration_locked"] is False


def test_generative_nodes_mark_duration_unlocked() -> None:
    for name in ("TTS", "GenerateAudio", "MIDIToAudio", "SingFromMIDI"):
        cls = NODE_REGISTRY[name]
        assert cls.DURATION_LOCKED is False
        assert cls.describe()["duration_locked"] is False


def test_transform_ai_keeps_duration_locked() -> None:
    assert NODE_REGISTRY["Denoise"].DURATION_LOCKED is True
    assert NODE_REGISTRY["TimbreTransfer"].DURATION_LOCKED is True


def test_note_is_explicitly_not_sample_accurate() -> None:
    note = NODE_REGISTRY["Note"]
    assert note.SAMPLE_ACCURATE is False


def test_executor_does_not_gate_on_sample_accurate_flag() -> None:
    """Document current gap: SAMPLE_ACCURATE is metadata, not an engine check."""
    import inspect

    from groovy.executor import engine as engine_mod

    source = inspect.getsource(engine_mod)
    assert "SAMPLE_ACCURATE" not in source
    assert "DURATION_LOCKED" not in source