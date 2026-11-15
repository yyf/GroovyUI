"""LTX-2.3 Q4 MLX text-to-video for Apple Silicon (resource-constrained Macs).

Uses community ``ltx-2-mlx`` (dgrauet) with ``dgrauet/ltx-2.3-mlx-q4`` + ``--low-ram``.
Target envelope: M1/M2/M3 Max ≥32 GB unified memory, short clips at ~512p.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

HF_REPO = "dgrauet/ltx-2.3-mlx-q4"
# Distilled-only slice of the Hub repo (full snapshot is 50+ GB with duplicate transformers).
# Distilled two-stage slice only (skip transformer-dev / duplicate LoRAs / x1.5 upscaler).
_ALLOW_PATTERNS = (
    "transformer-distilled.safetensors",
    "connector.safetensors",
    "vae_encoder.safetensors",
    "vae_decoder.safetensors",
    "audio_vae.safetensors",
    "vocoder.safetensors",
    "ltx-2.3-22b-distilled-lora-384.safetensors",
    "spatial_upscaler_x2_v1_1.safetensors",
    "spatial_upscaler_x2_v1_1_config.json",
    "config.json",
    "embedded_config.json",
    "split_model.json",
    "quantize_config.json",
    "LICENSE",
    "README.md",
)
_REQUIRED = (
    "transformer-distilled.safetensors",
    "connector.safetensors",
    "vae_decoder.safetensors",
    "config.json",
)


def _model_root() -> Path:
    override = os.environ.get("GROOVY_LTX_MLX_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    project = os.environ.get("GROOVY_PROJECT_DIR", "").strip()
    if project:
        return Path(project).expanduser().resolve() / ".groovy" / "models" / "ltx-2.3-q4"
    return Path.home() / ".groovy" / "models" / "ltx-2.3-q4"


def _pack_ready(root: Path) -> bool:
    if not root.is_dir():
        return False
    return all((root / name).is_file() for name in _REQUIRED)


def ensure_weights(root: Path | None = None) -> Path:
    """Download the distilled-only LTX-2.3 Q4 slice (~20 GB) into the model dir."""
    dest = root or _model_root()
    if _pack_ready(dest):
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is required to download LTX-2.3 Q4. "
            "Install from Model Browser or: uv pip install huggingface_hub"
        ) from exc

    # Fail fast when the volume cannot hold the pack.
    usage = shutil.disk_usage(dest)
    # Distilled transformer + connector + VAEs + LoRA + x2 upscaler ≈ 27 GB; Gemma TE may add more.
    need = 30 * 1024**3
    if usage.free < need:
        free_gb = usage.free / (1024**3)
        raise RuntimeError(
            f"Not enough free disk for LTX-2.3 Q4 distilled slice (~27 GB pack; need ≥30 GB free, "
            f"have {free_gb:.1f} GB). Free Hugging Face caches in Terminal, then retry:\n"
            f"  bash scripts/setup-ltx-mac.sh --free-disk\n"
            f"  bash scripts/setup-ltx-mac.sh"
        )

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or None
    snapshot_download(
        repo_id=HF_REPO,
        local_dir=str(dest),
        local_dir_use_symlinks=False,
        token=token,
        allow_patterns=list(_ALLOW_PATTERNS),
    )
    if not _pack_ready(dest):
        raise RuntimeError(
            f"Downloaded {HF_REPO} but required files are missing under {dest}. "
            "Check the Hub card / retry download."
        )
    return dest


def _snap_dim(value: int, *, multiple: int = 32, lo: int = 256, hi: int = 768) -> int:
    v = max(lo, min(hi, int(value)))
    return max(multiple, v - (v % multiple))


def _frame_count(duration_sec: float, *, fps: int = 24) -> int:
    """LTX expects 8n+1 frames."""
    target = max(9, int(round(float(duration_sec) * fps)))
    n = max(1, round((target - 1) / 8))
    frames = 8 * n + 1
    # Cap short demos on 32 GB Macs (~2.7 s at 24 fps).
    return min(frames, 65)


@lru_cache(maxsize=1)
def _resolve_cli() -> list[str]:
    """Return argv prefix for the ltx-2-mlx CLI."""
    sibling = Path(sys.executable).resolve().parent / "ltx-2-mlx"
    if sibling.is_file() and os.access(sibling, os.X_OK):
        return [str(sibling)]
    which = shutil.which("ltx-2-mlx")
    if which:
        return [which]
    raise RuntimeError(
        "ltx-2-mlx is not installed. From the GroovyUI venv run:\n"
        "  bash scripts/setup-ltx-mac.sh\n"
        "Or: uv pip install "
        "'ltx-pipelines-mlx @ git+https://github.com/dgrauet/ltx-2-mlx.git#subdirectory=packages/ltx-pipelines-mlx' "
        "'ltx-core-mlx @ git+https://github.com/dgrauet/ltx-2-mlx.git#subdirectory=packages/ltx-core-mlx' mlx"
    )


def generate_mp4(
    prompt: str,
    *,
    dest: Path,
    duration: float = 2.0,
    width: int = 512,
    height: int = 512,
    seed: int | None = None,
    negative_prompt: str = "",
    low_ram: bool = True,
    image_path: Path | str | None = None,
    image_strength: float = 1.0,
) -> Path:
    """Run distilled + low-ram LTX-2.3 Q4 → ``dest`` mp4.

    Optional ``image_path`` enables image-to-video (``--image PATH 0 STRENGTH``).
    """
    _ = negative_prompt  # Distilled path has no CFG negative.
    if not prompt.strip():
        raise RuntimeError("LTX-2.3 Q4 needs a non-empty text prompt.")

    pack = ensure_weights()
    dest = Path(dest).with_suffix(".mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)

    w = _snap_dim(width)
    h = _snap_dim(height)
    frames = _frame_count(duration, fps=24)
    cli = _resolve_cli()
    cmd = [
        *cli,
        "generate",
        "--distilled",
        "--model",
        str(pack),
        "--prompt",
        prompt.strip(),
        "-H",
        str(h),
        "-W",
        str(w),
        "-f",
        str(frames),
        "--frame-rate",
        "24",
        "-o",
        str(dest),
    ]
    if image_path is not None:
        img = Path(image_path).expanduser().resolve()
        if not img.is_file():
            raise RuntimeError(f"Reference image not found: {img}")
        # LTX --image PATH FRAME STRENGTH expects STRENGTH in [0, 1] (default 1.0).
        strength = max(0.0, min(1.0, float(image_strength)))
        cmd.extend(["--image", str(img), "0", str(strength)])
    if low_ram:
        cmd.append("--low-ram")
    if seed is not None and int(seed) >= 0:
        cmd.extend(["--seed", str(int(seed))])

    env = os.environ.copy()
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    # Keep Metal from fighting the browser for every last byte.
    env.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0 or not dest.is_file():
        detail = (result.stderr or result.stdout or "ltx-2-mlx failed").strip()
        raise RuntimeError(
            "LTX-2.3 Q4 MLX generation failed. On 32 GB Macs use 512×512, ≤2–3 s, "
            "close other apps, and ensure --low-ram. "
            f"Detail: {detail[:800]}"
        )
    return dest


def available() -> bool:
    try:
        _resolve_cli()
        return True
    except RuntimeError:
        return False
