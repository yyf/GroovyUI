from __future__ import annotations

import uuid
from typing import Any

from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata

# Foreign class_type / type → GroovyUI node type (partial Phase 2 subset).
EXTERNAL_NODE_MAP: dict[str, str] = {
    "LoadAudio": "LoadAudio",
    "SaveAudio": "SaveAudio",
    "PreviewAudio": "Preview",
    "NormalizeAudio": "Normalize",
    "DenoiseAudio": "Denoise",
    "Demucs": "SeparateStems",
    "Whisper": "WhisperSTT",
    "TTS": "GenerateSpeech",
    "VoiceConvert": "VoiceConvert",
    "TimbreTransfer": "TimbreTransfer",
}

# Foreign link type → Groovy socket type.
EXTERNAL_LINK_TYPES: dict[str, str] = {
    "AUDIO": "AUDIO",
    "STRING": "TEXT",
    "MIDI": "MIDI",
}


def import_external_graph(
    data: dict[str, Any],
    *,
    title: str = "Imported graph",
) -> dict[str, Any]:
    """Convert an external node-graph workflow dict into a GroovyUI workflow dict."""
    source_nodes = data.get("nodes", [])
    source_links = data.get("links", [])

    id_map: dict[int | str, str] = {}
    groovy_nodes: list[NodeInstance] = []
    unmapped: list[str] = []

    for node in source_nodes:
        source_id = node.get("id")
        source_type = str(node.get("type") or node.get("class_type") or "")
        groovy_type = EXTERNAL_NODE_MAP.get(source_type)
        if not groovy_type:
            unmapped.append(source_type)
            continue
        groovy_id = f"n{source_id}"
        id_map[source_id] = groovy_id
        pos = node.get("pos") or [0, 0]
        widgets = _widgets_from_external(node, groovy_type)
        groovy_nodes.append(
            NodeInstance(
                id=groovy_id,
                type=groovy_type,
                pos={"x": float(pos[0]), "y": float(pos[1])},
                widgets=widgets,
            )
        )

    groovy_links: list[Link] = []
    for index, link in enumerate(source_links):
        if not isinstance(link, (list, tuple)) or len(link) < 4:
            continue
        src_id, src_slot, dst_id, dst_slot = link[0], link[1], link[2], link[3]
        link_type = EXTERNAL_LINK_TYPES.get(str(link[4]) if len(link) > 4 else "AUDIO", "AUDIO")
        src = id_map.get(src_id)
        dst = id_map.get(dst_id)
        if not src or not dst:
            continue
        groovy_links.append(
            Link(
                id=f"l{index + 1}",
                from_=[src, int(src_slot)],
                to=[dst, int(dst_slot)],
                type=link_type,
            )
        )

    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id=str(uuid.uuid4()),
        metadata=WorkflowMetadata(title=title, description="Converted from an external node graph"),
        nodes=groovy_nodes,
        links=groovy_links,
    )
    result = workflow.model_dump(by_alias=True)
    result["import_meta"] = {
        "source": "external_graph",
        "unmapped_node_types": sorted(set(unmapped)),
        "mapped_nodes": len(groovy_nodes),
        "mapped_links": len(groovy_links),
    }
    return result


def _widgets_from_external(node: dict[str, Any], groovy_type: str) -> dict[str, Any]:
    widgets: dict[str, Any] = {}
    widgets_values = node.get("widgets_values") or []
    inputs = node.get("inputs") or {}

    if groovy_type == "LoadAudio" and widgets_values:
        widgets["path"] = str(widgets_values[0])
    elif groovy_type == "SaveAudio" and widgets_values:
        full = str(widgets_values[0])
        if "/" in full:
            parent, _, leaf = full.rpartition("/")
            widgets["path"] = parent or "exports"
            widgets["filename"] = leaf
        else:
            widgets["filename"] = full
    elif groovy_type == "Normalize":
        widgets.setdefault("target_lufs", -16.0)
    elif groovy_type in {
        "Denoise",
        "SeparateStems",
        "WhisperSTT",
        "GenerateSpeech",
        "VoiceConvert",
        "TimbreTransfer",
    }:
        if widgets_values and isinstance(widgets_values[0], str):
            widgets["model"] = widgets_values[0]

    for key, value in inputs.items():
        if isinstance(value, (str, int, float, bool)):
            widgets[key] = value

    return widgets
