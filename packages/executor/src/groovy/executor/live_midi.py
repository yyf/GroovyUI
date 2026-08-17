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
class AudioDeviceInfo:
    id: str
    name: str
    manufacturer: str = ""
    direction: str = "in"
    channels: int = 0
    sample_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "direction": self.direction,
            "channels": self.channels,
            "sample_rate": self.sample_rate,
        }


VIRTUAL_AUDIO_INPUT = AudioDeviceInfo(
    id="virtual:audio:in-demo",
    name="Virtual Audio In (demo)",
    manufacturer="GroovyUI",
    direction="in",
    channels=2,
    sample_rate=48000.0,
)
VIRTUAL_AUDIO_OUTPUT = AudioDeviceInfo(
    id="virtual:audio:out-demo",
    name="Virtual Audio Out (preview route)",
    manufacturer="GroovyUI",
    direction="out",
    channels=2,
    sample_rate=48000.0,
)


@dataclass
class LiveIoSettings:
    midi_input_enabled: bool = False
    midi_output_enabled: bool = False
    osc_live_enabled: bool = False
    default_input_id: str | None = VIRTUAL_INPUT.id
    default_output_id: str | None = VIRTUAL_OUTPUT.id
    audio_input_enabled: bool = False
    audio_output_enabled: bool = False
    default_audio_input_id: str | None = VIRTUAL_AUDIO_INPUT.id
    default_audio_output_id: str | None = VIRTUAL_AUDIO_OUTPUT.id

    def to_dict(self) -> dict[str, Any]:
        return {
            "midi_input_enabled": self.midi_input_enabled,
            "midi_output_enabled": self.midi_output_enabled,
            "osc_live_enabled": self.osc_live_enabled,
            "default_input_id": self.default_input_id,
            "default_output_id": self.default_output_id,
            "audio_input_enabled": self.audio_input_enabled,
            "audio_output_enabled": self.audio_output_enabled,
            "default_audio_input_id": self.default_audio_input_id,
            "default_audio_output_id": self.default_audio_output_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LiveIoSettings:
        return cls(
            midi_input_enabled=bool(data.get("midi_input_enabled", False)),
            midi_output_enabled=bool(data.get("midi_output_enabled", False)),
            osc_live_enabled=bool(data.get("osc_live_enabled", False)),
            default_input_id=data.get("default_input_id", VIRTUAL_INPUT.id),
            default_output_id=data.get("default_output_id", VIRTUAL_OUTPUT.id),
            audio_input_enabled=bool(data.get("audio_input_enabled", False)),
            audio_output_enabled=bool(data.get("audio_output_enabled", False)),
            default_audio_input_id=data.get("default_audio_input_id", VIRTUAL_AUDIO_INPUT.id),
            default_audio_output_id=data.get("default_audio_output_id", VIRTUAL_AUDIO_OUTPUT.id),
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

    def list_audio_devices(self, direction: str | None = None) -> list[AudioDeviceInfo]:
        devices: list[AudioDeviceInfo] = []
        if direction in (None, "in"):
            devices.append(VIRTUAL_AUDIO_INPUT)
        if direction in (None, "out"):
            devices.append(VIRTUAL_AUDIO_OUTPUT)
        try:
            import sounddevice as sd

            hostapis = sd.query_hostapis()
            for index, info in enumerate(sd.query_devices()):
                hostapi = hostapis[info["hostapi"]]["name"] if info.get("hostapi") is not None else "sounddevice"
                name = str(info.get("name", f"Device {index}"))
                default_rate = float(info.get("default_samplerate") or 48000.0)
                if int(info.get("max_input_channels", 0)) > 0 and direction in (None, "in"):
                    devices.append(
                        AudioDeviceInfo(
                            id=f"sounddevice:in:{index}",
                            name=name,
                            manufacturer=hostapi,
                            direction="in",
                            channels=int(info["max_input_channels"]),
                            sample_rate=default_rate,
                        )
                    )
                if int(info.get("max_output_channels", 0)) > 0 and direction in (None, "out"):
                    devices.append(
                        AudioDeviceInfo(
                            id=f"sounddevice:out:{index}",
                            name=name,
                            manufacturer=hostapi,
                            direction="out",
                            channels=int(info["max_output_channels"]),
                            sample_rate=default_rate,
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


def write_midi_events_meta(
    cache: Any,
    midi: MidiBuffer,
    events: list[dict[str, Any]],
    midi_bytes: bytes | None = None,
) -> MidiBuffer:
    events_path = cache.cache_dir / f"{midi.id}.midi.events.json"
    events_path.write_text(json.dumps(events, indent=2))
    cache.write_midi(midi, midi_bytes=midi_bytes)
    meta = midi.to_meta()
    meta["events_path"] = str(events_path)
    meta_path = cache.cache_dir / f"{midi.id}.midi.meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    return midi


def smf_bytes_from_note_events(
    events: list[dict[str, Any]],
    *,
    sample_rate: int,
    tempo_bpm: float = 120.0,
) -> bytes:
    """Serialize note_on/note_off executor events to a Type-0 SMF."""
    import tempfile
    from pretty_midi import Instrument, Note, PrettyMIDI

    sr = max(1, int(sample_rate))
    pm = PrettyMIDI(initial_tempo=float(tempo_bpm))
    inst = Instrument(program=0, is_drum=False)
    pending: dict[tuple[int, int], tuple[int, float]] = {}
    ordered = sorted(events, key=lambda item: (int(item.get("frame", 0)), str(item.get("type", ""))))
    for event in ordered:
        etype = str(event.get("type", ""))
        if etype not in {"note_on", "note_off"}:
            continue
        channel = int(event.get("channel", 0))
        note = max(0, min(127, int(event.get("note", 60))))
        frame = max(0, int(event.get("frame", 0)))
        velocity = float(event.get("velocity", 0.8))
        key = (channel, note)
        if etype == "note_on" and velocity > 0:
            pending[key] = (frame, velocity)
            continue
        start = pending.pop(key, None)
        if start is None:
            continue
        start_frame, start_vel = start
        start_t = start_frame / sr
        end_t = max(start_t + (1.0 / sr), frame / sr)
        inst.notes.append(
            Note(
                velocity=max(1, min(127, int(round(start_vel * 127.0)))),
                pitch=note,
                start=start_t,
                end=end_t,
            )
        )
    for (_channel, note), (start_frame, start_vel) in pending.items():
        start_t = start_frame / sr
        inst.notes.append(
            Note(
                velocity=max(1, min(127, int(round(start_vel * 127.0)))),
                pitch=note,
                start=start_t,
                end=start_t + 0.05,
            )
        )
    pm.instruments.append(inst)
    handle = tempfile.NamedTemporaryFile(suffix=".mid", delete=False)
    path = Path(handle.name)
    handle.close()
    try:
        pm.write(str(path))
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def events_from_smf(
    mid_path: Path | str,
    *,
    sample_rate: int,
    frame_count: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Parse Standard MIDI File notes/CC into executor event dicts.

    Channel is 0-based (PrettyMIDI / SMF). Duration frames are derived from the
    file end time when *frame_count* is omitted.
    """
    from pretty_midi import PrettyMIDI

    pm = PrettyMIDI(str(mid_path))
    duration = max(0.25, float(pm.get_end_time()))
    frames = frame_count if frame_count is not None else max(1, int(round(duration * sample_rate)))
    events: list[dict[str, Any]] = []
    for instrument in pm.instruments:
        channel = int(getattr(instrument, "midi_channel", 0) or 0)
        for note in instrument.notes:
            start = max(0, min(frames - 1, int(round(note.start * sample_rate))))
            end = max(start, min(frames - 1, int(round(note.end * sample_rate))))
            events.append(
                {
                    "frame": start,
                    "type": "note_on",
                    "channel": channel,
                    "note": int(note.pitch),
                    "velocity": float(note.velocity) / 127.0,
                }
            )
            events.append(
                {
                    "frame": end,
                    "type": "note_off",
                    "channel": channel,
                    "note": int(note.pitch),
                    "velocity": 0.0,
                }
            )
        for cc in instrument.control_changes:
            frame = max(0, min(frames - 1, int(round(cc.time * sample_rate))))
            events.append(
                {
                    "frame": frame,
                    "type": "cc",
                    "channel": channel,
                    "num": int(cc.number),
                    "value": float(cc.value) / 127.0,
                }
            )
    events.sort(key=lambda item: (int(item.get("frame", 0)), str(item.get("type", ""))))
    return events, frames


def load_midi_events(cache: Any, midi_id: str) -> list[dict[str, Any]]:
    events_path = cache.cache_dir / f"{midi_id}.midi.events.json"
    if events_path.exists():
        return json.loads(events_path.read_text())
    mid_path = cache.cache_dir / f"{midi_id}.mid"
    if mid_path.exists():
        try:
            midi = cache.load_midi(midi_id)
            events, _frames = events_from_smf(
                mid_path,
                sample_rate=int(midi.sample_rate),
                frame_count=int(midi.frame_count),
            )
            events_path.write_text(json.dumps(events, indent=2))
            return events
        except Exception:
            return []
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
