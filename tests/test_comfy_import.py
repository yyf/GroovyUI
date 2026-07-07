from __future__ import annotations

from groovy.schema.comfy_import import import_comfy_workflow
from groovy.schema.models import Workflow
from groovy.schema.validate import validate_workflow
from groovy.nodes.core import register_all
from groovy.node import NODE_REGISTRY

register_all()


def test_import_comfy_maps_known_nodes() -> None:
    comfy = {
        "nodes": [
            {"id": 1, "type": "LoadAudio", "pos": [0, 0], "widgets_values": ["audio.wav"]},
            {"id": 2, "type": "NormalizeAudio", "pos": [300, 0], "widgets_values": []},
            {"id": 3, "type": "PreviewAudio", "pos": [600, 0], "widgets_values": []},
            {"id": 99, "type": "UnknownComfyNode", "pos": [900, 0], "widgets_values": []},
        ],
        "links": [
            [1, 0, 2, 0, "AUDIO"],
            [2, 0, 3, 0, "AUDIO"],
        ],
    }
    result = import_comfy_workflow(comfy, title="Test import")
    import_meta = result.pop("import_meta")
    assert import_meta["mapped_nodes"] == 3
    assert import_meta["mapped_links"] == 2
    assert "UnknownComfyNode" in import_meta["unmapped_node_types"]
    assert [n["type"] for n in result["nodes"]] == ["LoadAudio", "Normalize", "Preview"]
    validation = validate_workflow(
        Workflow.model_validate(result),
        known_node_types=set(NODE_REGISTRY.keys()),
    )
    assert validation.valid


def test_import_comfy_api_shape() -> None:
    result = import_comfy_workflow({"nodes": [], "links": []})
    assert result["import_meta"]["source"] == "comfyui"
    assert result["metadata"]["title"]
