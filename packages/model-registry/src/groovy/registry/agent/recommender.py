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
    (re.compile(r"\b(video.?to.?audio|foley|diff.?foley)\b", re.I), "video-to-audio", "video-to-audio Foley"),
    (
        re.compile(r"\b(text.?to.?video|generate.?video|t2v|video.?generat|ltx.?video|ltx.?2)\b", re.I),
        "text-to-video",
        "text-to-video generation",
    ),
    (re.compile(r"\b(animate|character.?anim|wan.?animate)\b", re.I), "character-animation", "character animation"),
    (re.compile(r"\b(sing|vocal|diffsinger|singing)\b", re.I), "singing-synthesis", "singing from MIDI"),
    (re.compile(r"\b(deepfake|spoof|authentic|synthetic.?speech)\b", re.I), "deepfake-detection", "deepfake detection"),
    (re.compile(r"\b(watermark|audioseal)\b", re.I), "watermark-embed", "audio watermarking"),
    (re.compile(r"\b(timbre|rave|resynth)\b", re.I), "timbre-transfer", "timbre transfer"),
]

# Bare "video" / "videos" → entire public video family (filter further with Hardware presets).
BARE_VIDEO_QUERY = re.compile(r"^videos?$", re.I)
VIDEO_FAMILY_TASKS = (
    "text-to-video",
    "video-generation",
    "video-to-audio",
    "character-animation",
)

COMMERCIAL_HINTS = re.compile(r"\b(commercial|client|broadcast|monetiz)\b", re.I)
LOW_VRAM_HINTS = re.compile(r"\b(low.?vram|cpu|laptop|lightweight|mac|apple.?silicon|mlx|mps)\b", re.I)


def recommend_models(
    catalog: ModelCatalog,
    store: InstallStore,
    *,
    prompt: str,
    commercial_ok: bool | None = None,
    max_results: int = 40,
    task_type: str | None = None,
    node_type: str | None = None,
    max_vram_gb: float | None = None,
) -> dict[str, Any]:
    prompt = prompt.strip()
    if not prompt:
        return {"prompt": prompt, "results": [], "mode": "empty"}

    inferred_task: str | None = task_type or None
    task_phrase = ""
    video_family = False
    if not inferred_task and BARE_VIDEO_QUERY.match(prompt):
        # Return all published video-family models; UI Hardware preset narrows by machine.
        video_family = True
        task_phrase = "public video models"
    elif not inferred_task:
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

    keyword_results = _collect_candidates(
        catalog,
        prompt=prompt,
        inferred_task=inferred_task,
        video_family=video_family,
        commercial_ok=commercial_ok,
        node_type=node_type,
    )

    scored: list[tuple[int, ModelManifest, str]] = []
    for model in keyword_results:
        if max_vram_gb is not None and model.vram_gb_estimate > max_vram_gb:
            continue
        score, rationale = _score_model(
            model,
            prompt,
            inferred_task,
            task_phrase,
            commercial_ok,
            store,
            node_type,
            video_family=video_family,
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
                model,
                prompt,
                inferred_task,
                task_phrase,
                commercial_ok,
                store,
                node_type,
                video_family=video_family,
            )
            if score > 0:
                scored.append((score, model, rationale))

    scored.sort(key=lambda item: (-item[0], item[1].name.lower()))
    limit = max(1, min(int(max_results), 100))
    results = [
        {
            "model": _card(item[1], store.get(item[1].id)),
            "rationale": item[2],
            "score": item[0],
        }
        for item in scored[:limit]
    ]
    return {
        "prompt": prompt,
        "inferred_task": inferred_task,
        "video_family": video_family,
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


def _collect_candidates(
    catalog: ModelCatalog,
    *,
    prompt: str,
    inferred_task: str | None,
    video_family: bool,
    commercial_ok: bool | None,
    node_type: str | None,
) -> list[ModelManifest]:
    """Union keyword hits with full task catalogs so public peers are not truncated away."""
    by_id: dict[str, ModelManifest] = {}

    def _add(models: list[ModelManifest]) -> None:
        for model in models:
            by_id[model.id] = model

    if video_family:
        for task in VIDEO_FAMILY_TASKS:
            _add(
                catalog.search(
                    "",
                    task_type=task,
                    commercial_ok=commercial_ok,
                    node_type=node_type,
                )
            )
        _add(
            catalog.search(
                prompt,
                commercial_ok=commercial_ok,
                node_type=node_type,
            )
        )
        return list(by_id.values())

    _add(
        catalog.search(
            prompt,
            task_type=inferred_task,
            commercial_ok=commercial_ok,
            node_type=node_type,
        )
    )
    if inferred_task:
        # Always include every published model for the inferred task (public catalog completeness).
        _add(
            catalog.search(
                "",
                task_type=inferred_task,
                commercial_ok=commercial_ok,
                node_type=node_type,
            )
        )
    return list(by_id.values())


def _score_model(
    model: ModelManifest,
    prompt: str,
    inferred_task: str | None,
    task_phrase: str,
    commercial_ok: bool | None,
    store: InstallStore,
    node_type: str | None,
    *,
    video_family: bool = False,
) -> tuple[int, str]:
    score = catalog_score(model, prompt.lower())
    state = store.get(model.id)
    if inferred_task and inferred_task in model.task_types:
        score += 12
    if video_family and set(model.task_types) & set(VIDEO_FAMILY_TASKS):
        score += 10
    if node_type and node_type in model.compatible_nodes:
        score += 8
    if commercial_ok and model.license.commercial_ok:
        score += 6
    if LOW_VRAM_HINTS.search(prompt) and model.vram_gb_estimate <= 4:
        score += 5
    # Mild footprint hint only — Hardware preset is the real Mac/CUDA/CPU filter.
    if video_family or inferred_task in {"text-to-video", "video-generation", "character-animation"}:
        if model.vram_gb_estimate <= 2:
            score += 2
        if model.download_size_mb_estimate <= 50:
            score += 2
    if state.status == "ready":
        score += 3
    if state.status == "failed":
        score -= 2

    reasons: list[str] = []
    if inferred_task and inferred_task in model.task_types:
        reasons.append(f"Best match for {task_phrase or inferred_task}")
    elif video_family and set(model.task_types) & set(VIDEO_FAMILY_TASKS):
        reasons.append("Public video catalog match")
    elif model.task_types:
        reasons.append(f"Fits {model.task_types[0]}")
    if node_type and node_type in model.compatible_nodes:
        reasons.append(f"compatible with {node_type}")
    if model.license.commercial_ok:
        reasons.append(f"{model.license.spdx} commercial OK")
    else:
        reasons.append(f"{model.license.spdx} — check commercial policy")
    if model.vram_gb_estimate <= 2:
        reasons.append("Mac-local · minimal RAM")
    elif model.vram_gb_estimate <= 4:
        reasons.append("low VRAM")
    else:
        reasons.append(f"~{model.vram_gb_estimate:g} GB VRAM")
    if model.download_size_mb_estimate <= 50:
        reasons.append("~0 GB disk (stub)")
    elif model.download_size_mb_estimate >= 1000:
        reasons.append(f"~{model.download_size_mb_estimate / 1000:g} GB disk")
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
    from groovy.registry.compute import resolve_compute

    return {
        "id": manifest.id,
        "name": manifest.name,
        "description": manifest.description,
        "task_types": manifest.task_types,
        "tags": manifest.tags,
        "author": manifest.author,
        "license": manifest.license.model_dump(),
        "vram_gb_estimate": manifest.vram_gb_estimate,
        "download_size_mb_estimate": manifest.download_size_mb_estimate,
        "compatible_nodes": manifest.compatible_nodes,
        "install_status": state.status,
        "install_progress": state.progress,
        "install_error": state.error,
        "dev_stub": manifest.install.dev_stub,
        "compute": manifest.compute.model_dump(),
        "compute_resolved": resolve_compute(manifest),
    }
