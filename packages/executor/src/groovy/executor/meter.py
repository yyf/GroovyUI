"""Offline multi-channel level metering for Meter node / Inspector."""

from __future__ import annotations

from typing import Any

import numpy as np

# Common layout labels (index → name). Unknown counts fall back to ch0, ch1, …
_LAYOUT_LABELS: dict[str, list[str]] = {
    "mono": ["M"],
    "stereo": ["L", "R"],
    "lrc": ["L", "R", "C"],
    "quad": ["FL", "FR", "BL", "BR"],
    "5.1": ["L", "R", "C", "LFE", "Ls", "Rs"],
    "7.1": ["L", "R", "C", "LFE", "Lss", "Rss", "Lrs", "Rrs"],
    "7.1.4": ["L", "R", "C", "LFE", "Lss", "Rss", "Lrs", "Rrs", "Ltf", "Rtf", "Ltr", "Rtr"],
    # AmbiX ACN (SN3D): W Y Z X …
    "foa": ["W", "Y", "Z", "X"],
    "hoa1": ["W", "Y", "Z", "X"],
    "hoa2": ["W", "Y", "Z", "X", "V", "T", "R", "S", "U"],
    "hoa3": [
        "W",
        "Y",
        "Z",
        "X",
        "V",
        "T",
        "R",
        "S",
        "U",
        "Q",
        "O",
        "M",
        "K",
        "L",
        "N",
        "P",
    ],
}


def ambisonic_channel_labels(layout_order: int, channel_count: int) -> list[str]:
    """ACN channel names for FOA/HOA; fall back to ACN0… for unknown orders."""
    order = max(0, int(layout_order))
    key = f"hoa{order}" if order > 1 else "foa"
    labels = list(_LAYOUT_LABELS.get(key, []))
    if len(labels) >= channel_count:
        return labels[:channel_count]
    if labels:
        return labels + [f"ACN{i}" for i in range(len(labels), channel_count)]
    return [f"ACN{i}" for i in range(channel_count)]


def channel_labels_for_layout(layout: str, channel_count: int) -> list[str]:
    key = str(layout or "auto").strip().lower()
    if key in {"", "auto"}:
        if channel_count == 1:
            return ["M"]
        if channel_count == 2:
            return ["L", "R"]
        return [f"ch{i}" for i in range(channel_count)]
    if key.startswith("hoa") or key == "foa":
        order = 1
        if key.startswith("hoa"):
            try:
                order = int(key.replace("hoa", "") or "1")
            except ValueError:
                order = 1
        return ambisonic_channel_labels(order, channel_count)
    labels = list(_LAYOUT_LABELS.get(key, []))
    if len(labels) >= channel_count:
        return labels[:channel_count]
    if labels:
        return labels + [f"ch{i}" for i in range(len(labels), channel_count)]
    return [f"ch{i}" for i in range(channel_count)]


def resolve_meter_layout(
    *,
    layout_widget: str = "auto",
    channel_count: int,
    channel_layout: str | None = None,
    spatial_meta: dict[str, Any] | None = None,
    layout_order: int | None = None,
) -> str:
    """Pick a label layout from widget override, then inlet metadata, then channel count."""
    key = str(layout_widget or "auto").strip().lower()
    if key not in {"", "auto"}:
        return key

    meta = dict(spatial_meta or {})
    order = layout_order
    if order is None:
        raw = meta.get("layout_order", meta.get("ambisonic_order"))
        if raw is not None:
            try:
                order = int(raw)
            except (TypeError, ValueError):
                order = None
    if order is not None:
        return "foa" if int(order) <= 1 else f"hoa{int(order)}"

    layout_name = str(channel_layout or meta.get("channel_layout") or "").strip().lower()
    if layout_name in _LAYOUT_LABELS:
        return layout_name
    if layout_name in {"ambisonics", "ambi", "foa", "b-format", "bformat"}:
        if channel_count == 4:
            return "foa"
        expected = int(round(channel_count**0.5)) - 1
        if expected >= 1 and (expected + 1) ** 2 == channel_count:
            return f"hoa{expected}"
        return "foa" if channel_count == 4 else "auto"

    if channel_count == 1:
        return "mono"
    if channel_count == 2:
        return "stereo"
    if channel_count == 4:
        encoding = str(meta.get("encoding_scheme") or meta.get("channel_ordering") or "").lower()
        if "ambi" in encoding or "acn" in encoding or "foa" in encoding:
            return "foa"
    return "auto"


def _dbfs(linear: float) -> float:
    if linear <= 0.0:
        return float("-inf")
    return float(20.0 * np.log10(linear))


def measure_channel_levels(
    pcm: np.ndarray,
    *,
    layout: str = "auto",
    edge_fraction: float = 0.05,
    channel_layout: str | None = None,
    spatial_meta: dict[str, Any] | None = None,
    layout_order: int | None = None,
) -> dict[str, Any]:
    """Per-channel peak/RMS (full clip + head/tail windows).

    ``pcm`` is planar (channels, frames). Layout defaults to **auto** (infer from
    channel count + inlet metadata such as ambisonic order).
    """
    if pcm.ndim == 1:
        pcm = pcm.reshape(1, -1)
    channels, frames = pcm.shape
    effective = resolve_meter_layout(
        layout_widget=layout,
        channel_count=channels,
        channel_layout=channel_layout,
        spatial_meta=spatial_meta,
        layout_order=layout_order,
    )
    labels = channel_labels_for_layout(effective, channels)
    edge = max(1, int(round(frames * max(0.01, min(0.25, float(edge_fraction))))))
    head_end = min(frames, edge)
    tail_start = max(0, frames - edge)

    channel_rows: list[dict[str, Any]] = []
    for i in range(channels):
        row = pcm[i]
        peak = float(np.max(np.abs(row))) if frames else 0.0
        rms = float(np.sqrt(np.mean(row**2))) if frames else 0.0
        head = row[:head_end]
        tail = row[tail_start:]
        peak_head = float(np.max(np.abs(head))) if head.size else 0.0
        peak_tail = float(np.max(np.abs(tail))) if tail.size else 0.0
        rms_head = float(np.sqrt(np.mean(head**2))) if head.size else 0.0
        rms_tail = float(np.sqrt(np.mean(tail**2))) if tail.size else 0.0
        channel_rows.append(
            {
                "index": i,
                "name": labels[i] if i < len(labels) else f"ch{i}",
                "peak": peak,
                "rms": rms,
                "peak_db": _dbfs(peak),
                "rms_db": _dbfs(rms),
                "peak_head": peak_head,
                "peak_tail": peak_tail,
                "peak_db_head": _dbfs(peak_head),
                "peak_db_tail": _dbfs(peak_tail),
                "rms_db_head": _dbfs(rms_head),
                "rms_db_tail": _dbfs(rms_tail),
            }
        )

    return {
        "layout": effective,
        "channel_count": channels,
        "frame_count": frames,
        "edge_fraction": float(edge_fraction),
        "layout_order": layout_order,
        "channels": channel_rows,
    }


def _json_safe_meter(meter: dict[str, Any]) -> dict[str, Any]:
    """Replace ±inf / nan floats so json.dumps(..., allow_nan=False) succeeds."""

    def _num(v: Any) -> Any:
        if isinstance(v, float):
            if np.isneginf(v):
                return None
            if np.isposinf(v) or np.isnan(v):
                return None
        return v

    channels = []
    for ch in meter.get("channels") or []:
        channels.append({k: _num(v) for k, v in dict(ch).items()})
    out = {**meter, "channels": channels}
    return out


def format_meter_summary(meter: dict[str, Any]) -> str:
    """Compact one-line summary for canvas chrome (peak dBFS)."""
    parts: list[str] = []
    for ch in meter.get("channels") or []:
        name = str(ch.get("name") or "?")
        peak_db = ch.get("peak_db")
        if peak_db is None or peak_db == float("-inf"):
            parts.append(f"{name} −∞")
        else:
            parts.append(f"{name} {float(peak_db):+.1f}")
    body = " · ".join(parts) if parts else "—"
    return f"{body} dBFS peak"


def format_meter_debug_lines(meter: dict[str, Any]) -> list[str]:
    """Head/tail peak lines for L/R vs XYZ debugging."""
    lines: list[str] = []
    for ch in meter.get("channels") or []:
        name = str(ch.get("name") or "?")
        head = ch.get("peak_db_head")
        tail = ch.get("peak_db_tail")

        def _fmt(v: Any) -> str:
            if v is None or v == float("-inf"):
                return "−∞"
            return f"{float(v):+.1f}"

        lines.append(f"{name} head {_fmt(head)} · tail {_fmt(tail)}")
    return lines
