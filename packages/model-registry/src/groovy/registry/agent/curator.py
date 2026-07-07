from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from groovy.registry.models import LicenseInfo, ModelManifest

# Curated ingest hints — deterministic drafts; human approves before publish.
INGEST_HINTS: list[dict[str, Any]] = [
    {
        "source": "huggingface:facebook/musicgen-small",
        "id": "musicgen-small-draft",
        "name": "MusicGen Small",
        "description": "Text- and melody-conditioned music generation (draft ingest).",
        "task_types": ["music-generation", "midi-to-audio"],
        "tags": ["musicgen", "generation", "melody"],
        "author": "Meta",
        "license_spdx": "CC-BY-NC-4.0",
        "commercial_ok": False,
        "vram_gb_estimate": 6,
        "compatible_nodes": ["MIDIToAudio"],
    },
    {
        "source": "huggingface:openai/whisper-base",
        "id": "whisper-base-draft",
        "name": "Whisper Base",
        "description": "Compact speech-to-text model for dialogue transcription (draft ingest).",
        "task_types": ["speech-to-text", "stt"],
        "tags": ["whisper", "stt", "transcribe"],
        "author": "OpenAI",
        "license_spdx": "MIT",
        "commercial_ok": True,
        "vram_gb_estimate": 2,
        "compatible_nodes": ["WhisperSTT"],
    },
    {
        "source": "github:spotify/basic-pitch",
        "id": "basic-pitch-community-draft",
        "name": "Basic Pitch (community draft)",
        "description": "Polyphonic audio-to-MIDI transcription (draft ingest from GitHub hint).",
        "task_types": ["audio-to-midi"],
        "tags": ["midi", "transcription", "basic-pitch"],
        "author": "Spotify",
        "license_spdx": "Apache-2.0",
        "commercial_ok": True,
        "vram_gb_estimate": 2,
        "compatible_nodes": ["AudioToMIDI"],
    },
]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "draft-model"


def draft_from_hint(hint: dict[str, Any]) -> ModelManifest:
    model_id = str(hint.get("id") or _slug(str(hint.get("name", "draft"))))
    return ModelManifest(
        id=model_id,
        status="draft",
        trust="draft",
        name=str(hint["name"]),
        description=str(hint["description"]),
        task_types=list(hint.get("task_types", [])),
        tags=list(hint.get("tags", [])),
        author=str(hint.get("author", "")),
        license=LicenseInfo(
            spdx=str(hint.get("license_spdx", "UNKNOWN")),
            commercial_ok=bool(hint.get("commercial_ok", False)),
            attribution_required=bool(hint.get("attribution_required", False)),
            confidence=float(hint.get("license_confidence", 0.75)),
        ),
        vram_gb_estimate=float(hint.get("vram_gb_estimate", 0)),
        compatible_nodes=list(hint.get("compatible_nodes", [])),
        install={"dev_stub": True},
        similar_models=list(hint.get("similar_models", [])),
    )


def ingest_drafts(
    draft_dir: Path,
    *,
    hints: list[dict[str, Any]] | None = None,
    skip_existing: bool = True,
) -> dict[str, Any]:
    draft_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    skipped: list[str] = []
    for hint in hints or INGEST_HINTS:
        draft = draft_from_hint(hint)
        path = draft_dir / f"{draft.id}.json"
        if skip_existing and path.exists():
            skipped.append(draft.id)
            continue
        payload = draft.model_dump()
        payload["agent_notes"] = (
            f"Draft from {hint.get('source', 'curator')}. Verify license and weights before publish."
        )
        path.write_text(json.dumps(payload, indent=2))
        created.append(draft.id)
    return {"created": created, "skipped": skipped, "draft_dir": str(draft_dir)}


def list_drafts(draft_dir: Path) -> list[dict[str, Any]]:
    if not draft_dir.exists():
        return []
    drafts: list[dict[str, Any]] = []
    for path in sorted(draft_dir.glob("*.json")):
        drafts.append(json.loads(path.read_text()))
    return drafts


def approve_draft(
    draft_dir: Path,
    overlay_path: Path,
    model_id: str,
    *,
    edits: dict[str, Any] | None = None,
) -> ModelManifest:
    draft_path = draft_dir / f"{model_id}.json"
    if not draft_path.exists():
        raise FileNotFoundError(f"Draft not found: {model_id}")
    data = json.loads(draft_path.read_text())
    if edits:
        data.update(edits)
    data["status"] = "published"
    data["trust"] = "verified"
    manifest = ModelManifest.model_validate(data)

    overlay: dict[str, Any] = {"models": []}
    if overlay_path.exists():
        overlay = json.loads(overlay_path.read_text())
    models = {item["id"]: item for item in overlay.get("models", [])}
    models[manifest.id] = manifest.model_dump()
    overlay["models"] = list(models.values())
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_path.write_text(json.dumps(overlay, indent=2))
    draft_path.unlink()
    return manifest
