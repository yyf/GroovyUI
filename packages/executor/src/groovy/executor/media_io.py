from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

# Containers / codecs that libsndfile typically cannot open; decode via ffmpeg.
FFMPEG_READ_SUFFIXES = frozenset(
    {
        ".mp4",
        ".m4a",
        ".aac",
        ".mp3",
        ".ogg",
        ".opus",
        ".mov",
        ".webm",
    }
)
FFMPEG_WRITE_FORMATS = frozenset({"mp4", "m4a", "aac", "mp3"})


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def requires_ffmpeg_read(path: Path) -> bool:
    return path.suffix.lower() in FFMPEG_READ_SUFFIXES


def write_uses_ffmpeg(format_name: str) -> bool:
    return format_name.strip().lower() in FFMPEG_WRITE_FORMATS


def _run_ffmpeg(args: list[str]) -> None:
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg is required for this media format (not found on PATH).")
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "ffmpeg failed").strip()
        raise RuntimeError(detail[:500])


def count_audio_streams(path: Path) -> int:
    if not ffprobe_available():
        return 1
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 1
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return 1
    streams = payload.get("streams") or []
    return max(1, sum(1 for stream in streams if stream.get("codec_type") == "audio"))


def default_audio_stream_index(path: Path) -> int:
    """OpenSTEM `.stem.mp4` stores the full mix as audio stream 0."""
    return 0


def read_audio_pcm(
    path: Path,
    *,
    stream_index: int | None = None,
) -> tuple[np.ndarray, int]:
    """Load audio as planar float64 ``(channels, frames)`` and sample rate.

    Tries libsndfile first. Falls back to ffmpeg for compressed containers
    (MP4 / M4A / AAC / MP3 / …). For multi-stream OpenSTEM files, ``stream_index``
    selects which audio stream to decode (0 = mix).
    """
    suffix = path.suffix.lower()
    prefer_ffmpeg = requires_ffmpeg_read(path)
    if not prefer_ffmpeg:
        try:
            interleaved, sample_rate = sf.read(path, dtype="float64", always_2d=True)
            return interleaved.T, int(sample_rate)
        except Exception:
            if suffix not in FFMPEG_READ_SUFFIXES:
                raise

    index = default_audio_stream_index(path) if stream_index is None else int(stream_index)
    return _read_via_ffmpeg(path, stream_index=index)


def _read_via_ffmpeg(path: Path, *, stream_index: int) -> tuple[np.ndarray, int]:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        tmp_path = Path(handle.name)
    try:
        _run_ffmpeg(
            [
                "-y",
                "-i",
                str(path),
                "-map",
                f"0:a:{stream_index}",
                "-vn",
                str(tmp_path),
            ]
        )
        interleaved, sample_rate = sf.read(tmp_path, dtype="float64", always_2d=True)
        return interleaved.T, int(sample_rate)
    except Exception as exc:
        raise RuntimeError(
            f"Could not decode audio from {path.name} (stream {stream_index}): {exc}"
        ) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


def write_audio_ffmpeg(
    dest: Path,
    pcm: np.ndarray,
    sample_rate: int,
    *,
    format_name: str,
) -> None:
    """Encode planar float PCM to a compressed container via ffmpeg."""
    fmt = format_name.strip().lower()
    if fmt not in FFMPEG_WRITE_FORMATS:
        raise ValueError(f"Unsupported ffmpeg export format: {format_name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        tmp_path = Path(handle.name)
    try:
        interleaved = pcm.T if pcm.ndim == 2 else pcm.reshape(-1, 1)
        sf.write(tmp_path, interleaved, sample_rate, format="WAV", subtype="PCM_16")
        if fmt == "mp3":
            codec_args = ["-c:a", "libmp3lame", "-b:a", "192k"]
        else:
            # mp4 / m4a / aac → AAC in MP4-family container
            codec_args = ["-c:a", "aac", "-b:a", "192k"]
        _run_ffmpeg(["-y", "-i", str(tmp_path), *codec_args, str(dest)])
    finally:
        tmp_path.unlink(missing_ok=True)


def probe_with_ffmpeg(path: Path) -> dict[str, Any]:
    """Minimal probe for ffmpeg-only containers (channels, rate, duration)."""
    from typing import Any

    if not ffprobe_available():
        raise RuntimeError("ffprobe is required to inspect this media format.")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "ffprobe failed").strip()
        raise RuntimeError(detail[:500])
    payload = json.loads(result.stdout or "{}")
    audio_streams = [
        stream
        for stream in (payload.get("streams") or [])
        if stream.get("codec_type") == "audio"
    ]
    if not audio_streams:
        raise RuntimeError(f"No audio stream in {path.name}")
    stream = audio_streams[0]
    channels = int(stream.get("channels") or 2)
    sample_rate = int(float(stream.get("sample_rate") or 44100))
    duration = float((payload.get("format") or {}).get("duration") or stream.get("duration") or 0.0)
    codec = str(stream.get("codec_name") or "unknown")
    return {
        "channels": channels,
        "sample_rate": sample_rate,
        "duration_seconds": duration,
        "file_format": path.suffix.lstrip(".").upper() or "FFMPEG",
        "file_subtype": codec.upper(),
        "audio_stream_count": len(audio_streams),
    }
