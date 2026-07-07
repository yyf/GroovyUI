from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class MidiBuffer:
    id: str
    sample_rate: int
    frame_count: int
    ppq: int = 480
    midi_kind: str = "transcript"
    format: str = "smf"
    tracks: int = 1
    path: str | None = None
    tempo_bpm: float = 120.0
    source_node: str | None = None
    source_node_type: str | None = None

    def to_meta(self) -> dict:
        return {
            "id": self.id,
            "type": "MIDI",
            "format": self.format,
            "midi_kind": self.midi_kind,
            "sample_rate": self.sample_rate,
            "frame_count": self.frame_count,
            "ppq": self.ppq,
            "tracks": self.tracks,
            "tempo_map": [{"frame": 0, "bpm": self.tempo_bpm}],
            "path": self.path,
            "source_node": self.source_node,
            "source_node_type": self.source_node_type,
            "created_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def create(
        cls,
        *,
        sample_rate: int,
        frame_count: int,
        source_node_type: str = "AudioToMIDI",
        midi_kind: str = "transcript",
        ppq: int = 480,
    ) -> MidiBuffer:
        return cls(
            id=str(uuid.uuid4()),
            sample_rate=sample_rate,
            frame_count=frame_count,
            ppq=ppq,
            midi_kind=midi_kind,
            source_node_type=source_node_type,
        )
