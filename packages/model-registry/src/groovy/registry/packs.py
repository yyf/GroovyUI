from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NodePackManifest:
    id: str
    version: str
    name: str
    description: str
    trust_tier: str
    license_spdx: str
    node_types: list[str]
    deps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "trust_tier": self.trust_tier,
            "license": {"spdx": self.license_spdx},
            "node_types": self.node_types,
            "deps": self.deps,
        }


PACK_CATALOG: dict[str, NodePackManifest] = {
    "groovy-immersive-stubs": NodePackManifest(
        id="groovy-immersive-stubs",
        version="0.1.0",
        name="Groovy Immersive Stubs",
        description="Community-tier metadata pack for immersive/OBA workflow templates (no extra Python).",
        trust_tier="community",
        license_spdx="Apache-2.0",
        node_types=[
            "AmbisonicEncode",
            "AmbisonicDecode",
            "ObjectFromAudio",
            "ObjectMerge",
            "RenderObjectScene",
        ],
        deps=[],
    ),
    "groovy-modular-control": NodePackManifest(
        id="groovy-modular-control",
        version="0.1.0",
        name="Groovy Modular Control",
        description="Control-rate wiring helpers for MIDI/automation subgraphs.",
        trust_tier="community",
        license_spdx="Apache-2.0",
        node_types=[
            "LoadMIDI",
            "MIDIToFloat",
            "MIDINoteGate",
            "ControlCurve",
            "AutomationApply",
            "Float",
            "FloatMath",
            "FloatRoute",
            "SignalGenerator",
            "NoiseGenerator",
            "Oscillator",
            "MatrixMixer",
            "Filter",
            "Amplifier",
            "Envelope",
            "LFO",
            "Attenuator",
            "Logic",
            "Comparator",
            "SampleAndHold",
            "Quantizer",
            "Clock",
            "ModuleInlet",
            "ModuleOutlet",
        ],
        deps=[],
    ),
}


def list_packs() -> list[NodePackManifest]:
    return list(PACK_CATALOG.values())


def get_pack(pack_id: str) -> NodePackManifest | None:
    return PACK_CATALOG.get(pack_id)
