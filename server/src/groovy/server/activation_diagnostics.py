from __future__ import annotations

import json
import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ALLOWED_EVENTS = {
    "task_started",
    "workflow_applied",
    "compliance_confirmed",
    "install_started",
    "install_completed",
    "render_started",
    "render_completed",
    "playback_requested",
    "playback_started",
    "playback_failed",
    "cancelled",
    "failed",
}
ALLOWED_CONTEXT_KEYS = {
    "source",
    "template_id",
    "model_id",
    "model_count",
    "preview_node_id",
    "preview_kind",
    "reason",
}
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_SESSIONS = 100
RETENTION_DAYS = 30
ROTATE_AFTER_BYTES = 1024 * 1024


class ActivationDiagnosticsStore:
    """Privacy-limited local timing traces for first-audition diagnostics."""

    def __init__(self, project_dir: Path) -> None:
        self.path = (
            project_dir.resolve()
            / ".groovy"
            / "diagnostics"
            / "activation.jsonl"
        )
        self._lock = threading.Lock()

    def append(
        self,
        *,
        session_id: str,
        event: str,
        elapsed_ms: int,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("Invalid activation diagnostics session ID.")
        if event not in ALLOWED_EVENTS:
            raise ValueError(f"Unsupported activation diagnostics event: {event}")
        if elapsed_ms < 0:
            raise ValueError("elapsed_ms must be non-negative.")
        record = {
            "schema_version": "1.0",
            "session_id": session_id,
            "event": event,
            "elapsed_ms": min(int(elapsed_ms), 24 * 60 * 60 * 1000),
            "recorded_at": datetime.now(UTC).isoformat(),
            "context": self._sanitize_context(context or {}),
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as destination:
                destination.write(json.dumps(record, separators=(",", ":")) + "\n")
            if self.path.stat().st_size > ROTATE_AFTER_BYTES:
                self._rotate()
        return record

    def summary(self) -> dict[str, Any]:
        with self._lock:
            records = self._read_records()
        sessions: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            sessions.setdefault(str(record["session_id"]), []).append(record)
        latest_records = (
            sessions[str(records[-1]["session_id"])] if records else []
        )
        return {
            "path": str(self.path),
            "stored_locally": True,
            "session_count": len(sessions),
            "event_count": len(records),
            "latest_session": self._summarize_session(latest_records),
        }

    def clear(self) -> None:
        with self._lock:
            self.path.unlink(missing_ok=True)

    def _read_records(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(record, dict)
                and record.get("event") in ALLOWED_EVENTS
                and isinstance(record.get("session_id"), str)
            ):
                records.append(record)
        return records

    def _rotate(self) -> None:
        records = self._read_records()
        cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
        recent: list[dict[str, Any]] = []
        for record in records:
            try:
                recorded_at = datetime.fromisoformat(str(record["recorded_at"]))
            except (KeyError, TypeError, ValueError):
                continue
            if recorded_at.tzinfo is None:
                recorded_at = recorded_at.replace(tzinfo=UTC)
            if recorded_at >= cutoff:
                recent.append(record)
        session_ids = list(dict.fromkeys(str(item["session_id"]) for item in recent))
        allowed_sessions = set(session_ids[-MAX_SESSIONS:])
        kept = [
            record
            for record in recent
            if str(record["session_id"]) in allowed_sessions
        ]
        temporary = self.path.with_suffix(".jsonl.tmp")
        temporary.write_text(
            "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in kept),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    @staticmethod
    def _sanitize_context(context: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key in ALLOWED_CONTEXT_KEYS:
            value = context.get(key)
            if isinstance(value, bool | int | float):
                sanitized[key] = value
            elif isinstance(value, str):
                candidate = value[:120]
                if (
                    candidate.startswith(("/", "\\", "~"))
                    or re.match(r"^[A-Za-z]:[\\/]", candidate)
                    or "://" in candidate
                ):
                    sanitized[key] = "[redacted]"
                else:
                    sanitized[key] = candidate
        return sanitized

    @staticmethod
    def _summarize_session(
        records: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not records:
            return None
        events = [str(record["event"]) for record in records]
        if "playback_started" in events:
            outcome = "audible"
        elif "failed" in events:
            outcome = "failed"
        elif "cancelled" in events:
            outcome = "cancelled"
        elif "playback_failed" in events:
            outcome = "playback_blocked"
        else:
            outcome = "in_progress"
        first_audible = next(
            (
                int(record["elapsed_ms"])
                for record in records
                if record["event"] == "playback_started"
            ),
            None,
        )
        return {
            "session_id": records[0]["session_id"],
            "started_at": records[0]["recorded_at"],
            "outcome": outcome,
            "elapsed_ms": max(int(record.get("elapsed_ms", 0)) for record in records),
            "time_to_first_audible_ms": first_audible,
            "context": records[0].get("context") or {},
            "milestones": [
                {
                    "event": record["event"],
                    "elapsed_ms": int(record.get("elapsed_ms", 0)),
                    "context": record.get("context") or {},
                }
                for record in records
            ],
        }
