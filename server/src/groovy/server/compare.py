from __future__ import annotations

from typing import Any

from groovy.executor.ab_compare import (
    analyze_signal_pair,
    build_signal_facts,
    build_transcript_facts,
    collect_difference_bullets,
    compare_metrics,
    format_compare_answer,
    measure_clip,
    synthesize_verdict,
)
from groovy.executor.cache import CacheStore
from groovy.nodes.ai.inference import require_model, transcribe_audio
from groovy.registry import ModelRegistry


def _model_name(registry: ModelRegistry, model_id: str) -> str:
    manifest = registry.catalog.get(model_id)
    return manifest.name if manifest else model_id


def _uses_transcription(model_id: str, task_types: list[str]) -> bool:
    if model_id == "groovy-signal-diff":
        return False
    if model_id == "whisper-ab-compare":
        return True
    if "stt" in task_types and model_id != "groovy-signal-diff":
        return True
    return model_id.startswith("whisper-")


def _transcription_model_id(model_id: str) -> str:
    if model_id == "whisper-ab-compare":
        return model_id
    return model_id


def _ensure_compare_model(registry: ModelRegistry, model_id: str) -> None:
    manifest = registry.catalog.get(model_id)
    if manifest and manifest.install.dev_stub:
        registry.installer.install(model_id)
        return
    require_model(registry.project_dir, model_id)


def analyze_ab_pair(
    cache: CacheStore,
    registry: ModelRegistry,
    *,
    cache_id_a: str,
    cache_id_b: str,
    label_a: str,
    label_b: str,
    model_id: str,
    question: str | None = None,
) -> dict[str, Any]:
    manifest = registry.catalog.get(model_id)
    task_types = list(manifest.task_types) if manifest else []
    model_name = _model_name(registry, model_id)

    metrics_a = measure_clip(cache, cache_id_a, label=label_a)
    metrics_b = measure_clip(cache, cache_id_b, label=label_b)
    _, pcm_a = cache.load_audio(cache_id_a)
    _, pcm_b = cache.load_audio(cache_id_b)
    comparison = compare_metrics(metrics_a, metrics_b, pcm_a=pcm_a, pcm_b=pcm_b)
    verdict, verdict_summary = synthesize_verdict(comparison)
    difference_bullets = collect_difference_bullets(comparison)
    signal_facts = build_signal_facts(
        metrics_a,
        metrics_b,
        comparison,
        difference_bullets=difference_bullets,
        verdict=verdict,
        verdict_summary=verdict_summary,
    )

    if _uses_transcription(model_id, task_types):
        transcription_model = _transcription_model_id(model_id)
        _ensure_compare_model(registry, transcription_model)
        text_a = transcribe_audio(
            pcm_a,
            sample_rate=metrics_a.sample_rate,
            model_id=transcription_model,
        )
        text_b = transcribe_audio(
            pcm_b,
            sample_rate=metrics_b.sample_rate,
            model_id=transcription_model,
        )
        transcript_facts = build_transcript_facts(text_a, text_b)
        if text_a.strip() != text_b.strip() and verdict != "no_difference":
            difference_bullets = [*difference_bullets, "Spoken transcript differs between A and B."]
        facts = signal_facts + transcript_facts
        narrative = format_compare_answer(
            question=question,
            label_a=label_a,
            label_b=label_b,
            model_name=model_name,
            facts=facts,
            verdict_summary=verdict_summary,
            differences=difference_bullets,
        )
        return {
            "mode": "transcript",
            "model_id": model_id,
            "transcription_model": transcription_model,
            "verdict": verdict,
            "verdict_summary": verdict_summary,
            "difference_count": len(difference_bullets),
            "differences": difference_bullets,
            "narrative": narrative,
            "facts": facts,
            "transcript_a": text_a,
            "transcript_b": text_b,
            "clip_a": metrics_a.to_dict(),
            "clip_b": metrics_b.to_dict(),
            "comparison": comparison,
        }

    result = analyze_signal_pair(
        cache,
        cache_id_a=cache_id_a,
        cache_id_b=cache_id_b,
        label_a=label_a,
        label_b=label_b,
        question=question,
        model_name=model_name,
    )
    result["model_id"] = model_id
    return result
