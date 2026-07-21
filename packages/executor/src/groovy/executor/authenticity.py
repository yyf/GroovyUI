from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class AuthenticityReport:
    id: str
    record: dict[str, Any] = field(default_factory=dict)

    def to_meta(self) -> dict[str, Any]:
        return {"id": self.id, "type": "AUTHENTICITY", **self.record}

    @classmethod
    def create(cls, record: dict[str, Any]) -> AuthenticityReport:
        report_id = str(uuid.uuid4())
        record = {
            "schema_version": "1.0.0",
            "cache_id": report_id,
            "evaluated_at": datetime.now(UTC).isoformat(),
            **record,
        }
        return cls(id=report_id, record=record)


def verify_provenance_for_audio(
    cache: Any,
    audio_id: str,
    *,
    source_path: str | None = None,
    check_sidecar: bool = True,
) -> dict[str, Any]:
    meta = cache.read_meta(audio_id)
    imported = meta.get("imported_provenance")
    sidecar_record: dict[str, Any] | None = None

    if check_sidecar and source_path:
        resolved = cache.resolve_project_path(source_path)
        sidecar = resolved.with_name(f"{resolved.stem}.provenance.json")
        if sidecar.exists():
            sidecar_record = json.loads(sidecar.read_text())

    provenance = sidecar_record or imported
    if not provenance:
        return {
            "status": "missing",
            "sidecar_found": False,
            "chain_intact": None,
            "contribution_class": "unknown",
            "groovy_origin": False,
        }

    from groovy.executor.provenance import verify_record_integrity

    record_integrity = verify_record_integrity(provenance)
    chain_intact = record_integrity is not False
    artifact_hash = provenance.get("artifact", {}).get("file_hash")
    if artifact_hash and source_path:
        resolved = cache.resolve_project_path(source_path)
        digest = hashlib.sha256()
        with resolved.open("rb") as audio_file:
            for chunk in iter(lambda: audio_file.read(1024 * 1024), b""):
                digest.update(chunk)
        chain_intact = chain_intact and artifact_hash == f"sha256:{digest.hexdigest()}"
    else:
        content_hash = meta.get("content_hash")
        if provenance.get("content_hash") and content_hash:
            chain_intact = chain_intact and provenance.get("content_hash") == content_hash

    contribution = provenance.get("contribution", {})
    return {
        "status": "verified" if chain_intact else "tampered",
        "sidecar_found": sidecar_record is not None,
        "chain_intact": chain_intact,
        "record_integrity": record_integrity,
        "contribution_class": contribution.get("class", "unknown"),
        "groovy_origin": provenance.get("origin", {}).get("type") == "render",
    }


def ml_detection_stub(*, model_id: str, spoof_score: float = 0.35) -> dict[str, Any]:
    bonafide = max(0.0, 1.0 - spoof_score)
    return {
        "model_id": model_id,
        "spoof_score": spoof_score,
        "bonafide_score": bonafide,
        "task": "deepfake-detection",
        "segment_scores": [],
    }


def overall_label(
    provenance_check: dict[str, Any],
    ml_detection: dict[str, Any] | None,
    *,
    spoof_threshold: float = 0.5,
) -> tuple[str, float, str]:
    prov_status = provenance_check.get("status", "missing")
    contribution = provenance_check.get("contribution_class", "unknown")
    spoof = float(ml_detection.get("spoof_score", 0.0)) if ml_detection else 0.0
    bonafide = float(ml_detection.get("bonafide_score", 1.0)) if ml_detection else 1.0

    if prov_status == "tampered":
        return (
            "provenance_tampered",
            0.9,
            "Provenance sidecar present but hash chain verification failed.",
        )
    if contribution in {"ai_generated", "ai_transformed"} and prov_status == "verified":
        return (
            "ai_disclosed",
            0.85,
            "Provenance discloses AI-generated or AI-transformed audio.",
        )
    if spoof >= spoof_threshold:
        return (
            "likely_synthetic",
            spoof,
            f"ML classifier scores {spoof:.0%} spoof probability.",
        )
    if bonafide >= 0.7 and prov_status == "verified" and contribution == "human_recorded":
        return ("verified_bonafide", bonafide, "Provenance and ML both indicate human-recorded audio.")
    if bonafide >= 0.6:
        return ("likely_bonafide", bonafide, "ML classifier indicates likely bonafide speech.")
    if prov_status == "missing" and ml_detection is None:
        return ("unknown", 0.0, "No provenance metadata and no ML analysis available.")
    return ("unknown", 0.5, "Inconclusive authenticity signals.")


def merge_authenticity_reports(
    provenance_report: AuthenticityReport | None,
    ml_report: AuthenticityReport | None,
    *,
    spoof_threshold: float = 0.5,
) -> AuthenticityReport:
    prov_check = (provenance_report.record.get("provenance_check") if provenance_report else None) or {
        "status": "missing",
        "sidecar_found": False,
        "chain_intact": None,
        "contribution_class": "unknown",
        "groovy_origin": False,
    }
    ml_det = ml_report.record.get("ml_detection") if ml_report else None
    label, confidence, summary = overall_label(prov_check, ml_det, spoof_threshold=spoof_threshold)
    signals: list[dict[str, Any]] = []
    if ml_det:
        signals.append(
            {
                "source": "ml_detection",
                "weight": 0.7,
                "label": "likely_synthetic" if ml_det["spoof_score"] >= spoof_threshold else "likely_bonafide",
            }
        )
    signals.append(
        {
            "source": "provenance_check",
            "weight": 0.3 if ml_det else 1.0,
            "label": prov_check.get("contribution_class", "unknown"),
        }
    )
    return AuthenticityReport.create(
        {
            "overall": {"label": label, "confidence": confidence, "summary": summary},
            "provenance_check": prov_check,
            "ml_detection": ml_det,
            "signals": signals,
        }
    )


def write_minimal_smf(path: Path, *, duration_sec: float = 1.0, note: int = 60) -> None:
    """Write a minimal type-0 SMF (dev stub) without external MIDI libraries."""
    import struct

    def vlq(value: int) -> bytes:
        buffer = value & 0x7F
        value >>= 7
        parts = []
        while value:
            parts.insert(0, struct.pack("B", 0x80 | (value & 0x7F)))
            value >>= 7
        parts.append(struct.pack("B", buffer))
        return b"".join(parts)

    ticks = int(480 * duration_sec)
    track = b"MTrk" + struct.pack(">I", 0)
    events = b""
    events += b"\x00" + bytes([0x90, note, 80])
    events += vlq(ticks) + bytes([0x80, note, 0])
    events += b"\x00\xff/\x00"
    track_data = events
    track = b"MTrk" + struct.pack(">I", len(track_data)) + track_data
    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480)
    path.write_bytes(header + track)
