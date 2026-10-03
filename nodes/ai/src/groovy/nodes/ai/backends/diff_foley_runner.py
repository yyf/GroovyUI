"""Diff-Foley video → synchronized audio (luosiallen/Diff-Foley / SimianLuo HF).

Research notebook pipeline (NeurIPS 2023). Commercial-friendly: Apache-2.0 code,
MIT-labeled HF weights. Outputs 16 kHz mono. Text prompts are ignored (video-only).
"""

from __future__ import annotations

import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

NATIVE_SAMPLE_RATE = 16_000
HF_REPO = "SimianLuo/Diff-Foley"
CKPT_FILES = (
    "diff_foley_ckpt/cavp_epoch66.ckpt",
    "diff_foley_ckpt/ldm_epoch240.ckpt",
    "diff_foley_ckpt/double_guidance_classifier.ckpt",
)
REPO_URL = "https://github.com/luosiallen/Diff-Foley.git"


def _model_root() -> Path:
    override = os.environ.get("GROOVY_DIFF_FOLEY_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    # Prefer project model dir when executor set GROOVY_PROJECT_DIR.
    project = os.environ.get("GROOVY_PROJECT_DIR", "").strip()
    if project:
        return Path(project).expanduser().resolve() / ".groovy" / "models" / "diff-foley"
    return Path.home() / ".groovy" / "models" / "diff-foley"


def _ensure_repo(root: Path) -> Path:
    """Clone luosiallen/Diff-Foley if missing. Upstream has no package ``__init__.py``."""
    repo = root / "Diff-Foley"
    # Upstream layout: diff_foley/util.py + inference/demo_util.py (no __init__.py).
    markers = (
        repo / "diff_foley" / "util.py",
        repo / "inference" / "demo_util.py",
        repo / "inference" / "config" / "Stage2_LDM.yaml",
    )

    def _complete() -> bool:
        return all(path.is_file() for path in markers)

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
            # Broken / shallow clone — wipe and re-clone.
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
                f"Could not clone Diff-Foley from {REPO_URL}: {detail[:400]}\n"
                f"Clone manually into {repo} or set GROOVY_DIFF_FOLEY_ROOT to an existing checkout."
            )

    if not _complete():
        missing = [str(path.relative_to(repo)) for path in markers if not path.is_file()]
        raise RuntimeError(
            "Diff-Foley repo clone incomplete "
            f"(missing {', '.join(missing)}). "
            f"Clone https://github.com/luosiallen/Diff-Foley into {repo} "
            "or set GROOVY_DIFF_FOLEY_ROOT."
        )
    return repo


def _ensure_checkpoints(root: Path) -> Path:
    ckpt_dir = root / "diff_foley_ckpt"
    missing = [name for name in CKPT_FILES if not (root / name).is_file()]
    if not missing:
        return ckpt_dir
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is required to download Diff-Foley checkpoints. "
            "Install diff-foley from Model Browser (Cmd+K)."
        ) from exc
    for rel in CKPT_FILES:
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file():
            continue
        path = hf_hub_download(repo_id=HF_REPO, filename=rel, local_dir=str(root))
        # hf_hub_download may place under root/rel already; ensure dest exists.
        downloaded = Path(path)
        if downloaded.resolve() != dest.resolve() and downloaded.is_file():
            dest.write_bytes(downloaded.read_bytes())
    return ckpt_dir


@lru_cache(maxsize=1)
def _load_pipeline():
    import torch
    from omegaconf import OmegaConf

    root = _model_root()
    repo = _ensure_repo(root)
    _ensure_checkpoints(root)

    # Diff-Foley expects repo root + inference/ on sys.path.
    inference_dir = repo / "inference"
    for path in (str(repo), str(inference_dir)):
        if path not in sys.path:
            sys.path.insert(0, path)

    from demo_util import Extract_CAVP_Features  # type: ignore
    from diff_foley.util import instantiate_from_config  # type: ignore

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        # Upstream demo hard-requires CUDA tensors / .cuda() in Extract_CAVP_Features.
        raise RuntimeError(
            "Diff-Foley real inference needs an NVIDIA CUDA GPU (upstream demo path). "
            "This machine has no CUDA. Set Settings → Inference = Stub for demos/CI, "
            "or run on a CUDA host."
        )

    cavp_config = str(inference_dir / "config" / "Stage1_CAVP.yaml")
    cavp_ckpt = str(root / "diff_foley_ckpt" / "cavp_epoch66.ckpt")
    extract_cavp = Extract_CAVP_Features(
        fps=4,
        batch_size=40,
        device=device,
        config_path=cavp_config,
        ckpt_path=cavp_ckpt,
    )

    def load_model_from_config(config, ckpt: str):
        pl_sd = torch.load(ckpt, map_location="cpu")
        sd = pl_sd["state_dict"] if "state_dict" in pl_sd else pl_sd
        model = instantiate_from_config(config.model)
        model.load_state_dict(sd, strict=False)
        model.to(device)
        model.eval()
        return model

    ldm_config = OmegaConf.load(str(inference_dir / "config" / "Stage2_LDM.yaml"))
    ldm = load_model_from_config(ldm_config, str(root / "diff_foley_ckpt" / "ldm_epoch240.ckpt"))

    classifier = None
    classifier_ckpt = root / "diff_foley_ckpt" / "double_guidance_classifier.ckpt"
    if classifier_ckpt.is_file():
        classifier_config = OmegaConf.load(
            str(inference_dir / "config" / "Double_Guidance_Classifier.yaml")
        )
        classifier = load_model_from_config(classifier_config, str(classifier_ckpt))

    return extract_cavp, ldm, classifier, device, inference_dir, root


def generate_from_video(
    *,
    video_path: Path,
    sample_rate: int,
    duration: float = 8.0,
    num_steps: int = 25,
    cfg_strength: float = 4.5,
    seed: int | None = None,
) -> np.ndarray:
    """Run Diff-Foley on a silent/source video; returns planar float64 @ sample_rate."""
    import tempfile

    import torch

    _ = cfg_strength  # Double-guidance scale is fixed in upstream demo configs.
    extract_cavp, ldm, classifier, device, inference_dir, _root = _load_pipeline()

    if seed is not None:
        torch.manual_seed(int(seed))
        if device.type == "cuda":
            torch.cuda.manual_seed(int(seed))

    truncate = float(max(1.0, min(duration, 16.0)))
    with tempfile.TemporaryDirectory(prefix="diff_foley_") as tmp:
        tmp_path = Path(tmp)
        cavp_feats, _new_video = extract_cavp(
            str(video_path),
            0.0,
            truncate,
            tmp_path=str(tmp_path),
        )
        # cavp_feats: [T, D] — match notebook windowing / sample API when present.
        feats = torch.as_tensor(cavp_feats, device=device, dtype=torch.float32)
        if feats.ndim == 2:
            feats = feats.unsqueeze(0)

        # Prefer the notebook's generation helpers if exposed on the LDM module.
        generate_fn = getattr(ldm, "sample", None) or getattr(ldm, "generate", None)
        if generate_fn is None:
            raise RuntimeError(
                "Diff-Foley LDM does not expose a sample/generate entrypoint in this checkout. "
                "Update the Diff-Foley clone or set Inference=Stub."
            )

        kwargs: dict = {"steps": int(num_steps)}
        if classifier is not None:
            kwargs["classifier"] = classifier
        try:
            audio = generate_fn(feats, **kwargs)
        except TypeError:
            audio = generate_fn(feats)

    pcm = _to_planar(audio, target_sr=sample_rate)
    return pcm


def _to_planar(audio, *, target_sr: int) -> np.ndarray:
    import torch
    import torchaudio

    if isinstance(audio, torch.Tensor):
        arr = audio.detach().float().cpu().numpy()
    else:
        arr = np.asarray(audio, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    elif arr.ndim == 3:
        arr = arr[0]
    if arr.shape[0] > arr.shape[-1]:
        arr = arr.T
    # Upstream Griffin-Lim path is 16 kHz mono.
    src = torch.from_numpy(arr.astype(np.float32))
    if src.shape[0] > 1:
        src = src.mean(dim=0, keepdim=True)
    if target_sr != NATIVE_SAMPLE_RATE:
        src = torchaudio.functional.resample(src, NATIVE_SAMPLE_RATE, target_sr)
    return src.numpy().astype(np.float64)
