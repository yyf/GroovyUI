"""Optional mflux FLUX.2 [klein] text-to-image backend (Apple Silicon / MLX)."""

from __future__ import annotations

from pathlib import Path


def mflux_available() -> bool:
    try:
        from mflux.models.flux2.variants import Flux2Klein  # noqa: F401

        return True
    except Exception:
        return False


def generate_png(
    prompt: str,
    *,
    dest: Path,
    width: int = 512,
    height: int = 512,
    num_steps: int = 4,
    seed: int = 42,
    model_name: str = "flux-klein-4b",
) -> Path:
    """Generate a still with mflux Flux2Klein and write ``dest`` (PNG).

    mflux ≥0.24 exposes ``Flux2Klein`` (FLUX.2 klein 4B). First Real render may
    download weights into the Hugging Face cache.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _ = model_name  # Groovy registry id; Flux2Klein defaults to flux2_klein_4b.

    try:
        from mflux.models.flux2.variants import Flux2Klein
    except Exception as exc:  # pragma: no cover - optional dep / API drift
        raise RuntimeError(
            "mflux Flux2Klein is not importable. Install flux-klein-4b from the "
            "Model Browser (python dep: mflux≥0.24) or use flux-image path-demo."
        ) from exc

    try:
        model = Flux2Klein(quantize=8)
    except Exception as exc:
        raise RuntimeError(
            "Failed to load FLUX.2 klein 4B via mflux. "
            "Check HF cache / disk space, or use flux-image path-demo."
        ) from exc

    try:
        result = model.generate_image(
            seed=int(seed),
            prompt=str(prompt or "a calm still life"),
            num_inference_steps=max(1, int(num_steps)),
            width=int(width),
            height=int(height),
        )
    except Exception as exc:
        raise RuntimeError(
            f"mflux Flux2Klein generate_image failed: {exc}. "
            "Ensure Real inference mode and that weights finished downloading."
        ) from exc

    # GeneratedImage.save writes PNG; also accept raw PIL.
    if hasattr(result, "save"):
        result.save(dest, overwrite=True)
    else:
        image = getattr(result, "image", result)
        if hasattr(image, "save"):
            image.save(dest)
        elif isinstance(image, (str, Path)):
            Path(image).replace(dest)
        else:
            raise RuntimeError(f"Unexpected mflux result type: {type(result)!r}")

    if not dest.is_file():
        raise RuntimeError(f"mflux did not write image to {dest}")
    return dest
