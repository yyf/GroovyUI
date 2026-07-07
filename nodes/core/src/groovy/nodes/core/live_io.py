from __future__ import annotations

from pathlib import Path

import numpy as np
from groovy.executor.control import AutomationBuffer
from groovy.executor.live_midi import (
    VIRTUAL_INPUT,
    automation_from_midi_events,
    demo_control_events,
    load_midi_events,
    midi_buffer_from_events,
    midi_events_from_automation,
    write_midi_events_meta,
)
from groovy.executor.midi import MidiBuffer
from groovy.executor.osc_live import OscBuffer
from groovy.node import GroovyNode, register_node


def register_live_io() -> None:
    _ = (MIDIInDevice, MIDIOutDevice, OSCInLive)


@register_node
class MIDIInDevice(GroovyNode):
    CATEGORY = "GroovyUI/Live"
    RETURN_TYPES = ("MIDI",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "device_id": ("STRING", {"default": VIRTUAL_INPUT.id}),
                "channel_filter": ("STRING", {"default": "all"}),
                "mode": ("STRING", {"default": "control"}),
                "record_arm": ("BOOL", {"default": False}),
                "sample_rate": ("INT", {"default": 48000}),
                "frame_count": ("INT", {"default": 48000}),
            },
        }

    def run(
        self,
        device_id: str = VIRTUAL_INPUT.id,
        channel_filter: str = "all",
        mode: str = "control",
        record_arm: bool = False,
        sample_rate: int = 48000,
        frame_count: int = 48000,
        **kwargs,
    ) -> tuple[MidiBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        device_id = str(kwargs.get("device_id", device_id))
        mode = str(kwargs.get("mode", mode))
        sample_rate = int(kwargs.get("sample_rate", sample_rate))
        frame_count = int(kwargs.get("frame_count", frame_count))
        midi_kind = "performance" if mode == "performance" else "control"
        _ = (kwargs.get("channel_filter", channel_filter), kwargs.get("record_arm", record_arm))

        from groovy.executor.live_midi import LiveIoState

        state = LiveIoState(self._ctx.project_dir)
        events = state.read_midi_capture(device_id)
        if not events:
            fallback = self._ctx.project_dir / "assets" / "samples" / "automation_cc7.mid"
            if fallback.exists():
                midi = MidiBuffer.create(
                    sample_rate=sample_rate,
                    frame_count=frame_count,
                    source_node_type="MIDIInDevice",
                    midi_kind=midi_kind,
                )
                midi.source_node = device_id
                self._ctx.cache.write_midi(midi, fallback.read_bytes())
                return (midi,)
            events = demo_control_events(frame_count=frame_count, sample_rate=sample_rate)

        filtered = []
        channel_filter_value = str(kwargs.get("channel_filter", channel_filter))
        for event in events:
            if event.get("type") == "sysex":
                continue
            if channel_filter_value != "all":
                if int(event.get("channel", 0)) != int(channel_filter_value):
                    continue
            filtered.append({k: v for k, v in event.items() if k != "_ts"})

        midi = midi_buffer_from_events(
            filtered,
            sample_rate=sample_rate,
            frame_count=frame_count,
            source_node_type="MIDIInDevice",
            midi_kind=midi_kind,
            device_id=device_id,
        )
        write_midi_events_meta(self._ctx.cache, midi, filtered)
        return (midi,)


@register_node
class MIDIOutDevice(GroovyNode):
    CATEGORY = "GroovyUI/Live"
    RETURN_TYPES = ()

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "midi": ("MIDI",),
                "value": ("FLOAT",),
                "device_id": ("STRING", {"default": "virtual:out-demo"}),
                "channel": ("INT", {"default": 1}),
                "mode": ("STRING", {"default": "stream"}),
                "cc_number": ("INT", {"default": 7}),
                "frame_count": ("INT", {"default": 48000}),
            },
        }

    def run(
        self,
        device_id: str = "virtual:out-demo",
        channel: int = 1,
        mode: str = "stream",
        cc_number: int = 7,
        frame_count: int = 48000,
        **kwargs,
    ) -> tuple[()]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        from groovy.executor.live_midi import LiveIoState

        state = LiveIoState(self._ctx.project_dir)
        device_id = str(kwargs.get("device_id", device_id))
        mode = str(kwargs.get("mode", mode))
        channel = int(kwargs.get("channel", channel))
        cc_number = int(kwargs.get("cc_number", cc_number))
        frame_count = int(kwargs.get("frame_count", frame_count))

        events: list[dict] = []
        midi = kwargs.get("midi")
        if mode == "cc_mirror":
            automation = kwargs.get("value")
            if isinstance(automation, AutomationBuffer):
                values = automation.resample_to(frame_count)
            elif isinstance(automation, (int, float)):
                values = np.full(frame_count, float(automation))
            else:
                values = np.full(frame_count, 0.5)
            events = midi_events_from_automation(
                values,
                frame_count=frame_count,
                channel=channel,
                cc_number=cc_number,
            )
        elif isinstance(midi, MidiBuffer):
            events = load_midi_events(self._ctx.cache, midi.id)
            if not events and midi.path:
                path = Path(midi.path)
                if path.exists():
                    self._ctx.cache.write_midi(midi, path.read_bytes())
                    events = demo_control_events(frame_count=frame_count, sample_rate=midi.sample_rate)

        for event in events:
            state.append_midi_output({**event, "device_id": device_id})
        return ()


@register_node
class OSCInLive(GroovyNode):
    CATEGORY = "GroovyUI/Live"
    RETURN_TYPES = ("OSC",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "sample_rate": ("INT", {"default": 48000}),
                "frame_count": ("INT", {"default": 48000}),
            },
        }

    def run(self, sample_rate: int = 48000, frame_count: int = 48000, **kwargs) -> tuple[OscBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        sample_rate = int(kwargs.get("sample_rate", sample_rate))
        frame_count = int(kwargs.get("frame_count", frame_count))
        from groovy.executor.osc_live import OscCaptureStore

        store = OscCaptureStore(self._ctx.project_dir)
        events = [
            event
            for event in store.events()
            if str(event.get("address", "")).startswith("/groovy/")
        ]
        buffer = OscBuffer.create(
            sample_rate=sample_rate,
            frame_count=frame_count,
            events=events,
            source_node_type="OSCInLive",
        )
        self._ctx.cache.write_osc(buffer)
        return (buffer,)
