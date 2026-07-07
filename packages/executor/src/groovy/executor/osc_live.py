from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

OSC_ALLOWLIST_PREFIX = "/groovy/"
OSC_RATE_LIMIT_PER_SEC = 100


@dataclass
class OscBuffer:
    id: str
    sample_rate: int
    frame_count: int
    events: list[dict[str, Any]] = field(default_factory=list)
    source_node_type: str | None = None

    def to_meta(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "OSC",
            "sample_rate": self.sample_rate,
            "frame_count": self.frame_count,
            "event_count": len(self.events),
            "source_node_type": self.source_node_type,
            "created_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def create(
        cls,
        *,
        sample_rate: int,
        frame_count: int,
        events: list[dict[str, Any]] | None = None,
        source_node_type: str = "OSCInLive",
    ) -> OscBuffer:
        return cls(
            id=str(uuid.uuid4()),
            sample_rate=sample_rate,
            frame_count=frame_count,
            events=list(events or []),
            source_node_type=source_node_type,
        )


def is_allowed_osc_address(address: str) -> bool:
    return address.startswith(OSC_ALLOWLIST_PREFIX)


_PARAM_RE = re.compile(
    r"^/groovy/node/(?P<node_id>[^/]+)/(?P<param>[^/]+)$"
)


def parse_widget_target(address: str) -> tuple[str, str] | None:
    match = _PARAM_RE.match(address)
    if not match:
        return None
    return match.group("node_id"), match.group("param")


class OscCaptureStore:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self._events: list[dict[str, Any]] = []
        self._last_second = 0.0
        self._second_count = 0

    @property
    def capture_path(self) -> Path:
        path = self.project_dir / ".groovy" / "osc_capture.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _rate_ok(self) -> bool:
        now = time.monotonic()
        if now - self._last_second >= 1.0:
            self._last_second = now
            self._second_count = 0
        if self._second_count >= OSC_RATE_LIMIT_PER_SEC:
            return False
        self._second_count += 1
        return True

    def append(self, address: str, args: list[Any], *, frame: int = 0) -> bool:
        if not is_allowed_osc_address(address):
            return False
        if not self._rate_ok():
            return False
        event = {
            "frame": frame,
            "address": address,
            "args": args,
            "received_at": datetime.now(UTC).isoformat(),
        }
        self._events.append(event)
        if len(self._events) > 5000:
            self._events.pop(0)
        self.capture_path.write_text(json.dumps(self._events, indent=2))
        return True

    def events(self) -> list[dict[str, Any]]:
        if self.capture_path.exists():
            return json.loads(self.capture_path.read_text())
        return list(self._events)
