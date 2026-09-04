from __future__ import annotations

import re
from typing import Any

from groovy.registry.catalog import ModelCatalog
from groovy.registry.models import ModelManifest
from groovy.registry.store import InstallStore

TASK_HINTS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\b(denoise|noise|clean|podcast)\b", re.I), "denoise", "podcast or dialogue cleanup"),
    (re.compile(r"\b(stem|separate|vocals|instrumental)\b", re.I), "stem-separation", "stem separation"),
    (re.compile(r"\b(transcrib|speech.to.text|stt|subtitle)\b", re.I), "speech-to-text", "speech transcription"),
    (re.compile(r"\b(tts|text.to.speech|voiceover|narrat)\b", re.I), "text-to-speech", "text-to-speech synthesis"),
    (re.compile(r"\b(voice.?clone|convert|rvc|speaker)\b", re.I), "voice-conversion", "voice conversion"),
    (re.compile(r"\b(audio.?to.?midi|midi.?transcrib|basic.?pitch)\b", re.I), "audio-to-midi", "audio to MIDI transcription"),
    (re.compile(r"\b(midi.?to.?audio|musicgen|regenerat)\b", re.I), "midi-to-audio", "MIDI-conditioned generation"),
    (re.compile(r"\b(text.?to.?music|generate.?music|soundscape)\b", re.I), "music-generation", "text-to-music generation"),
    (re.compile(r"\b(sing|vocal|diffsinger|singing)\b", re.I), "singing-synthesis", "singing from MIDI"),
    (re.compile(r"\b(deepfake|spoof|authentic|synthetic.?speech)\b", re.I), "deepfake-detection", "deepfake detection"),
    (re.compile(r"\b(watermark|audioseal)\b", re.I), "watermark-embed", "audio watermarking"),
    (re.compile(r"\b(timbre|rave|resynth)\b", re.I), "timbre-transfer", "timbre transfer"),
]

COMMERCIAL_HINTS = re.compile(r"\b(commercial|client|broadcast|monetiz)\b", re.I)
LOW_VRAM_HINTS = re.compile(r"\b(low.?vram|cpu|laptop|lightweight)\b", re.I)


def recommend_models(
    catalog: ModelCatalog,
    store: InstallStore,
    *,
    prompt: str,
    commercial_ok: bool | None = None,
    max_results: int = 5,
    task_type: str | None = None,
    node_type: str | None = None,
    max_vram_gb: float | None = None,
) -> dict[str, Any]:
    prompt = prompt.strip()
    if not prompt:
        return {"prompt": prompt, "results": [], "mode": "empty"}

    inferred_task: str | None = task_type or None
    task_phrase = ""
    if not inferred_task:
        for pattern, task, phrase in TASK_HINTS:
            if pattern.search(prompt):
                inferred_task = task
                task_phrase = phrase
                break
    elif inferred_task:
        for _, task, phrase in TASK_HINTS:
            if task == inferred_task:
                task_phrase = phrase
                break

    if COMMERCIAL_HINTS.search(prompt):
        commercial_ok = True
    if max_vram_gb is None and LOW_VRAM_HINTS.search(prompt):
        max_vram_gb = 4.0

    keyword_results = catalog.search(
        prompt,
        task_type=inferred_task,
        commercial_ok=commercial_ok,
        node_type=node_type,
    )
    if not keyword_results and inferred_task:
        keyword_results = catalog.search(
            "",
            task_type=inferred_task,
            commercial_ok=commercial_ok,
            node_type=node_type,
        )

    scored: list[tuple[int, ModelManifest, str]] = []
    for model in keyword_results:
        if max_vram_gb is not None and model.vram_gb_estimate > max_vram_gb:
            continue
        score, rationale = _score_model(
            model, prompt, inferred_task, task_phrase, commercial_ok, store, node_type
        )
        scored.append((score, model, rationale))

    if not scored:
        for model in catalog.all():
            if model.status != "published":
                continue
            if commercial_ok is not None and model.license.commercial_ok != commercial_ok:
                continue
            if node_type and node_type not in model.compatible_nodes:
                continue
            if max_vram_gb is not None and model.vram_gb_estimate > max_vram_gb:
                continue
            score, rationale = _score_model(
                model, prompt, inferred_task, task_phrase, commercial_ok, store, node_type
            )
            if score > 0:
                scored.append((score, model, rationale))

    scored.sort(key=lambda item: (-item[0], item[1].name.lower()))
    results = [
        {
            "model": _card(item[1], store.get(item[1].id)),
            "rationale": item[2],
            "score": item[0],
        }
        for item in scored[:max_results]
    ]
    return {
        "prompt": prompt,
        "inferred_task": inferred_task,
        "commercial_ok": commercial_ok,
        "node_type": node_type,
        "max_vram_gb": max_vram_gb,
        "mode": "recommender",
        "results": results,
        "workflow_handoff_hint": (
            "Switch to Suggest workflow with the same prompt to preview a template (Apply is explicit)."
            if results
            else None
        ),
    }


def _score_model(
    model: ModelManifest,
    prompt: str,
    inferred_task: str | None,
    task_phrase: str,
    commercial_ok: bool | None,
    store: InstallStore,
    node_type: str | None,
) -> tuple[int, str]:
    score = catalog_score(model, prompt.lower())
    state = store.get(model.id)
    if inferred_task and inferred_task in model.task_types:
        score += 12
    if node_type and node_type in model.compatible_nodes:
        score += 8
    if commercial_ok and model.license.commercial_ok:
        score += 6
    if LOW_VRAM_HINTS.search(prompt) and model.vram_gb_estimate <= 4:
        score += 5
    if state.status == "ready":
        score += 3
    if state.status == "failed":
        score -= 2

    reasons: list[str] = []
    if inferred_task and inferred_task in model.task_types:
        reasons.append(f"Best match for {task_phrase or inferred_task}")
    elif model.task_types:
        reasons.append(f"Fits {model.task_types[0]}")
    if node_type and node_type in model.compatible_nodes:
        reasons.append(f"compatible with {node_type}")
    if model.license.commercial_ok:
        reasons.append(f"{model.license.spdx} commercial OK")
    else:
        reasons.append(f"{model.license.spdx} — check commercial policy")
    if model.vram_gb_estimate <= 4:
        reasons.append("low VRAM")
    else:
        reasons.append(f"~{model.vram_gb_estimate:g} GB VRAM")
    if state.status == "ready":
        reasons.append("already installed")
    elif state.status == "failed":
        reasons.append("prior install failed — open recovery on the card")
    rationale = " · ".join(reasons) if reasons else f"Catalog match for {model.id}"
    return score, rationale


def catalog_score(model: ModelManifest, query: str) -> int:
    haystack = " ".join([model.id, model.name, model.description, " ".join(model.tags)]).lower()
    if query in haystack:
        return 10
    return sum(2 for token in query.split() if len(token) > 2 and token in haystack)


def _card(manifest: ModelManifest, state) -> dict[str, Any]:
    return {
        "id": manifest.id,
        "name": manifest.name,
        "description": manifest.description,
        "task_types": manifest.task_types,
        "tags": manifest.tags,
        "author": manifest.author,
        "license": manifest.license.model_dump(),
        "vram_gb_estimate": manifest.vram_gb_estimate,
        "compatible_nodes": manifest.compatible_nodes,
        "install_status": state.status,
        "install_progress": state.progress,
        "install_error": state.error,
        "dev_stub": manifest.install.dev_stub,
    }
