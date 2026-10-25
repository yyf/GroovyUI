"""Step-Audio-EditX emotion/style editor.

Two real-inference backends:

1. **Apple Silicon (Darwin arm64)** — ``mlx-speech`` + HF
   ``appautomaton/step-audio-editx-8bit-mlx`` in a Python 3.13 sidecar venv
   (GroovyUI's main env is often 3.12; mlx-speech requires ≥3.13).
2. **NVIDIA CUDA Linux** — upstream ``stepfun-ai/Step-Audio-EditX`` + vLLM
   (Diff-Foley-style git clone + weight download).
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

REPO_URL = "https://github.com/stepfun-ai/Step-Audio-EditX.git"
HF_EDITX = "stepfun-ai/Step-Audio-EditX"
HF_TOKENIZER = "stepfun-ai/Step-Audio-Tokenizer"
MLX_MODEL_ALIAS = "step-audio"
NATIVE_SAMPLE_RATE = 24_000

VALID_EDIT_TYPES = frozenset(
    {"emotion", "style", "speed", "denoise", "vad", "paralinguistic", "clone"}
)
# Users often put the sub-type (whisper, radio, happy…) into edit_type by mistake.
EMOTION_INFOS = frozenset(
    {
        "happy",
        "angry",
        "sad",
        "fear",
        "surprised",
        "excited",
        "confused",
        "confusion",
        "empathy",
        "embarrass",
        "depressed",
        "admiration",
        "coldness",
        "disgusted",
        "humour",
        "humor",
    }
)
STYLE_INFOS = frozenset(
    {
        "whisper",
        "serious",
        "child",
        "older",
        "girl",
        "sweet",
        "exaggerated",
        "ethereal",
        "generous",
        "act_coy",
        "warm",
        "shy",
        "chat",
        "radio",
        "news",
        "advertising",
        "recite",
        "story",
        "vivid",
        "roar",
        "murmur",
        "shout",
        "deeply",
        "loudly",
        "pure",
        "sister",
        "arrogant",
        "comfort",
        "authority",
        "soulful",
        "gentle",
        "program",
    }
)
SPEED_INFOS = frozenset({"faster", "slower", "more faster", "more slower"})

_MLX_WORKER = r"""
import json
import os
import sys
from pathlib import Path

# Keep stderr readable in GroovyUI job errors (no HF/tqdm progress spam).
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")

import numpy as np
import soundfile as sf
import mlx_speech

payload = json.loads(Path(sys.argv[1]).read_text())
model = mlx_speech.tts.load(payload.get("model_alias") or "step-audio")
edit_type = payload.get("edit_type")
kwargs = {
    "reference_audio": payload["prompt_wav"],
    "reference_text": payload["prompt_text"],
}
if edit_type and edit_type != "clone":
    kwargs["edit_type"] = edit_type
    if payload.get("edit_info"):
        kwargs["edit_info"] = payload["edit_info"]
    text = payload.get("target_text") or None
else:
    text = payload.get("target_text") or payload["prompt_text"]
result = model.generate(text, **kwargs)
wav = np.asarray(result.waveform, dtype=np.float64)
if wav.ndim > 1:
    wav = wav.reshape(-1)
sf.write(payload["out_wav"], wav, int(result.sample_rate))
meta = {"sample_rate": int(result.sample_rate), "samples": int(wav.size)}
Path(payload["out_meta"]).write_text(json.dumps(meta))
"""


def normalize_edit_params(edit_type: str, edit_info: str) -> tuple[str, str]:
    """Map mistaken edit_type=radio/whisper/… into edit_type=style + edit_info."""
    et = (edit_type or "emotion").strip().lower()
    ei = (edit_info or "").strip()
    ei_l = ei.lower()

    if et in VALID_EDIT_TYPES:
        return et, ei

    # Sub-type was typed into edit_type (common VoiceConvert mix-up).
    if et in STYLE_INFOS:
        return "style", et if not ei_l else ei
    if et in EMOTION_INFOS:
        return "emotion", et if not ei_l else ei
    if et in SPEED_INFOS:
        return "speed", et if not ei_l else ei

    raise RuntimeError(
        f"Unsupported Step-Audio-EditX edit_type={edit_type!r}. "
        f"Use edit_type in {{{', '.join(sorted(VALID_EDIT_TYPES))}}}. "
        "Sub-types like radio / whisper / happy go in edit_info "
        "(e.g. edit_type=style, edit_info=radio)."
    )


def _summarize_worker_error(stdout: str, stderr: str, *, limit: int = 700) -> str:
    """Drop HF/tqdm progress noise; prefer the last meaningful traceback lines."""
    import re

    progress_re = re.compile(
        r"(Fetching \d+ files|Downloading|^\s*\d+%\|)|it/s\]|█|▋|▎",
        re.IGNORECASE,
    )
    chunks: list[str] = []
    for blob in (stderr, stdout):
        for line in (blob or "").splitlines():
            stripped = line.strip()
            if not stripped or progress_re.search(stripped):
                continue
            chunks.append(stripped)
    if not chunks:
        raw = (stderr or stdout or "mlx-speech worker failed").strip()
        return raw[-limit:] if len(raw) > limit else raw
    joined = "\n".join(chunks[-40:])
    return joined[-limit:] if len(joined) > limit else joined


def _model_root() -> Path:
    override = os.environ.get("GROOVY_STEP_AUDIO_EDITX_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    project = os.environ.get("GROOVY_PROJECT_DIR", "").strip()
    if project:
        return Path(project).expanduser().resolve() / ".groovy" / "models" / "step-audio-editx"
    return Path.home() / ".groovy" / "models" / "step-audio-editx"


def apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _which_uv() -> str | None:
    import shutil

    return shutil.which("uv")


def _ensure_mlx_python() -> Path:
    """Bootstrap a Python 3.13 venv with mlx-speech under the model root."""
    root = _model_root()
    venv = root / "mlx-venv"
    py = venv / "bin" / "python"
    marker = venv / ".groovy-mlx-speech-ok"
    if py.is_file() and marker.is_file():
        probe = subprocess.run(
            [str(py), "-c", "import mlx_speech"],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return py

    uv = _which_uv()
    if not uv:
        raise RuntimeError(
            "Step-Audio-EditX on Apple Silicon needs `uv` to bootstrap a Python 3.13 "
            "sidecar with mlx-speech. Install uv (https://docs.astral.sh/uv/), or set "
            "Settings → Inference = Stub for demos."
        )

    root.mkdir(parents=True, exist_ok=True)
    install_py = subprocess.run(
        [uv, "python", "install", "3.13"],
        capture_output=True,
        text=True,
    )
    if install_py.returncode != 0:
        detail = (install_py.stderr or install_py.stdout or "").strip()
        raise RuntimeError(
            "Could not install Python 3.13 via uv for Step-Audio-EditX MLX sidecar. "
            f"{detail[:400]}"
        )

    if venv.exists() and not py.is_file():
        import shutil

        shutil.rmtree(venv, ignore_errors=True)

    if not py.is_file():
        create = subprocess.run(
            [uv, "venv", "--python", "3.13", str(venv)],
            capture_output=True,
            text=True,
        )
        if create.returncode != 0 or not py.is_file():
            detail = (create.stderr or create.stdout or "").strip()
            raise RuntimeError(
                f"Could not create mlx-speech venv at {venv}: {detail[:400]}"
            )

    pip = subprocess.run(
        [uv, "pip", "install", "--python", str(py), "mlx-speech"],
        capture_output=True,
        text=True,
    )
    if pip.returncode != 0:
        detail = (pip.stderr or pip.stdout or "").strip()
        raise RuntimeError(
            "Failed to install mlx-speech into the Step-Audio-EditX sidecar venv. "
            f"{detail[:500]}"
        )

    probe = subprocess.run(
        [str(py), "-c", "import mlx_speech"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout or "").strip()
        raise RuntimeError(f"mlx-speech import failed in sidecar: {detail[:400]}")

    marker.write_text("ok\n", encoding="utf-8")
    return py


def _edit_pcm_mlx(
    mono: np.ndarray,
    *,
    sample_rate: int,
    prompt_text: str,
    edit_type: str,
    edit_info: str,
    target_text: str,
) -> np.ndarray:
    py = _ensure_mlx_python()
    with tempfile.TemporaryDirectory(prefix="groovy-step-editx-mlx-") as tmp:
        tmp_path = Path(tmp)
        prompt_wav = tmp_path / "prompt.wav"
        out_wav = tmp_path / "out.wav"
        out_meta = tmp_path / "out.json"
        payload_path = tmp_path / "payload.json"
        sf.write(str(prompt_wav), mono, int(sample_rate))
        payload = {
            "model_alias": MLX_MODEL_ALIAS,
            "prompt_wav": str(prompt_wav),
            "prompt_text": prompt_text,
            "edit_type": edit_type,
            "edit_info": edit_info,
            "target_text": target_text,
            "out_wav": str(out_wav),
            "out_meta": str(out_meta),
        }
        payload_path.write_text(json.dumps(payload), encoding="utf-8")
        # First run downloads ~4 GB MLX weights from Hugging Face.
        env = {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
            "TQDM_DISABLE": "1",
        }
        proc = subprocess.run(
            [str(py), "-c", _MLX_WORKER, str(payload_path)],
            capture_output=True,
            text=True,
            env=env,
        )
        if proc.returncode != 0 or not out_wav.is_file():
            detail = _summarize_worker_error(proc.stdout, proc.stderr)
            raise RuntimeError(f"Step-Audio-EditX MLX inference failed. {detail}")
        wav, native_sr = sf.read(str(out_wav), always_2d=False)
        mono_out = np.asarray(wav, dtype=np.float64)
        if mono_out.ndim > 1:
            mono_out = mono_out.mean(axis=1)
        return _resample_peak(mono_out, native_sr=int(native_sr), sample_rate=sample_rate)


def _ensure_repo(root: Path) -> Path:
    repo = root / "Step-Audio-EditX"
    markers = (
        repo / "tts.py",
        repo / "tokenizer.py",
        repo / "model_loader.py",
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
                f"Could not clone Step-Audio-EditX from {REPO_URL}: {detail[:400]}\n"
                f"Clone manually into {repo} or set GROOVY_STEP_AUDIO_EDITX_ROOT."
            )

    if not _complete():
        missing = [str(path.relative_to(repo)) for path in markers if not path.is_file()]
        raise RuntimeError(
            "Step-Audio-EditX repo clone incomplete "
            f"(missing {', '.join(missing)}). "
            f"Clone {REPO_URL} into {repo} or set GROOVY_STEP_AUDIO_EDITX_ROOT."
        )
    return repo


def _ensure_weights(root: Path) -> tuple[Path, Path]:
    editx_dir = root / "Step-Audio-EditX-weights"
    tok_dir = root / "Step-Audio-Tokenizer"

    def _has_config(path: Path) -> bool:
        if (path / "config.json").is_file():
            return True
        snaps = path / "snapshots"
        if snaps.is_dir():
            return any((p / "config.json").is_file() for p in snaps.iterdir() if p.is_dir())
        return False

    if _has_config(editx_dir) and _has_config(tok_dir):
        return editx_dir, tok_dir

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is required to download Step-Audio-EditX weights. "
            "Install step-audio-editx from Model Browser (Cmd+K)."
        ) from exc

    root.mkdir(parents=True, exist_ok=True)
    if not _has_config(editx_dir):
        snapshot_download(repo_id=HF_EDITX, local_dir=str(editx_dir))
    if not _has_config(tok_dir):
        snapshot_download(repo_id=HF_TOKENIZER, local_dir=str(tok_dir))
    return editx_dir, tok_dir


def _resolve_snapshot(path: Path) -> str:
    if (path / "config.json").is_file():
        return str(path)
    snaps = path / "snapshots"
    if snaps.is_dir():
        for child in sorted(snaps.iterdir(), reverse=True):
            if child.is_dir() and (child / "config.json").is_file():
                return str(child)
    return str(path)


@lru_cache(maxsize=1)
def _load_cuda_pipeline():
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            "Step-Audio-EditX CUDA path needs an NVIDIA GPU + vLLM (upstream Linux). "
            "On Apple Silicon, the MLX path should have been used instead."
        )
    try:
        import vllm  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Step-Audio-EditX needs vLLM for CUDA inference. "
            "On a CUDA Linux host: uv pip install vllm "
            "(see stepfun-ai/Step-Audio-EditX README)."
        ) from exc

    root = _model_root()
    repo = _ensure_repo(root)
    editx_dir, tok_dir = _ensure_weights(root)
    editx_path = _resolve_snapshot(editx_dir)
    tok_path = _resolve_snapshot(tok_dir)

    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    from tokenizer import StepAudioTokenizer  # type: ignore
    from tts import StepAudioTTS  # type: ignore

    tokenizer = StepAudioTokenizer(tok_path, model_source="local")
    return StepAudioTTS(
        editx_path,
        tokenizer,
        model_source="local",
        enforce_eager=True,
        gpu_memory_utilization=0.5,
        max_num_seqs=1,
        cosyvoice_dtype="bfloat16",
        cosyvoice_cuda_graph=False,
    )


def _edit_pcm_cuda(
    mono: np.ndarray,
    *,
    sample_rate: int,
    prompt_text: str,
    edit_type: str,
    edit_info: str,
    target_text: str,
) -> np.ndarray:
    model = _load_cuda_pipeline()
    with tempfile.TemporaryDirectory(prefix="groovy-step-editx-") as tmp:
        wav_path = Path(tmp) / "prompt.wav"
        sf.write(str(wav_path), mono, int(sample_rate))

        if edit_type == "clone":
            target = (target_text or prompt_text).strip()
            if not target:
                raise RuntimeError("clone edit_type needs target_text (or prompt_text).")
            out_audio, native_sr = model.clone(
                prompt_wav_path=str(wav_path),
                prompt_text=prompt_text,
                target_text=target,
            )
        else:
            out_audio, native_sr = model.edit(
                prompt_wav_path=str(wav_path),
                prompt_text=prompt_text,
                edit_type=edit_type,
                edit_info=edit_info or None,
                target_text=(target_text or None) or None,
            )

    if hasattr(out_audio, "detach"):
        out_np = out_audio.detach().cpu().float().numpy()
    else:
        out_np = np.asarray(out_audio, dtype=np.float64)
    if out_np.ndim > 1:
        if out_np.shape[0] <= 8:
            out_np = out_np.mean(axis=0)
        else:
            out_np = out_np.mean(axis=-1)
    mono_out = np.asarray(out_np, dtype=np.float64).reshape(-1)
    return _resample_peak(mono_out, native_sr=int(native_sr or NATIVE_SAMPLE_RATE), sample_rate=sample_rate)


def _resample_peak(mono_out: np.ndarray, *, native_sr: int, sample_rate: int) -> np.ndarray:
    if sample_rate != native_sr:
        from scipy import signal

        mono_out = signal.resample(mono_out, int(len(mono_out) * sample_rate / native_sr))
    peak_out = float(np.max(np.abs(mono_out))) if mono_out.size else 0.0
    if peak_out > 1e-8:
        mono_out = mono_out / peak_out * 0.9
    return mono_out.reshape(1, -1)


def edit_pcm(
    pcm: np.ndarray,
    *,
    sample_rate: int,
    prompt_text: str,
    edit_type: str = "emotion",
    edit_info: str = "happy",
    target_text: str = "",
) -> np.ndarray:
    """Edit speech PCM with Step-Audio-EditX. Returns planar float64 at ``sample_rate``."""
    mono = pcm.astype(np.float64)
    if mono.ndim > 1:
        mono = mono.mean(axis=0)
    if mono.size == 0:
        raise RuntimeError("Step-Audio-EditX requires non-empty audio")

    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    if peak > 1e-8:
        mono = mono / peak * 0.9

    edit_type_norm, edit_info_norm = normalize_edit_params(edit_type, edit_info)
    prompt = (prompt_text or "").strip()
    if edit_type_norm in {"emotion", "style", "speed", "paralinguistic", "clone"} and not prompt:
        raise RuntimeError(
            "Step-Audio-EditX needs prompt_text (transcript of the input audio) "
            f"for edit_type={edit_type_norm!r}."
        )

    if apple_silicon():
        return _edit_pcm_mlx(
            mono,
            sample_rate=sample_rate,
            prompt_text=prompt,
            edit_type=edit_type_norm,
            edit_info=edit_info_norm,
            target_text=(target_text or "").strip(),
        )

    try:
        import torch

        has_cuda = bool(torch.cuda.is_available())
    except ImportError:
        has_cuda = False

    if not has_cuda:
        raise RuntimeError(
            "Step-Audio-EditX real inference needs either Apple Silicon (MLX / mlx-speech) "
            "or an NVIDIA CUDA GPU + vLLM (upstream Linux). This machine has neither. "
            "Set Settings → Inference = Stub for demos/CI, or run on Apple Silicon / a CUDA host."
        )

    return _edit_pcm_cuda(
        mono,
        sample_rate=sample_rate,
        prompt_text=prompt,
        edit_type=edit_type_norm,
        edit_info=edit_info_norm,
        target_text=(target_text or "").strip(),
    )
