"""Template integrity registry for Phase 2.6 L1–L3 regression over bundled workflows."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import soundfile as sf
from groovy.registry import ModelRegistry
from groovy.registry.studio_settings import inference_stub_active
from groovy.schema.models import Workflow

FixtureKind = Literal["tone", "surround_51", "none"]
TerminalOutputType = Literal["AUDIO", "MIDI", "TEXT", "AUTHENTICITY", "NONE"]

TERMINAL_OUTPUT_BY_NODE: dict[str, TerminalOutputType] = {
    "Preview": "AUDIO",
    "WhisperSTT": "TEXT",
    "DiarizeTranscribe": "TEXT",
    "AudioToMIDI": "MIDI",
    "AuthenticitySummary": "AUTHENTICITY",
    "MIDIOutDevice": "NONE",
}

MIDI_STUB_BYTES = (
    b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60MTrk\x00\x00\x00\x04\x00\xff\x2f\x00"
)


@dataclass(frozen=True)
class TemplateIntegritySpec:
    template_id: str
    target_nodes: tuple[str, ...]
    terminal_node: str
    terminal_output_type: TerminalOutputType = "AUDIO"
    sample_path: str | None = "assets/samples/noisy_speech_1214.wav"
    midi_path: str | None = None
    models: tuple[str, ...] = ()
    fixture: FixtureKind = "tone"
    expect_stems_node: str | None = None
    expect_stem_keys: frozenset[str] | None = None
    expect_terminal_layout: str | None = None
    expect_hop_layout: dict[str, str] = field(default_factory=dict)
    required_outputs: tuple[tuple[str, str], ...] = ()
    spot_check: str | None = None


TEMPLATE_OVERRIDES: dict[str, dict[str, Any]] = {
    "hello-groovy": {
        "fixture": "none",
        "sample_path": None,
        "models": ("kokoro-82m",),
        "required_outputs": (("n8", "AUDIO"),),
    },
    "podcast-denoise": {"sample_path": "assets/samples/noisy_speech_1214.wav"},
    "ab-compare-demo": {"sample_path": "assets/samples/noisy_speech_1214.wav", "spot_check": "ab_compare"},
    "stem-separation": {
        "sample_path": "assets/samples/Knockout_41k_mono.wav",
        "expect_stems_node": "n2",
        "expect_stem_keys": frozenset({"vocals", "drums", "bass", "other"}),
    },
    "stems-to-spatial": {
        "models": ("demucs-v4", "demucs-v4-objects", "object-placement-heuristic"),
    },
    "surround-downmix": {
        "fixture": "surround_51",
        "sample_path": "assets/samples/surround_51.wav",
        "expect_terminal_layout": "stereo",
    },
    "surround-mix": {"expect_hop_layout": {"n6": "5.1", "n8": "stereo"}},
    "midi-automation-demo": {"midi_path": "assets/samples/automation_cc7.mid"},
    "sing-from-midi": {
        "fixture": "none",
        "sample_path": None,
        "midi_path": "assets/samples/automation_cc7.mid",
    },
    "text-to-music": {"fixture": "none", "sample_path": None},
    "stable-audio": {
        "fixture": "none",
        "sample_path": None,
        "models": ("stable-audio-open-1.0",),
        "required_outputs": (("n3", "AUDIO"),),
    },
    "ace-step-1.5": {
        "fixture": "none",
        "sample_path": None,
        "models": ("ace-step-1.5",),
        "required_outputs": (("n3", "AUDIO"),),
    },
    "voice-cloning": {
        "sample_path": "assets/samples/noisy_speech_1214.wav",
        "models": ("f5-tts-base",),
        "required_outputs": (("n4", "AUDIO"),),
    },
    "prompt-modular-synth": {
        "fixture": "none",
        "sample_path": None,
        "models": ("kokoro-82m",),
        "required_outputs": (("n4", "AUDIO"),),
    },
    "simple-fm-synth": {"fixture": "none", "sample_path": None},
    "keyboard-to-music": {"fixture": "none", "sample_path": None},
    "ai-midi-to-hardware": {
        "fixture": "none",
        "sample_path": None,
        "required_outputs": (("n4", "AUDIO"),),
    },
    "transcribe-dialogue": {
        # n3 = text Preview (Whisper); n4 = audio Preview (source waveform).
        "terminal_output_type": "TEXT",
        "required_outputs": (("n2", "TEXT"), ("n3", "TEXT"), ("n4", "AUDIO")),
    },
    "cleanup-and-transcribe": {
        "terminal_output_type": "TEXT",
        "required_outputs": (("n4", "TEXT"), ("n5", "TEXT"), ("n6", "AUDIO")),
    },
    "transcribe-and-diarize": {
        "terminal_output_type": "TEXT",
        "required_outputs": (("n2", "TEXT"), ("n3", "TEXT"), ("n4", "AUDIO")),
    },
    "denoise-diarize-transcribe": {
        "sample_path": "assets/samples/diarization.wav",
        "terminal_output_type": "TEXT",
        "required_outputs": (("n4", "TEXT"), ("n5", "TEXT"), ("n6", "AUDIO")),
    },
    "song-cover-remix": {
        # CI writes a tone fixture as WAV; studio template LoadAudio still uses Signe mp4.
        "sample_path": "assets/samples/Knockout_41k_mono.wav",
        "expect_stems_node": "n2",
        "expect_stem_keys": frozenset({"vocals", "drums", "bass", "other"}),
        "required_outputs": (("n9", "AUDIO"),),
    },
    "karaoke-stems": {
        "sample_path": "assets/samples/noisy_speech_1214.wav",
        "expect_stems_node": "n2",
        "expect_stem_keys": frozenset({"vocals", "drums", "bass", "other"}),
        "required_outputs": (("n5", "AUDIO"), ("n6", "AUDIO")),
    },
    "transcribe-to-midi": {"terminal_output_type": "MIDI"},
    "transcribe-to-synth": {
        "terminal_output_type": "MIDI",
        "required_outputs": (("n2", "MIDI"),),
    },
    "authenticity-check": {
        "models": ("rawnet2-asvspoof",),
        "required_outputs": (("n4", "AUTHENTICITY"), ("n5", "AUDIO"), ("n6", "AUDIO")),
    },
    "compare-whisper-sizes": {
        "sample_path": "assets/samples/noisy_speech_1214.wav",
        "terminal_output_type": "TEXT",
        "required_outputs": (("n3", "TEXT"), ("n4", "TEXT"), ("n7", "AUDIO")),
        "spot_check": "ab_compare",
    },
    "script-to-vo-master": {
        "fixture": "none",
        "sample_path": None,
        "models": ("kokoro-82m", "deepfilternet-v3"),
        "required_outputs": (("n7", "AUDIO"),),
    },
    "karaoke-guide-vocal": {
        "sample_path": "assets/samples/Knockout_41k_mono.wav",
        "expect_stems_node": "n2",
        "expect_stem_keys": frozenset({"vocals", "drums", "bass", "other"}),
        "models": ("demucs-v4", "kokoro-82m"),
        "required_outputs": (("n9", "AUDIO"),),
    },
    "instrumental-tts-dub": {
        "sample_path": "assets/samples/Knockout_41k_mono.wav",
        "expect_stems_node": "n2",
        "expect_stem_keys": frozenset({"vocals", "drums", "bass", "other"}),
        "models": ("demucs-v4", "whisper-large-v3-turbo", "kokoro-82m"),
        "required_outputs": (("n9", "AUDIO"), ("n3", "TEXT")),
    },
    "melody-to-modular-synth": {
        "sample_path": "assets/samples/noisy_speech_1214.wav",
        "models": ("basic-pitch",),
        "required_outputs": (("n10", "AUDIO"), ("n2", "MIDI")),
    },
    "compare-stemmers": {
        "sample_path": "assets/samples/Knockout_41k_mono.wav",
        "expect_stems_node": "n2",
        "expect_stem_keys": frozenset({"vocals", "drums", "bass", "other"}),
        "models": ("demucs-v4", "demucs-v4-ht"),
        "required_outputs": (("n4", "AUDIO"), ("n5", "AUDIO")),
        "spot_check": "ab_compare",
    },
    "stem-lyrics-to-ace": {
        "sample_path": "assets/samples/Knockout_41k_mono.wav",
        "expect_stems_node": "n2",
        "expect_stem_keys": frozenset({"vocals", "drums", "bass", "other"}),
        "models": ("demucs-v4", "whisper-large-v3-turbo", "ace-step-1.5-2b-turbo"),
        "required_outputs": (("n9", "AUDIO"), ("n3", "TEXT")),
    },
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _templates_dir() -> Path:
    return _repo_root() / "templates"


def _terminal_node_ids(workflow: Workflow) -> tuple[str, ...]:
    sources = {link.from_[0] for link in workflow.links}
    return tuple(
        node.id
        for node in workflow.nodes
        if node.id not in sources and node.type != "Note"
    )


def _primary_terminal(workflow: Workflow, terminal_ids: tuple[str, ...]) -> str:
    by_id = {node.id: node for node in workflow.nodes}
    for node_id in terminal_ids:
        if by_id[node_id].type == "Preview":
            return node_id
    for node_id in terminal_ids:
        if by_id[node_id].type != "Note":
            return node_id
    return terminal_ids[0]


def _terminal_output_type(node_type: str, override: TerminalOutputType | None) -> TerminalOutputType:
    if override:
        return override
    return TERMINAL_OUTPUT_BY_NODE.get(node_type, "AUDIO")


def _models_for_workflow(workflow: Workflow) -> tuple[str, ...]:
    models: list[str] = []
    for node in workflow.nodes:
        model = node.widgets.get("model")
        if isinstance(model, str) and model.strip():
            models.append(model.strip())
    return tuple(dict.fromkeys(models))


def _default_sample_path(workflow: Workflow) -> str | None:
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            path = node.widgets.get("path")
            if isinstance(path, str) and path.strip():
                return path.strip()
    return None


def _default_midi_path(workflow: Workflow) -> str | None:
    for node in workflow.nodes:
        if node.type == "LoadMIDI":
            path = node.widgets.get("path")
            if isinstance(path, str) and path.strip():
                return path.strip()
    return None


def _default_required_outputs(
    workflow: Workflow,
    terminal_ids: tuple[str, ...],
    terminal_node: str,
    terminal_output_type: TerminalOutputType,
) -> tuple[tuple[str, str], ...]:
    if terminal_output_type == "NONE":
        for link in workflow.links:
            if link.to[0] == terminal_node and link.type == "MIDI":
                return ((link.from_[0], "MIDI"),)
        return ()
    if terminal_output_type in {"AUDIO", "MIDI", "TEXT", "AUTHENTICITY"}:
        return ((terminal_node, terminal_output_type),)
    return ((terminal_node, "AUDIO"),)


def build_template_spec(template_path: Path) -> TemplateIntegritySpec:
    template_id = template_path.stem.replace(".groovy", "")
    workflow = Workflow.model_validate(json.loads(template_path.read_text()))
    terminal_ids = _terminal_node_ids(workflow)
    if not terminal_ids:
        raise ValueError(f"{template_id}: no terminal nodes")
    terminal_node = _primary_terminal(workflow, terminal_ids)
    terminal_type_node = next(node for node in workflow.nodes if node.id == terminal_node)
    overrides = TEMPLATE_OVERRIDES.get(template_id, {})
    terminal_output_type = _terminal_output_type(
        terminal_type_node.type,
        overrides.get("terminal_output_type"),
    )
    required_outputs = overrides.get("required_outputs") or _default_required_outputs(
        workflow,
        terminal_ids,
        terminal_node,
        terminal_output_type,
    )
    sample_path = overrides.get("sample_path", _default_sample_path(workflow))
    midi_path = overrides.get("midi_path", _default_midi_path(workflow))
    fixture: FixtureKind = overrides.get("fixture", "surround_51" if template_id == "surround-downmix" else "tone")
    if sample_path is None:
        fixture = "none"
    models = overrides.get("models") or _models_for_workflow(workflow)
    return TemplateIntegritySpec(
        template_id=template_id,
        target_nodes=terminal_ids,
        terminal_node=terminal_node,
        terminal_output_type=terminal_output_type,
        sample_path=sample_path,
        midi_path=midi_path,
        models=tuple(models),
        fixture=fixture,
        expect_stems_node=overrides.get("expect_stems_node"),
        expect_stem_keys=overrides.get("expect_stem_keys"),
        expect_terminal_layout=overrides.get("expect_terminal_layout"),
        expect_hop_layout=dict(overrides.get("expect_hop_layout", {})),
        required_outputs=tuple(required_outputs),
        spot_check=overrides.get("spot_check"),
    )


def all_template_specs() -> tuple[TemplateIntegritySpec, ...]:
    paths = sorted(_templates_dir().glob("*.groovy.json"))
    return tuple(build_template_spec(path) for path in paths)


# v1 subset retained for docs / quick CI slice
SIGNAL_INTEGRITY_V1_TEMPLATES: tuple[TemplateIntegritySpec, ...] = tuple(
    spec for spec in all_template_specs() if spec.template_id in {"hello-groovy", "podcast-denoise", "stem-separation"}
)

ALL_TEMPLATE_INTEGRITY_SPECS: tuple[TemplateIntegritySpec, ...] = all_template_specs()


def _write_tone_wav(path: Path, *, sr: int = 48000, duration: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * 440 * t)
    sf.write(path, tone, sr)


def _write_surround_wav(path: Path, *, sr: int = 48000, frames: int = 4800) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fl = np.sin(2 * np.pi * 220 * np.linspace(0, frames / sr, frames, endpoint=False))
    pcm = np.zeros((6, frames))
    pcm[0] = fl
    pcm[2] = 0.5 * fl
    pcm[4] = 0.3 * fl
    sf.write(path, pcm.T, sr)


def prepare_template_project(project_dir: Path, spec: TemplateIntegritySpec) -> Path:
    if spec.fixture == "surround_51" and spec.sample_path:
        _write_surround_wav(project_dir / spec.sample_path)
    elif spec.fixture == "tone" and spec.sample_path:
        _write_tone_wav(project_dir / spec.sample_path)
    if spec.midi_path:
        midi_abs = project_dir / spec.midi_path
        midi_abs.parent.mkdir(parents=True, exist_ok=True)
        midi_abs.write_bytes(MIDI_STUB_BYTES)
    registry = ModelRegistry(project_dir)
    stub_mode = inference_stub_active(project_dir=project_dir)
    for model_id in spec.models:
        if stub_mode:
            # CI stub path: mark installed without downloading multi-GB / gated weights.
            # AI workers still require installed.json; inference uses stubs when env is set.
            model_dir = project_dir / ".groovy" / "models" / model_id
            model_dir.mkdir(parents=True, exist_ok=True)
            registry.store.mark_ready(model_id)
        else:
            registry.installer.install(model_id)
    return project_dir


def load_template_workflow(spec: TemplateIntegritySpec) -> Workflow:
    path = _templates_dir() / f"{spec.template_id}.groovy.json"
    workflow = Workflow.model_validate(json.loads(path.read_text()))
    for node in workflow.nodes:
        if spec.sample_path and node.type == "LoadAudio":
            node.widgets["path"] = spec.sample_path
        if spec.midi_path and node.type == "LoadMIDI":
            node.widgets["path"] = spec.midi_path
    return workflow
