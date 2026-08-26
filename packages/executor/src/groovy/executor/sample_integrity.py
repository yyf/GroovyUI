"""Offline PCM sample-buffer integrity checks (content hash + frame clock)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class SampleCheckReport:
    """Standalone sample-integrity report (not an AuthenticityReport)."""

    id: str
    record: dict[str, Any] = field(default_factory=dict)
    socket_type: str = "SAMPLE_CHECK"

    def to_meta(self) -> dict[str, Any]:
        return {"id": self.id, "type": "SAMPLE_CHECK", **self.record}

    @classmethod
    def create(cls, record: dict[str, Any]) -> SampleCheckReport:
        report_id = str(uuid.uuid4())
        record = {
            "schema_version": "1.0.0",
            "cache_id": report_id,
            "evaluated_at": datetime.now(UTC).isoformat(),
            **record,
        }
        return cls(id=report_id, record=record)


def pcm_content_hash(pcm: Any) -> str:
    import numpy as np

    arr = np.asarray(pcm, dtype=np.float64)
    return f"sha256:{hashlib.sha256(arr.tobytes()).hexdigest()}"


def verify_samples_for_audio(cache: Any, audio_id: str) -> dict[str, Any]:
    """Recompute PCM hash and report sample-accurate cache fields.

    Used by the VerifySamples node and inspector sample checks. Does not claim
    bit-identical AI across machines — only that this offline cache buffer is
    intact relative to its declared content_hash.
    """
    meta = cache.read_meta(audio_id)
    buffer, pcm = cache.load_audio(audio_id)
    recomputed = pcm_content_hash(pcm)
    declared = meta.get("content_hash") or getattr(buffer, "content_hash", None)
    hash_match = bool(declared) and declared == recomputed
    sample_rate = int(meta.get("sample_rate") or buffer.sample_rate or 0)
    frame_count = int(meta.get("frame_count") or buffer.frame_count or 0)
    channels = int(meta.get("channels") or buffer.channels or 0)
    channel_layout = str(meta.get("channel_layout") or buffer.channel_layout or "mono")
    duration_sec = (frame_count / sample_rate) if sample_rate > 0 else 0.0
    source_node_type = meta.get("source_node_type") or getattr(buffer, "source_node_type", None)
    ok = hash_match and frame_count > 0 and sample_rate > 0 and channels > 0
    if not declared:
        label = "incomplete"
        summary = "Cache has no declared content_hash; recomputed from PCM."
    elif hash_match:
        label = "match"
        summary = "PCM content hash matches declared cache meta (offline sample buffer intact)."
    else:
        label = "mismatch"
        summary = "PCM content hash does not match declared cache meta."
    return {
        "ok": ok,
        "label": label,
        "summary": summary,
        "cache_id": audio_id,
        "content_hash": declared,
        "recomputed_hash": recomputed,
        "hash_match": hash_match,
        "sample_rate": sample_rate,
        "frame_count": frame_count,
        "sample_count": frame_count,
        "channels": channels,
        "channel_layout": channel_layout,
        "duration_sec": round(duration_sec, 6),
        "source_node_type": source_node_type,
        "dtype": meta.get("dtype") or getattr(buffer, "dtype", None),
        "layout": meta.get("layout") or getattr(buffer, "layout", None),
    }


def sample_pair_check(meta_a: dict[str, Any], meta_b: dict[str, Any]) -> dict[str, Any]:
    """Compare two cache metas for A/B sample identity (hash / clock / layout)."""
    hash_a = meta_a.get("content_hash")
    hash_b = meta_b.get("content_hash")
    same_hash = bool(hash_a) and hash_a == hash_b
    same_sr = int(meta_a.get("sample_rate") or 0) == int(meta_b.get("sample_rate") or 0)
    same_frames = int(meta_a.get("frame_count") or 0) == int(meta_b.get("frame_count") or 0)
    same_layout = str(meta_a.get("channel_layout") or "") == str(meta_b.get("channel_layout") or "")
    if same_hash and same_sr and same_frames and same_layout:
        label = "identical"
        summary = "A and B share the same content hash, sample rate, frame count, and layout."
    elif same_sr and same_layout and not same_hash:
        label = "same_clock_different_pcm"
        summary = "Same sample rate and layout, different PCM content hash."
    elif not same_sr or not same_layout:
        label = "format_mismatch"
        summary = "Sample rate and/or channel layout differ between A and B."
    else:
        label = "different"
        summary = "Buffers differ (hash and/or frame count)."
    return {
        "label": label,
        "summary": summary,
        "same_content_hash": same_hash,
        "same_sample_rate": same_sr,
        "same_frame_count": same_frames,
        "same_channel_layout": same_layout,
        "content_hash_a": hash_a,
        "content_hash_b": hash_b,
        "frame_count_a": meta_a.get("frame_count"),
        "frame_count_b": meta_b.get("frame_count"),
        "sample_rate_a": meta_a.get("sample_rate"),
        "sample_rate_b": meta_b.get("sample_rate"),
        "channel_layout_a": meta_a.get("channel_layout"),
        "channel_layout_b": meta_b.get("channel_layout"),
    }
