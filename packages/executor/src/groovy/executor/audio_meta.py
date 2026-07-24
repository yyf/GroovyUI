from __future__ import annotations

import math
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import soundfile as sf

if TYPE_CHECKING:
    from groovy.executor.audio import AudioBuffer

STANDARD_CHANNEL_MAPS: dict[str, list[str]] = {
    "mono": ["M"],
    "stereo": ["FL", "FR"],
    "LRC": ["L", "C", "R"],
    "quad": ["FL", "FR", "BL", "BR"],
    "5.1": ["FL", "FR", "FC", "LFE", "BL", "BR"],
    "7.1": ["FL", "FR", "FC", "LFE", "BL", "BR", "SL", "SR"],
    "7.1.4": ["FL", "FR", "FC", "LFE", "BL", "BR", "SL", "SR", "TFL", "TFR", "TBL", "TBR"],
}


def ambisonic_order(channels: int) -> int | None:
    if channels < 4:
        return None
    order = int(round(math.sqrt(channels))) - 1
    if order >= 0 and (order + 1) ** 2 == channels:
        return order
    return None


def channel_layout_for_channels(channels: int) -> str:
    if channels == 1:
        return "mono"
    if channels == 2:
        return "stereo"
    if channels == 3:
        return "LRC"
    if channels == 4:
        return "quad"
    if channels == 6:
        return "5.1"
    if channels == 8:
        return "7.1"
    if channels == 12:
        return "7.1.4"
    if ambisonic_order(channels) is not None:
        return "ambisonics"
    return "custom"


def channel_map_for_layout(layout: str, channels: int) -> list[str]:
    mapped = STANDARD_CHANNEL_MAPS.get(layout)
    if mapped and len(mapped) == channels:
        return list(mapped)
    return [f"ch{i}" for i in range(channels)]


def _collect_text_hints(path: Path, comments: str | None, extra_info: Any) -> str:
    parts = [comments or ""]
    if isinstance(extra_info, dict):
        parts.extend(str(value) for value in extra_info.values())
    try:
        head = path.read_bytes()[:65536]
        parts.append(head.decode("utf-8", errors="ignore"))
    except OSError:
        pass
    return " ".join(parts).lower()


def _detect_adm_bwf(text: str) -> bool:
    return "audioformatextended" in text or ("<axml" in text and "adm" in text)


def _detect_ambisonics(text: str) -> bool:
    markers = ("ambisonic", "ambi", "ambiorder", "ambiorder", "sn3d", "n3d", "acn", "ambix")
    return any(marker in text for marker in markers)


def _encoding_scheme(
    *,
    channels: int,
    channel_layout: str,
    text: str,
    order: int | None,
) -> str | None:
    if _detect_adm_bwf(text):
        return "ADM BWF (EBU Tech 3369)"
    if order is not None and (_detect_ambisonics(text) or channel_layout == "ambisonics"):
        if order == 1:
            return "FOA AmbiX (ACN/SN3D)"
        return f"HOA order {order} AmbiX (ACN/SN3D)"
    if channel_layout == "7.1.4":
        return "Dolby Atmos 7.1.4 bed"
    if channel_layout == "7.1":
        return "7.1 surround"
    if channel_layout == "5.1":
        return "5.1 surround"
    if channel_layout == "quad":
        if order == 1:
            return "FOA AmbiX (ACN/SN3D)"
        return "Quad surround"
    if channel_layout == "binaural":
        return "Binaural (HRTF stereo)"
    if channels > 2:
        return f"{channels}-channel ({channel_layout})"
    return None


def probe_audio_file(path: Path) -> dict[str, Any]:
    """Read container/codec and infer multichannel layout metadata from a file on disk."""
    from groovy.executor.media_io import probe_with_ffmpeg, requires_ffmpeg_read

    try:
        info = sf.info(path)
    except Exception:
        if not requires_ffmpeg_read(path):
            raise
        ffmpeg_meta = probe_with_ffmpeg(path)
        channels = int(ffmpeg_meta["channels"])
        channel_layout = channel_layout_for_channels(channels)
        return {
            "channels": channels,
            "sample_rate": int(ffmpeg_meta["sample_rate"]),
            "duration_seconds": float(ffmpeg_meta["duration_seconds"]),
            "channel_layout": channel_layout,
            "channel_map": channel_map_for_layout(channel_layout, channels),
            "layout_order": None,
            "encoding_scheme": None,
            "file_format": ffmpeg_meta["file_format"],
            "file_subtype": ffmpeg_meta["file_subtype"],
            "spatial_meta": {
                "source_path": str(path),
                "file_format": ffmpeg_meta["file_format"],
                "file_subtype": ffmpeg_meta["file_subtype"],
                "audio_stream_count": ffmpeg_meta.get("audio_stream_count", 1),
                "decode_backend": "ffmpeg",
            },
        }

    comments: str | None = None
    extra_info: Any = None
    try:
        with sf.SoundFile(path) as handle:
            comments = getattr(handle, "comments", None)
            extra_info = getattr(handle, "extra_info", None)
    except Exception:
        comments = None
        extra_info = None

    channels = int(info.channels)
    channel_layout = channel_layout_for_channels(channels)
    order = ambisonic_order(channels)
    text = _collect_text_hints(path, comments, extra_info)

    if order == 1 and channels == 4 and (_detect_ambisonics(text) or "ambi" in path.name.lower()):
        channel_layout = "ambisonics"
    elif order is not None and _detect_ambisonics(text):
        channel_layout = "ambisonics"

    encoding_scheme = _encoding_scheme(
        channels=channels,
        channel_layout=channel_layout,
        text=text,
        order=order,
    )

    spatial_meta: dict[str, Any] = {
        "source_path": str(path),
        "file_format": info.format,
        "file_subtype": info.subtype,
    }
    if order is not None and channel_layout == "ambisonics":
        spatial_meta["channel_ordering"] = "ACN"
        spatial_meta["normalization"] = "SN3D" if "sn3d" in text or "n3d" not in text else "N3D"
        spatial_meta["layout_order"] = order
    if _detect_adm_bwf(text):
        spatial_meta["container"] = "ADM BWF"
        version = re.search(r"adm[^0-9]*(\d+\.\d+\.\d+)", text)
        if version:
            spatial_meta["adm_version"] = version.group(1)

    return {
        "channels": channels,
        "sample_rate": int(info.samplerate),
        "duration_seconds": float(info.duration),
        "channel_layout": channel_layout,
        "channel_map": channel_map_for_layout(channel_layout, channels),
        "layout_order": order if channel_layout == "ambisonics" else None,
        "encoding_scheme": encoding_scheme,
        "file_format": info.format,
        "file_subtype": info.subtype,
        "spatial_meta": spatial_meta,
    }


def apply_file_probe(buffer: AudioBuffer, probe: dict[str, Any]) -> None:
    buffer.channel_layout = str(probe.get("channel_layout", buffer.channel_layout))
    buffer.channel_map = list(probe.get("channel_map") or channel_map_for_layout(buffer.channel_layout, buffer.channels))
    buffer.layout_order = probe.get("layout_order")
    buffer.encoding_scheme = probe.get("encoding_scheme")
    buffer.file_format = probe.get("file_format")
    buffer.file_subtype = probe.get("file_subtype")
    buffer.spatial_meta = dict(probe.get("spatial_meta") or {})


def inherit_format_meta(target: AudioBuffer, parent: AudioBuffer, **overrides: Any) -> None:
    target.layout_order = overrides.get("layout_order", parent.layout_order)
    target.encoding_scheme = overrides.get("encoding_scheme", parent.encoding_scheme)
    target.file_format = overrides.get("file_format", parent.file_format)
    target.file_subtype = overrides.get("file_subtype", parent.file_subtype)
    target.spatial_meta = dict(overrides.get("spatial_meta", parent.spatial_meta))
    if "channel_map" in overrides:
        target.channel_map = list(overrides["channel_map"])
    elif parent.channel_map:
        target.channel_map = list(parent.channel_map)
