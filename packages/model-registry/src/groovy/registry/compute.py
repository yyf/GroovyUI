"""Hardware / compute affinity for Model Browser presets and card labels.

Presets:
  - apple — Mac-accelerated Real path (MLX or MPS), or explicitly Mac-friendly CPU
  - cuda  — NVIDIA CUDA path (preferred or required)
  - cpu   — usable without a discrete GPU
  - any   — no filter (default catalog sort)
"""

from __future__ import annotations

from typing import Any

from groovy.registry.models import ComputeInfo, ModelManifest

ComputePreset = str  # "any" | "apple" | "cuda" | "cpu"

# Hard CUDA-only Real paths (no Mac Real inference in-tree).
_CUDA_ONLY_IDS = frozenset(
    {
        "diff-foley",
        "audio-flamingo-3",
        "ace-step-1.5",
        "ace-step-1.5-2b-turbo",
    }
)

# Explicit Apple Silicon / MLX (or MPS-first) Real paths.
_APPLE_IDS = frozenset(
    {
        "step-audio-editx",
        "stable-audio-3-small-music",
        "stable-audio-3-small-sfx",
    }
)

# CPU-friendly / no GPU required for demos.
_CPU_FRIENDLY_IDS = frozenset(
    {
        "basic-pitch",
        "deepfilternet-v3",
        "whisper-small-en",
        "kokoro-82m",
        "stable-audio-open-small",
        "stable-audio-3-small-music",
        "stable-audio-3-small-sfx",
    }
)


def _blob(manifest: ModelManifest) -> str:
    return " ".join(
        [
            manifest.id,
            manifest.name,
            manifest.description,
            " ".join(manifest.tags),
            manifest.architecture_notes or "",
            " ".join(manifest.compute.runtimes),
            manifest.compute.label or "",
            manifest.compute.memory_note or "",
        ]
    ).lower()


def resolve_compute(manifest: ModelManifest) -> dict[str, Any]:
    """Return a resolved compute summary for API cards / UI."""
    curated = manifest.compute
    runtimes = {r.strip().lower() for r in curated.runtimes if r and r.strip()}
    requires_cuda = bool(curated.requires_cuda)
    blob = _blob(manifest)

    if manifest.id in _CUDA_ONLY_IDS or "cuda-only" in blob or "requires nvidia" in blob:
        requires_cuda = True
        runtimes.add("cuda")

    if manifest.id in _APPLE_IDS or "mlx" in blob or "apple-silicon" in blob or "apple silicon" in blob:
        if "mlx" in blob or "mlx" in (t.lower() for t in manifest.tags):
            runtimes.add("mlx")
        if "mps" in blob or "mps" in (t.lower() for t in manifest.tags):
            runtimes.add("mps")
        if "mlx" not in runtimes and "mps" not in runtimes:
            runtimes.add("mps")

    if "mps" in blob or "mps" in (t.lower() for t in manifest.tags):
        runtimes.add("mps")

    if (
        manifest.id in _CPU_FRIENDLY_IDS
        or "cpu" in (t.lower() for t in manifest.tags)
        or "onnxruntime" in blob
        or "cpu/mps" in blob
        or "cpu-friendly" in blob
    ):
        runtimes.add("cpu")

    if "cuda" in blob or "nvidia" in blob or "prefer nvidia" in blob:
        runtimes.add("cuda")

    if not runtimes:
        # Typical PyTorch catalog entry: CPU possible (slow), CUDA when present.
        runtimes.update({"cpu", "cuda"})

    if requires_cuda:
        runtimes.discard("mlx")
        runtimes.discard("mps")
        # Keep cpu only when the seed explicitly allows a CPU fallback.
        if "cpu" not in curated.runtimes and manifest.id in _CUDA_ONLY_IDS:
            runtimes.discard("cpu")
        runtimes.add("cuda")

    ordered = [name for name in ("mlx", "mps", "cuda", "cpu") if name in runtimes]
    presets = _presets_for(ordered, requires_cuda=requires_cuda)
    label = curated.label.strip() if curated.label and curated.label.strip() else _format_label(
        ordered,
        requires_cuda=requires_cuda,
        vram_gb=manifest.vram_gb_estimate,
        memory_note=curated.memory_note,
    )
    return {
        "runtimes": ordered,
        "requires_cuda": requires_cuda,
        "presets": presets,
        "label": label,
        "vram_gb_estimate": manifest.vram_gb_estimate,
        "memory_note": curated.memory_note,
    }


def _presets_for(runtimes: list[str], *, requires_cuda: bool) -> list[str]:
    presets: list[str] = []
    # Apple Silicon = MLX/MPS accel, or a documented CPU path that is not CUDA-only.
    # CUDA-first packs without ``cpu`` in runtimes stay out (e.g. ACE-Step on Mac).
    if "mlx" in runtimes or "mps" in runtimes:
        presets.append("apple")
    elif "cpu" in runtimes and not requires_cuda:
        presets.append("apple")
    if "cuda" in runtimes or requires_cuda:
        presets.append("cuda")
    if "cpu" in runtimes and not requires_cuda:
        presets.append("cpu")
    return presets


def _format_label(
    runtimes: list[str],
    *,
    requires_cuda: bool,
    vram_gb: float,
    memory_note: str | None,
) -> str:
    if memory_note and memory_note.strip():
        mem = memory_note.strip()
    elif vram_gb and vram_gb > 0:
        if requires_cuda or "cuda" in runtimes:
            mem = f"~{vram_gb:g} GB VRAM"
        elif "mlx" in runtimes:
            mem = f"~{vram_gb:g} GB (MLX)"
        else:
            mem = f"~{vram_gb:g} GB"
    else:
        mem = "memory n/a"

    if requires_cuda:
        return f"CUDA required · {mem}"

    parts: list[str] = []
    if "mlx" in runtimes:
        parts.append("Apple Silicon (MLX)")
    elif "mps" in runtimes:
        parts.append("Apple Silicon (MPS)")
    if "cuda" in runtimes:
        parts.append("CUDA")
    if "cpu" in runtimes:
        parts.append("CPU")
    if not parts:
        parts.append("Any host")
    return f"{' / '.join(parts)} · {mem}"


def matches_compute_preset(resolved: dict[str, Any], preset: ComputePreset) -> bool:
    if not preset or preset == "any":
        return True
    return preset in set(resolved.get("presets") or [])


def filter_manifests_by_compute(
    manifests: list[ModelManifest],
    preset: ComputePreset,
) -> list[ModelManifest]:
    if not preset or preset == "any":
        return list(manifests)
    out: list[ModelManifest] = []
    for manifest in manifests:
        resolved = resolve_compute(manifest)
        if matches_compute_preset(resolved, preset):
            out.append(manifest)
    return out


def sort_key_for_preset(manifest: ModelManifest, preset: ComputePreset) -> tuple:
    """Lower is better when a hardware preset is active."""
    resolved = resolve_compute(manifest)
    runtimes = set(resolved.get("runtimes") or [])
    requires = bool(resolved.get("requires_cuda"))
    vram = float(manifest.vram_gb_estimate or 0)
    if preset == "apple":
        prefer = 0 if ("mlx" in runtimes or "mps" in runtimes) else 1
        return (prefer, vram, manifest.name.lower())
    if preset == "cuda":
        prefer = 0 if requires else 1
        return (prefer, -vram, manifest.name.lower())
    if preset == "cpu":
        prefer = 0 if "cpu" in runtimes and not requires else 1
        return (prefer, vram, manifest.name.lower())
    return (0, manifest.name.lower())
