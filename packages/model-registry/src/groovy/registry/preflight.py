from __future__ import annotations

from typing import Any

from groovy.registry.machine import (
    build_machine_checks,
    missing_verify_imports_for_models,
    probe_machine,
)
from groovy.schema.models import Workflow

# Rough wall-clock seconds to process one minute of source audio. These are
# deliberately broad, hardware-agnostic planning ranges—not performance claims.
_SECONDS_PER_MINUTE: dict[str, tuple[int, int]] = {
    "Denoise": (5, 30),
    "SeparateStems": (20, 150),
    "SeparateToObjects": (20, 150),
    "AmbisonicUpmix": (15, 120),
    "AmbisonicTrajectoryExtract": (10, 90),
    "BinauralRender": (5, 40),
    "SpatialUpmix": (8, 60),
    "WhisperSTT": (8, 60),
    "DiarizeTranscribe": (20, 180),
    "AudioToMIDI": (5, 45),
    "VoiceConvert": (15, 120),
    "TimbreTransfer": (10, 90),
    "DeepfakeDetect": (5, 45),
    "EmbedWatermark": (5, 45),
    "DetectWatermark": (5, 45),
    "TTS": (5, 60),
    "MIDIToAudio": (30, 240),
    "GenerateAudio": (30, 240),
    "SingFromMIDI": (30, 240),
}
_CORE_NODE_RANGE = (0, 3)


def estimate_workflow_preflight(workflow: Workflow, registry: Any) -> dict[str, Any]:
    """Estimate missing-only transfer, sequential peak VRAM, and render time.

    Registry metadata stays the baseline. Machine probes add disk / VRAM /
    runtime checks without claiming precise timings.
    """

    model_ids: list[str] = []
    for node in workflow.nodes:
        model_id = node.widgets.get("model")
        if isinstance(model_id, str) and model_id and model_id not in model_ids:
            model_ids.append(model_id)

    known_download_mb = 0.0
    unknown_download_models: list[str] = []
    already_installed: list[str] = []
    model_rows: list[dict[str, Any]] = []
    peak_vram_gb = 0.0
    missing_manifests: list[Any] = []

    for model_id in model_ids:
        manifest = registry.catalog.get(model_id)
        if manifest is None:
            unknown_download_models.append(model_id)
            continue
        state = registry.store.get(model_id)
        peak_vram_gb = max(peak_vram_gb, float(manifest.vram_gb_estimate or 0))
        installed = state.status == "ready"
        size_mb = manifest.download_size_mb_estimate
        if installed:
            already_installed.append(model_id)
        elif size_mb is None:
            unknown_download_models.append(model_id)
            missing_manifests.append(manifest)
        else:
            known_download_mb += float(size_mb)
            missing_manifests.append(manifest)
        model_rows.append(
            {
                "model_id": model_id,
                "installed": installed,
                "download_size_mb_estimate": size_mb,
                "vram_gb_estimate": manifest.vram_gb_estimate,
            }
        )

    low_seconds = 0
    high_seconds = 0
    estimated_nodes: list[dict[str, Any]] = []
    for node in workflow.nodes:
        low, high = _SECONDS_PER_MINUTE.get(node.type, _CORE_NODE_RANGE)
        low_seconds += low
        high_seconds += high
        estimated_nodes.append(
            {
                "node_id": node.id,
                "node_type": node.type,
                "seconds_per_audio_minute": {"low": low, "high": high},
            }
        )

    project_dir = getattr(registry, "project_dir", None)
    machine = (
        probe_machine(project_dir)
        if project_dir is not None
        else {
            "disk_free_mb": 0.0,
            "disk_path": "",
            "models_dir": "",
            "models_used_mb": 0.0,
            "ram_available_gb": None,
            "vram_available_gb": None,
            "vram_source": "unknown",
            "torch_cuda_available": False,
            "python_executable": "",
            "uv_available": False,
        }
    )
    checks = build_machine_checks(
        known_download_mb=known_download_mb,
        peak_vram_gb=peak_vram_gb,
        machine=machine,
        missing_verify_imports=missing_verify_imports_for_models(missing_manifests),
    )

    return {
        "download": {
            "known_mb": round(known_download_mb, 1),
            "unknown_models": unknown_download_models,
            "already_installed": already_installed,
        },
        # Executor nodes run sequentially, so peak—not sum—is the honest bound.
        "peak_vram_gb": round(peak_vram_gb, 1),
        "render_time": {
            "basis_audio_seconds": 60,
            "low_seconds": low_seconds,
            "high_seconds": high_seconds,
            "confidence": "rough",
            "note": "Hardware-agnostic range for one minute of source audio; cache hits may be faster.",
        },
        "models": model_rows,
        "nodes": estimated_nodes,
        "machine": machine,
        "checks": checks,
    }
