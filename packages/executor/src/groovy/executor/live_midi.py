from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from groovy.executor.midi import MidiBuffer


@dataclass
class MidiDeviceInfo:
    id: str
    name: str
    manufacturer: str = ""
    direction: str = "in"

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "direction": self.direction,
        }


VIRTUAL_INPUT = MidiDeviceInfo(
    id="virtual:in-demo",
    name="Virtual MIDI In (demo CC)",
    manufacturer="GroovyUI",
    direction="in",
)
VIRTUAL_OUTPUT = MidiDeviceInfo(
    id="virtual:out-demo",
    name="Virtual MIDI Out (log only)",
    manufacturer="GroovyUI",
    direction="out",
)


@dataclass
class LiveIoSettings:
    midi_input_enabled: bool = False
    midi_output_enabled: bool = False
    osc_live_enabled: bool = False
    default_input_id: str | None = VIRTUAL_INPUT.id
    default_output_id: str | None = VIRTUAL_OUTPUT.id

    def to_dict(self) -> dict[str, Any]:
        return {
            "midi_input_enabled": self.midi_input_enabled,
            "midi_output_enabled": self.midi_output_enabled,
            "osc_live_enabled": self.osc_live_enabled,
            "default_input_id": self.default_input_id,
            "default_output_id": self.default_output_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LiveIoSettings:
        return cls(
            midi_input_enabled=bool(data.get("midi_input_enabled", False)),
            midi_output_enabled=bool(data.get("midi_output_enabled", False)),
            osc_live_enabled=bool(data.get("osc_live_enabled", False)),
            default_input_id=data.get("default_input_id", VIRTUAL_INPUT.id),
            default_output_id=data.get("default_output_id", VIRTUAL_OUTPUT.id),
        )


class LiveIoState:
    """Process-wide live I/O settings and capture buffers."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.settings = LiveIoSettings()
        self._midi_capture: dict[str, list[dict[str, Any]]] = {}
        self._midi_out_log: list[dict[str, Any]] = []
        self._load_settings()

    @property
    def settings_path(self) -> Path:
        return self.project_dir / ".groovy" / "live_io_settings.json"

    @property
    def capture_dir(self) -> Path:
        path = self.project_dir / ".groovy" / "midi_capture"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _load_settings(self) -> None:
        if not self.settings_path.exists():
            return
        try:
            data = json.loads(self.settings_path.read_text())
            self.settings = LiveIoSettings.from_dict(data)
        except (json.JSONDecodeError, OSError):
            self.settings = LiveIoSettings()

    def save_settings(self) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(self.settings.to_dict(), indent=2))

    def list_devices(self, direction: str | None = None) -> list[MidiDeviceInfo]:
        devices = [VIRTUAL_INPUT, VIRTUAL_OUTPUT]
        try:
            import rtmidi

            midi_in = rtmidi.MidiIn()
            midi_out = rtmidi.MidiOut()
            if direction in (None, "in"):
                for index, name in enumerate(midi_in.get_ports()):
                    devices.append(
                        MidiDeviceInfo(
                            id=f"rtmidi:in:{index}",
                            name=name,
                            manufacturer="rtmidi",
                            direction="in",
                        )
                    )
            if direction in (None, "out"):
                for index, name in enumerate(midi_out.get_ports()):
                    devices.append(
                        MidiDeviceInfo(
                            id=f"rtmidi:out:{index}",
                            name=name,
                            manufacturer="rtmidi",
                            direction="out",
                        )
                    )
        except Exception:
            pass
        if direction:
            devices = [device for device in devices if device.direction == direction]
        return devices

    def append_midi_input(self, device_id: str, event: dict[str, Any]) -> None:
        if event.get("type") == "sysex":
            return
        now = time.monotonic()
        bucket = self._midi_capture.setdefault(device_id, [])
        if bucket:
            last_ts = float(bucket[-1].get("_ts", now))
            if now - last_ts < 0.001:
                return
        if len(bucket) >= 1000:
            bucket.pop(0)
        event = {**event, "_ts": now}
        bucket.append(event)
        capture_path = self.capture_dir / f"{device_id.replace(':', '_')}.json"
        capture_path.write_text(json.dumps(bucket, indent=2))

    def read_midi_capture(self, device_id: str) -> list[dict[str, Any]]:
        if device_id in self._midi_capture:
            return list(self._midi_capture[device_id])
        capture_path = self.capture_dir / f"{device_id.replace(':', '_')}.json"
        if capture_path.exists():
            return json.loads(capture_path.read_text())
        return []

    def append_midi_output(self, event: dict[str, Any]) -> None:
        if event.get("type") == "sysex":
            return
        if len(self._midi_out_log) >= 1000:
            self._midi_out_log.pop(0)
        self._midi_out_log.append({**event, "sent_at": datetime.now(UTC).isoformat()})
        log_path = self.capture_dir / "midi_out_log.json"
        log_path.write_text(json.dumps(self._midi_out_log, indent=2))

    def midi_out_log(self) -> list[dict[str, Any]]:
        log_path = self.capture_dir / "midi_out_log.json"
        if log_path.exists():
            return json.loads(log_path.read_text())
        return list(self._midi_out_log)


def demo_control_events(*, frame_count: int, sample_rate: int, cc: int = 7) -> list[dict[str, Any]]:
    """Deterministic CC ramp for virtual MIDI input during offline render."""
    return [
        {"frame": 0, "type": "cc", "channel": 1, "num": cc, "value": 0.25},
        {"frame": frame_count // 2, "type": "cc", "channel": 1, "num": cc, "value": 0.75},
        {"frame": max(0, frame_count - 1), "type": "cc", "channel": 1, "num": cc, "value": 0.5},
    ]


def midi_buffer_from_events(
    events: list[dict[str, Any]],
    *,
    sample_rate: int,
    frame_count: int,
    source_node_type: str,
    midi_kind: str,
    device_id: str,
) -> MidiBuffer:
    midi = MidiBuffer.create(
        sample_rate=sample_rate,
        frame_count=frame_count,
        source_node_type=source_node_type,
        midi_kind=midi_kind,
    )
    midi.path = None
    midi.source_node = device_id
    return midi


def write_midi_events_meta(cache: Any, midi: MidiBuffer, events: list[dict[str, Any]]) -> MidiBuffer:
    events_path = cache.cache_dir / f"{midi.id}.midi.events.json"
    events_path.write_text(json.dumps(events, indent=2))
    cache.write_midi(midi, midi_bytes=None)
    meta = midi.to_meta()
    meta["events_path"] = str(events_path)
    meta_path = cache.cache_dir / f"{midi.id}.midi.meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    return midi


def load_midi_events(cache: Any, midi_id: str) -> list[dict[str, Any]]:
    events_path = cache.cache_dir / f"{midi_id}.midi.events.json"
    if events_path.exists():
        return json.loads(events_path.read_text())
    return []


def automation_from_midi_events(
    events: list[dict[str, Any]],
    *,
    frame_count: int,
    cc: int,
    default_value: float,
) -> list[float]:
    values = [default_value] * frame_count
    relevant = sorted(
        [event for event in events if event.get("type") == "cc" and int(event.get("num", -1)) == cc],
        key=lambda item: int(item.get("frame", 0)),
    )
    if not relevant:
        return values
    cursor = 0
    current = float(relevant[0].get("value", default_value))
    for event in relevant:
        frame = int(event.get("frame", 0))
        frame = max(0, min(frame_count - 1, frame))
        for index in range(cursor, frame + 1):
            values[index] = current
        current = float(event.get("value", current))
        cursor = frame + 1
    for index in range(cursor, frame_count):
        values[index] = current
    return values


def midi_events_from_automation(
    values: list[float] | Any,
    *,
    frame_count: int,
    channel: int,
    cc_number: int,
) -> list[dict[str, Any]]:
    import numpy as np

    curve = np.asarray(values, dtype=np.float64).reshape(-1)
    if curve.size != frame_count:
        x_old = np.linspace(0, 1, max(1, curve.size))
        x_new = np.linspace(0, 1, frame_count)
        curve = np.interp(x_new, x_old, curve)
    events: list[dict[str, Any]] = []
    last_value: float | None = None
    for frame, value in enumerate(curve):
        clipped = float(max(0.0, min(1.0, value)))
        if last_value is None or abs(clipped - last_value) > 0.01:
            events.append(
                {
                    "frame": frame,
                    "type": "cc",
                    "channel": channel,
                    "num": cc_number,
                    "value": clipped,
                }
            )
            last_value = clipped
    return events
