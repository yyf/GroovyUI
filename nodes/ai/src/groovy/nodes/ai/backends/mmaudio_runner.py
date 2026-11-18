"""MMAudio video±text → Foley/SFX (hkchengrex/MMAudio).

Code MIT; checkpoints CC-BY-NC-4.0 on Hugging Face. Prefer MPS on Apple Silicon
(with PYTORCH_ENABLE_MPS_FALLBACK=1), else CUDA, else CPU.
"""

from __future__ import annotations

import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

NATIVE_SAMPLE_RATE = 44_100
REPO_URL = "https://github.com/hkchengrex/MMAudio.git"
DEFAULT_VARIANT = "large_44k_v2"


def _model_root() -> Path:
    override = os.environ.get("GROOVY_MMAUDIO_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    project = os.environ.get("GROOVY_PROJECT_DIR", "").strip()
    if project:
        return Path(project).expanduser().resolve() / ".groovy" / "models" / "mmaudio"
    return Path.home() / ".groovy" / "models" / "mmaudio"


def _repo_dir(root: Path) -> Path:
    return root / "MMAudio"


def _ensure_repo(root: Path) -> Path:
    repo = _repo_dir(root)
    marker = repo / "mmaudio" / "eval_utils.py"

    def _complete() -> bool:
        return marker.is_file()

    if _complete():
        return repo

    root.mkdir(parents=True, exist_ok=True)
    if (repo / ".git").is_dir():
        pull = subprocess.run(
            ["git", "-C", str(repo), "pull", "--ff-only"],
            capture_output=True,
            text=True,
        )
        if pull.returncode != 0 and not _complete():
            import shutil

            shutil.rmtree(repo, ignore_errors=True)

    if not _complete():
        if repo.exists() and not (repo / ".git").is_dir():
            import shutil

            shutil.rmtree(repo, ignore_errors=True)
        clone = subprocess.run(
            ["git", "clone", "--depth", "1", REPO_URL, str(repo)],
            capture_output=True,
            text=True,
        )
        if clone.returncode != 0:
            detail = (clone.stderr or clone.stdout or "git clone failed").strip()
            raise RuntimeError(
                f"Could not clone MMAudio from {REPO_URL}: {detail[:400]}\n"
                f"Clone manually into {repo} or set GROOVY_MMAUDIO_ROOT."
            )

    if not _complete():
        raise RuntimeError(
            f"MMAudio clone incomplete (missing mmaudio/eval_utils.py). "
            f"Clone https://github.com/hkchengrex/MMAudio into {repo}."
        )
    return repo


def _link_workspace_ext_weights(repo: Path) -> None:
    """Reuse repo ``ext_weights/`` VAE + Synchformer when present (local Mac cache)."""
    project = os.environ.get("GROOVY_PROJECT_DIR", "").strip()
    if not project:
        # Walk up from this file: .../GroovyUI/nodes/ai/... → repo root is parents[5]
        here = Path(__file__).resolve()
        candidates = [p for p in here.parents if (p / "ext_weights").is_dir()]
        workspace = candidates[0] if candidates else None
    else:
        workspace = Path(project).expanduser().resolve()
        # Project dir may be workspace/; also try parent for monorepo checkout.
        if not (workspace / "ext_weights").is_dir() and (workspace.parent / "ext_weights").is_dir():
            workspace = workspace.parent
    if workspace is None:
        return
    src_ext = workspace / "ext_weights"
    if not src_ext.is_dir():
        return
    dest_ext = repo / "ext_weights"
    dest_ext.mkdir(parents=True, exist_ok=True)
    for name in ("v1-44.pth", "synchformer_state_dict.pth", "v1-16.pth", "best_netG.pt"):
        src = src_ext / name
        dest = dest_ext / name
        if src.is_file() and not dest.exists():
            try:
                dest.symlink_to(src)
            except OSError:
                import shutil

                shutil.copy2(src, dest)


def _pick_device():
    import torch

    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@lru_cache(maxsize=2)
def _load_pipeline(variant: str):
    import torch

    root = _model_root()
    repo = _ensure_repo(root)
    _link_workspace_ext_weights(repo)

    # MMAudio expects cwd-relative ./weights and ./ext_weights paths.
    prev = os.getcwd()
    try:
        os.chdir(repo)
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))

        from mmaudio.eval_utils import all_model_cfg
        from mmaudio.model.flow_matching import FlowMatching
        from mmaudio.model.networks import get_my_mmaudio
        from mmaudio.model.utils.features_utils import FeaturesUtils

        if variant not in all_model_cfg:
            raise RuntimeError(
                f"Unknown MMAudio variant {variant!r}. "
                f"Known: {', '.join(sorted(all_model_cfg))}."
            )
        model = all_model_cfg[variant]
        model.download_if_needed()

        device = _pick_device()
        # bf16 is flaky on MPS; use float32 there and on CPU.
        dtype = torch.float32 if device in ("mps", "cpu") else torch.bfloat16
        net = get_my_mmaudio(model.model_name).to(device, dtype).eval()
        net.load_weights(torch.load(model.model_path, map_location=device, weights_only=True))
        feature_utils = FeaturesUtils(
            tod_vae_ckpt=model.vae_path,
            synchformer_ckpt=model.synchformer_ckpt,
            enable_conditions=True,
            mode=model.mode,
            bigvgan_vocoder_ckpt=model.bigvgan_16k_path,
            need_vae_encoder=False,
        )
        feature_utils = feature_utils.to(device, dtype).eval()
        return {
            "repo": repo,
            "model": model,
            "net": net,
            "feature_utils": feature_utils,
            "device": device,
            "dtype": dtype,
            "FlowMatching": FlowMatching,
        }
    finally:
        os.chdir(prev)


def variant_for_model_id(model_id: str) -> str:
    mapping = {
        "mmaudio-large-44k-v2": "large_44k_v2",
        "mmaudio-large-44k": "large_44k",
        "mmaudio-medium-44k": "medium_44k",
        "mmaudio-small-44k": "small_44k",
        "mmaudio": "large_44k_v2",
    }
    return mapping.get(model_id, DEFAULT_VARIANT)


def generate_from_video(
    *,
    video_path: Path | None,
    prompt: str,
    negative_prompt: str = "",
    sample_rate: int = NATIVE_SAMPLE_RATE,
    duration: float = 8.0,
    num_steps: int = 25,
    cfg_strength: float = 4.5,
    seed: int | None = None,
    variant: str = DEFAULT_VARIANT,
) -> np.ndarray:
    """Return planar float64 audio @ ``sample_rate``."""
    import torch

    pipe = _load_pipeline(variant)
    repo: Path = pipe["repo"]
    model = pipe["model"]
    net = pipe["net"]
    feature_utils = pipe["feature_utils"]
    device = pipe["device"]
    FlowMatching = pipe["FlowMatching"]

    prev = os.getcwd()
    try:
        os.chdir(repo)
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        from mmaudio.eval_utils import generate, load_video

        seq_cfg = model.seq_cfg
        duration_sec = float(max(1.0, min(duration, 30.0)))
        clip_frames = sync_frames = None
        if video_path is not None:
            video_info = load_video(Path(video_path), duration_sec)
            clip_frames = video_info.clip_frames.unsqueeze(0)
            sync_frames = video_info.sync_frames.unsqueeze(0)
            duration_sec = float(video_info.duration_sec)

        seq_cfg.duration = duration_sec
        net.update_seq_lengths(seq_cfg.latent_seq_len, seq_cfg.clip_seq_len, seq_cfg.sync_seq_len)

        rng_device = device if device == "cuda" else "cpu"
        rng = torch.Generator(device=rng_device)
        if seed is not None and seed >= 0:
            rng.manual_seed(int(seed) % (2**63 - 1))
        else:
            rng.seed()

        fm = FlowMatching(min_sigma=0, inference_mode="euler", num_steps=max(4, int(num_steps)))
        audios = generate(
            clip_frames,
            sync_frames,
            [prompt or ""],
            negative_text=[negative_prompt or ""],
            feature_utils=feature_utils,
            net=net,
            fm=fm,
            rng=rng,
            cfg_strength=float(cfg_strength),
        )
        audio = audios.float().cpu()[0]
        return _to_planar(audio, native_sr=int(seq_cfg.sampling_rate), target_sr=sample_rate)
    finally:
        os.chdir(prev)


def _to_planar(audio, *, native_sr: int, target_sr: int) -> np.ndarray:
    import torch
    import torchaudio

    if isinstance(audio, torch.Tensor):
        arr = audio.detach().float().cpu()
    else:
        arr = torch.from_numpy(np.asarray(audio, dtype=np.float32))
    if arr.ndim == 1:
        arr = arr.unsqueeze(0)
    elif arr.ndim == 3:
        arr = arr[0]
    if arr.shape[0] > arr.shape[-1]:
        arr = arr.T
    if target_sr != native_sr:
        arr = torchaudio.functional.resample(arr, native_sr, target_sr)
    return arr.numpy().astype(np.float64)
