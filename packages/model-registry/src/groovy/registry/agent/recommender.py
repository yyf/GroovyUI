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
    (re.compile(r"\b(deepfake|spoof|authentic)\b", re.I), "deepfake-detection", "authenticity checking"),
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
) -> dict[str, Any]:
    prompt = prompt.strip()
    if not prompt:
        return {"prompt": prompt, "results": [], "mode": "empty"}

    inferred_task: str | None = None
    task_phrase = ""
    for pattern, task, phrase in TASK_HINTS:
        if pattern.search(prompt):
            inferred_task = task
            task_phrase = phrase
            break

    if COMMERCIAL_HINTS.search(prompt):
        commercial_ok = True

    keyword_results = catalog.search(prompt, task_type=inferred_task, commercial_ok=commercial_ok)
    if not keyword_results and inferred_task:
        keyword_results = catalog.search("", task_type=inferred_task, commercial_ok=commercial_ok)

    scored: list[tuple[int, ModelManifest, str]] = []
    for model in keyword_results:
        score, rationale = _score_model(model, prompt, inferred_task, task_phrase, commercial_ok, store)
        scored.append((score, model, rationale))

    if not scored:
        for model in catalog.all():
            if model.status != "published":
                continue
            if commercial_ok is not None and model.license.commercial_ok != commercial_ok:
                continue
            score, rationale = _score_model(model, prompt, inferred_task, task_phrase, commercial_ok, store)
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
        "mode": "recommender",
        "results": results,
    }


def _score_model(
    model: ModelManifest,
    prompt: str,
    inferred_task: str | None,
    task_phrase: str,
    commercial_ok: bool | None,
    store: InstallStore,
) -> tuple[int, str]:
    score = catalog_score(model, prompt.lower())
    state = store.get(model.id)
    if inferred_task and inferred_task in model.task_types:
        score += 12
    if commercial_ok and model.license.commercial_ok:
        score += 6
    if LOW_VRAM_HINTS.search(prompt) and model.vram_gb_estimate <= 4:
        score += 5
    if state.status == "ready":
        score += 3

    if inferred_task and inferred_task in model.task_types:
        rationale = f"Best match for {task_phrase or inferred_task}"
    elif model.license.commercial_ok:
        rationale = f"Commercial-friendly option for {model.task_types[0]}"
    else:
        rationale = f"Strong fit for {model.task_types[0]}"

    if model.vram_gb_estimate <= 4:
        rationale += " — low VRAM"
    if state.status == "ready":
        rationale += " — already installed"
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
        "license": manifest.license.model_dump(),
        "vram_gb_estimate": manifest.vram_gb_estimate,
        "compatible_nodes": manifest.compatible_nodes,
        "install_status": state.status,
        "install_error": state.error,
    }
