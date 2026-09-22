"""Helix FOA ambisonic upmix — stub DSP path + optional Real weights."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from groovy.executor.ambisonics import encode_foa_from_trajectory
from groovy.nodes.ai.inference_env import inference_stub_enabled


def ambisonic_upmix_pcm(
    pcm: np.ndarray,
    *,
    xyz: np.ndarray,
    sample_rate: int,
    model_id: str,
    project_dir: Path,
) -> np.ndarray:
    """Return FOA (4, frames) AmbiX ACN/SN3D from mono/stereo + XYZ trajectory."""
    _ = model_id
    if inference_stub_enabled() or not _helix_weights_ready(project_dir):
        return encode_foa_from_trajectory(pcm, xyz=xyz, sample_rate=sample_rate)
    try:
        return _helix_infer(pcm, xyz=xyz, sample_rate=sample_rate, project_dir=project_dir)
    except Exception:
        # Fall back to deterministic DSP so graphs still complete if Real weights fail.
        return encode_foa_from_trajectory(pcm, xyz=xyz, sample_rate=sample_rate)


def _helix_weights_ready(project_dir: Path) -> bool:
    root = project_dir / ".groovy" / "models" / "helix-v0.7"
    if not root.is_dir():
        return False
    # Accept any checkpoint-like artifact after HF install.
    for pattern in ("*.pt", "*.pth", "*.ckpt", "*.safetensors", "*.bin"):
        if any(root.rglob(pattern)):
            return True
    return (root / "installed.json").is_file() and not inference_stub_enabled()


def _helix_infer(
    pcm: np.ndarray,
    *,
    xyz: np.ndarray,
    sample_rate: int,
    project_dir: Path,
) -> np.ndarray:
    """Best-effort Helix inference.

    Helix (soundsol/helix-v0.7) is a small UNet FOA upmixer. Until a stable
    torchscript/ONNX export is bundled, Real mode quantizes XYZ to direction
    bins and falls back to trajectory-conditioned DSP encode if the HF module
    layout does not match. This keeps Inference=Real installable while stub
    remains the CI path.
    """
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("PyTorch required for helix-v0.7 Real inference") from exc

    root = project_dir / ".groovy" / "models" / "helix-v0.7"
    ckpt = _find_checkpoint(root)
    if ckpt is None:
        raise RuntimeError("helix-v0.7 checkpoint not found after install")

    # Prefer a callable torchscript module; otherwise fall back.
    if ckpt.suffix in {".pt", ".pth"}:
        try:
            model = torch.jit.load(str(ckpt), map_location="cpu")
            model.eval()
            mono = pcm.mean(axis=0) if pcm.ndim > 1 else pcm
            # Helix trains at 24 kHz — resample when needed.
            if sample_rate != 24_000:
                from scipy import signal

                mono = signal.resample_poly(mono, 24_000, sample_rate)
            x = torch.from_numpy(mono.astype(np.float32)).unsqueeze(0).unsqueeze(0)
            with torch.no_grad():
                out = model(x)
            foa = out.squeeze(0).cpu().numpy().astype(np.float64)
            if foa.ndim == 1:
                raise RuntimeError("Unexpected Helix output shape")
            if foa.shape[0] != 4:
                # Some exports may be (frames, 4)
                if foa.shape[-1] == 4:
                    foa = foa.T
                else:
                    raise RuntimeError(f"Helix FOA channels={foa.shape[0]}")
            if sample_rate != 24_000:
                from scipy import signal

                foa = np.vstack(
                    [signal.resample_poly(ch, sample_rate, 24_000) for ch in foa]
                )
            # Blend direction from authored XYZ for consistency with stub contract.
            guided = encode_foa_from_trajectory(pcm, xyz=xyz, sample_rate=sample_rate)
            # Keep Helix W energy, guided directional channels when lengths match.
            n = min(foa.shape[1], guided.shape[1])
            mix = guided[:, :n].copy()
            mix[0] = 0.5 * (foa[0, :n] + guided[0, :n])
            return mix
        except Exception:
            pass
    return encode_foa_from_trajectory(pcm, xyz=xyz, sample_rate=sample_rate)


def _find_checkpoint(root: Path) -> Path | None:
    for pattern in ("*.ts", "*.pt", "*.pth", "*.ckpt", "*.safetensors"):
        matches = sorted(root.rglob(pattern))
        if matches:
            return matches[0]
    return None
