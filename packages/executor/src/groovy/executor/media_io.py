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


def probe_video_dimensions(path: Path) -> tuple[int, int] | None:
    """Return (width, height) for the first video stream, or None if unavailable."""
    if not path.is_file() or not ffprobe_available():
        return None
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
        return None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    for stream in payload.get("streams") or []:
        if stream.get("codec_type") != "video":
            continue
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        if width > 0 and height > 0:
            # Honor display rotation when present (90/270 swap axes).
            rotate = str(stream.get("tags", {}).get("rotate") or "")
            side_data = stream.get("side_data_list") or []
            for entry in side_data:
                if "rotation" in entry:
                    rotate = str(entry.get("rotation") or rotate)
            try:
                angle = abs(int(float(rotate))) % 180
            except (TypeError, ValueError):
                angle = 0
            if angle in (90, 270):
                return height, width
            return width, height
    return None


def mux_video_with_audio(
    video_path: Path,
    pcm: np.ndarray,
    sample_rate: int,
    dest: Path,
) -> Path:
    """Replace / attach audio on a video file; copy video stream, AAC audio → ``dest`` (mp4)."""
    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")
    dest = dest.with_suffix(".mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        tmp_wav = Path(handle.name)
    try:
        interleaved = pcm.T if pcm.ndim == 2 else pcm.reshape(-1, 1)
        sf.write(tmp_wav, interleaved, sample_rate, format="WAV", subtype="PCM_16")
        _run_ffmpeg(
            [
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(tmp_wav),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(dest),
            ]
        )
    finally:
        tmp_wav.unlink(missing_ok=True)
    return dest


def strip_audio_from_video(video_path: Path, dest: Path) -> Path:
    """Copy the video stream only into a silent mp4 (no audio track)."""
    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")
    dest = dest.with_suffix(".mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-map",
            "0:v:0",
            "-c:v",
            "copy",
            "-an",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
    return dest


def probe_video_duration_seconds(path: Path) -> float | None:
    """Best-effort duration from ffprobe (format, else video stream)."""
    if not ffprobe_available() or not path.is_file():
        return None
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
        return None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    duration = float((payload.get("format") or {}).get("duration") or 0.0)
    if duration > 0:
        return duration
    for stream in payload.get("streams") or []:
        if stream.get("codec_type") != "video":
            continue
        try:
            stream_dur = float(stream.get("duration") or 0.0)
        except (TypeError, ValueError):
            stream_dur = 0.0
        if stream_dur > 0:
            return stream_dur
    return None


def _mac_demo_font() -> Path | None:
    for candidate in (
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
    ):
        if candidate.is_file():
            return candidate
    return None


def _ffmpeg_drawtext_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "%%")
    )


def read_video_gray_frames(
    path: Path,
    *,
    width: int,
    height: int,
    max_frames: int,
    fps: float | None = None,
) -> np.ndarray:
    """Decode up to ``max_frames`` grayscale frames via ffmpeg → ``(N, H, W)`` float64 0..1."""
    if not path.is_file():
        raise FileNotFoundError(f"Video not found: {path}")
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg is required to decode VIDEO for ScanProcessor.")
    w = max(16, int(width) - (int(width) % 2))
    h = max(16, int(height) - (int(height) % 2))
    n = max(1, int(max_frames))
    vf_parts = [f"scale={w}:{h}:flags=lanczos", "format=gray"]
    if fps is not None and float(fps) > 0:
        vf_parts.insert(0, f"fps={float(fps)}")
    vf = ",".join(vf_parts)
    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-vf",
            vf,
            "-frames:v",
            str(n),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None
    try:
        raw, stderr = proc.communicate(timeout=max(60.0, n * 0.25))
    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError("ffmpeg timed out decoding VIDEO frames") from None
    if proc.returncode != 0:
        detail = (stderr or b"ffmpeg failed").decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail[:500])
    frame_bytes = w * h
    if frame_bytes <= 0 or len(raw) < frame_bytes:
        raise RuntimeError(f"No video frames decoded from {path.name}")
    usable = (len(raw) // frame_bytes) * frame_bytes
    arr = np.frombuffer(raw[:usable], dtype=np.uint8)
    frames = arr.reshape(-1, h, w).astype(np.float64) / 255.0
    return frames


def extract_video_frame_png(
    video_path: Path,
    dest: Path,
    *,
    frame_index: int = 0,
) -> Path:
    """Extract a single frame from ``video_path`` to PNG via ffmpeg (for I2V / V2V prep)."""
    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg is required to extract a VIDEO frame (not found on PATH).")
    dest = dest.with_suffix(".png")
    dest.parent.mkdir(parents=True, exist_ok=True)
    idx = max(0, int(frame_index))
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"select=eq(n\\,{idx})",
            "-frames:v",
            "1",
            "-update",
            "1",
            str(dest),
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size < 32:
        detail = (proc.stderr or b"ffmpeg failed").decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail[:500] or f"Failed to extract frame {idx} from {video_path.name}")
    return dest


def write_rgb_frames_to_mp4(
    frames: np.ndarray,
    dest: Path,
    *,
    fps: float = 24.0,
) -> Path:
    """Encode an ``(N, H, W, 3)`` uint8 RGB stack to H.264 mp4 via ffmpeg rawvideo pipe."""
    if frames.ndim != 4 or frames.shape[-1] != 3:
        raise ValueError(f"frames must be (N,H,W,3); got {getattr(frames, 'shape', None)}")
    n_frames, height, width, _ = frames.shape
    if n_frames < 1:
        raise ValueError("frames must contain at least one frame")
    w = int(width) - (int(width) % 2)
    h = int(height) - (int(height) % 2)
    if w < 16 or h < 16:
        raise ValueError(f"frame size too small after even clamp: {w}x{h}")
    if w != width or h != height:
        frames = frames[:, :h, :w, :]
    dest = dest.with_suffix(".mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)
    rate = max(1.0, float(fps))
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg is required to encode ScanProcessor VIDEO (not found on PATH).")
    rgb = np.ascontiguousarray(frames, dtype=np.uint8)
    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{w}x{h}",
            "-r",
            str(rate),
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(dest),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None
    try:
        stdout, stderr = proc.communicate(input=rgb.tobytes(), timeout=max(60.0, n_frames * 0.5))
    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError("ffmpeg timed out encoding RGB frames to mp4") from None
    if proc.returncode != 0:
        detail = (stderr or stdout or b"ffmpeg failed").decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail[:500])
    return dest


def write_color_video(
    dest: Path,
    *,
    duration: float = 2.0,
    width: int = 640,
    height: int = 360,
    color: str = "0x1a1a2e",
    fps: int = 24,
    prompt: str | None = None,
) -> Path:
    """Write a short H.264 mp4 (Mac T2V demo / CI stub).

    This is **not** generative video — a solid plate plus on-screen prompt so the
    GenerateVideo → PreviewVideo path is exercisable without GPU weights.
    """
    dest = dest.with_suffix(".mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)
    seconds = max(0.5, min(float(duration), 30.0))
    w = max(16, int(width) - (int(width) % 2))
    h = max(16, int(height) - (int(height) % 2))
    lavfi = f"color=c={color}:s={w}x{h}:d={seconds}:r={fps}"
    args = ["-y", "-f", "lavfi", "-i", lavfi]
    label = (prompt or "").strip() or "text to video"
    font = _mac_demo_font()
    if font is not None:
        # Escape path for ffmpeg filtergraph (spaces / colons).
        font_esc = str(font).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        shown = label if len(label) <= 64 else f"{label[:63]}…"
        title_size = max(13, min(22, w // 28))
        body_size = max(12, min(26, w // 22))
        # Two lines: clear "demo" banner + user prompt (not a greenscreen glitch).
        draw = (
            f"drawtext=fontfile={font_esc}:"
            f"text='{_ffmpeg_drawtext_escape('Mac demo · not generative LTX')}':"
            f"fontsize={title_size}:fontcolor=white:x=(w-text_w)/2:y=h*0.28:"
            f"box=1:boxcolor=black@0.55:boxborderw=8,"
            f"drawtext=fontfile={font_esc}:"
            f"text='{_ffmpeg_drawtext_escape(shown)}':"
            f"fontsize={body_size}:fontcolor=white:x=(w-text_w)/2:y=h*0.52:"
            f"box=1:boxcolor=black@0.55:boxborderw=10"
        )
        args.extend(["-vf", draw])
    args.extend(
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
    _run_ffmpeg(args)
    return dest


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
