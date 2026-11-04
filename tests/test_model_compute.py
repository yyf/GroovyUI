from __future__ import annotations

from groovy.registry.catalog import ModelCatalog
from groovy.registry.compute import filter_manifests_by_compute, resolve_compute
from groovy.registry.models import ComputeInfo, LicenseInfo, ModelManifest


def _manifest(**kwargs) -> ModelManifest:
    base = dict(
        id="demo",
        name="Demo",
        description="",
        task_types=["denoise"],
        license=LicenseInfo(spdx="MIT", commercial_ok=True),
    )
    base.update(kwargs)
    return ModelManifest(**base)


def test_resolve_compute_cuda_only() -> None:
    resolved = resolve_compute(
        _manifest(
            id="diff-foley",
            compute=ComputeInfo(runtimes=["cuda"], requires_cuda=True),
        )
    )
    assert resolved["requires_cuda"] is True
    assert "cuda" in resolved["runtimes"]
    assert "apple" not in resolved["presets"]
    assert "CUDA required" in resolved["label"]


def test_resolve_compute_apple_mlx() -> None:
    resolved = resolve_compute(
        _manifest(
            id="step-audio-editx",
            tags=["mlx", "apple-silicon"],
            compute=ComputeInfo(runtimes=["mlx", "cuda"], label="Apple Silicon (MLX) / CUDA · ~4 GB"),
        )
    )
    assert "mlx" in resolved["runtimes"]
    assert "apple" in resolved["presets"]
    assert "cuda" in resolved["presets"]


def test_filter_preset_apple_excludes_cuda_only() -> None:
    catalog = ModelCatalog()
    apple = filter_manifests_by_compute(list(catalog.all()), "apple")
    ids = {m.id for m in apple}
    assert "diff-foley" not in ids
    assert "deepfilternet-v3" in ids or "basic-pitch" in ids


def test_filter_preset_cuda_includes_ace() -> None:
    catalog = ModelCatalog()
    cuda = filter_manifests_by_compute(list(catalog.all()), "cuda")
    ids = {m.id for m in cuda}
    assert "ace-step-1.5-sft" in ids or "ace-step-1.5" in ids


def test_seed_compute_round_trip() -> None:
    catalog = ModelCatalog()
    step = catalog.get("step-audio-editx")
    assert step is not None
    resolved = resolve_compute(step)
    assert "apple" in resolved["presets"]
    assert resolved["label"]
