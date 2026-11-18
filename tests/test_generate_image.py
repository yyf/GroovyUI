"""GenerateImage + SwitchImage smoke tests (stub path)."""

from __future__ import annotations

from pathlib import Path

import pytest
from groovy.executor import Executor
from groovy.node import NODE_REGISTRY
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.registry import ModelRegistry
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata
from groovy.schema.validate import validate_workflow

register_core()
register_ai()


def test_generate_image_registered() -> None:
    assert "GenerateImage" in NODE_REGISTRY
    assert NODE_REGISTRY["GenerateImage"].RETURN_TYPES == ("IMAGE", "GENERATE_LOG")
    assert NODE_REGISTRY["GenerateImage"].OUTPUT_NAMES == ("image", "log")
    opt = NODE_REGISTRY["GenerateImage"].INPUT_TYPES()["optional"]
    assert opt["text"][0] == "TEXT"


def test_preview_image_registered() -> None:
    assert "PreviewImage" in NODE_REGISTRY
    assert NODE_REGISTRY["PreviewImage"].RETURN_TYPES == ("IMAGE",)
    req = NODE_REGISTRY["PreviewImage"].INPUT_TYPES()["required"]
    assert req["image"][0] == "IMAGE"


def test_save_image_registered() -> None:
    assert "SaveImage" in NODE_REGISTRY
    assert NODE_REGISTRY["SaveImage"].RETURN_TYPES == ("STRING",)
    req = NODE_REGISTRY["SaveImage"].INPUT_TYPES()["required"]
    assert req["image"][0] == "IMAGE"


def test_save_image_writes_export_and_provenance(tmp_path: Path) -> None:
    sample_src = Path(__file__).resolve().parents[1] / "assets" / "samples" / "Fort-Zeelandia.png"
    sample_dst = tmp_path / "assets" / "samples" / "Fort-Zeelandia.png"
    sample_dst.parent.mkdir(parents=True, exist_ok=True)
    sample_dst.write_bytes(sample_src.read_bytes())
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="save-image",
        metadata=WorkflowMetadata(title="save-image"),
        nodes=[
            NodeInstance(
                id="n0",
                type="LoadImage",
                pos={"x": 0, "y": 0},
                widgets={"path": "assets/samples/Fort-Zeelandia.png"},
            ),
            NodeInstance(
                id="n1",
                type="SaveImage",
                pos={"x": 280, "y": 0},
                widgets={"path": "exports", "filename": "still.png"},
            ),
        ],
        links=[Link(id="l0", **{"from": ["n0", 0], "to": ["n1", 0], "type": "IMAGE"})],
    )
    validate_workflow(workflow)
    out = Executor(tmp_path).execute(workflow, target_nodes=["n1"])
    assert out.status == "completed", out.error
    assert out.outputs["n1"]["type"] == "STRING"
    rel = out.outputs["n1"]["path"]
    assert isinstance(rel, str) and rel.startswith("exports/")
    saved = tmp_path / rel
    assert saved.is_file()
    provenance_rel = out.outputs["n1"].get("provenance_path")
    assert isinstance(provenance_rel, str)
    assert (tmp_path / provenance_rel).is_file()


def test_image_switch_prunes_unselected_generate_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """select=0 must not execute GenerateImage (avoids mflux on LoadImage path)."""
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    sample_src = Path(__file__).resolve().parents[1] / "assets" / "samples" / "Fort-Zeelandia.png"
    sample_dst = tmp_path / "assets" / "samples" / "Fort-Zeelandia.png"
    sample_dst.parent.mkdir(parents=True, exist_ok=True)
    sample_dst.write_bytes(sample_src.read_bytes())
    ModelRegistry(tmp_path).installer.install("flux-image")
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="switch-prune",
        metadata=WorkflowMetadata(title="switch-prune"),
        nodes=[
            NodeInstance(
                id="load",
                type="LoadImage",
                pos={"x": 0, "y": 0},
                widgets={"path": "assets/samples/Fort-Zeelandia.png"},
            ),
            NodeInstance(
                id="gen",
                type="GenerateImage",
                pos={"x": 0, "y": 120},
                # Real model id — would fail without mflux if this branch ran.
                widgets={"model": "flux-klein-4b", "prompt": "should not run", "width": 128, "height": 128},
            ),
            NodeInstance(
                id="sw",
                type="SwitchImage",
                pos={"x": 280, "y": 40},
                widgets={"select": 0},
            ),
        ],
        links=[
            Link(id="la", **{"from": ["load", 0], "to": ["sw", 0], "type": "IMAGE"}),
            Link(id="lb", **{"from": ["gen", 0], "to": ["sw", 1], "type": "IMAGE"}),
        ],
    )
    out = Executor(tmp_path).execute(workflow, target_nodes=["sw"])
    assert out.status == "completed", out.error
    assert "gen" not in out.outputs
    assert out.outputs["sw"].get("path") == "assets/samples/Fort-Zeelandia.png"


def test_image_switch_registered() -> None:
    assert "SwitchImage" in NODE_REGISTRY
    assert NODE_REGISTRY["SwitchImage"].RETURN_TYPES == ("IMAGE",)
    opt = NODE_REGISTRY["SwitchImage"].INPUT_TYPES()["optional"]
    assert opt["a"][0] == "IMAGE"
    assert opt["b"][0] == "IMAGE"


def test_generate_image_stub_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    registry = ModelRegistry(tmp_path)
    registry.installer.install("flux-klein-4b")
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="gen-image",
        metadata=WorkflowMetadata(title="gen-image"),
        nodes=[
            NodeInstance(
                id="n0",
                type="Prompt",
                pos={"x": 0, "y": 0},
                widgets={"text": "a red lighthouse on a cliff"},
            ),
            NodeInstance(
                id="n1",
                type="GenerateImage",
                pos={"x": 260, "y": 0},
                widgets={"model": "flux-klein-4b", "width": 256, "height": 256, "seed": 7},
            ),
        ],
        links=[Link(id="l0", **{"from": ["n0", 0], "to": ["n1", 0], "type": "TEXT"})],
    )
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]
    out = Executor(tmp_path).execute(workflow, target_nodes=["n1"])
    assert out.status == "completed", out.error
    assert out.outputs["n1"]["type"] == "MULTI"
    assert out.outputs["n1"]["outputs"][0]["type"] == "IMAGE"
    assert out.outputs["n1"]["outputs"][1]["type"] == "GENERATE_LOG"
    assert out.outputs["n1"]["outputs"][1].get("generate_log_id")
    rel = out.outputs["n1"]["outputs"][0].get("path")
    assert rel
    assert (tmp_path / str(rel)).is_file()


def test_preview_image_passthrough(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    sample_src = Path(__file__).resolve().parents[1] / "assets" / "samples" / "Fort-Zeelandia.png"
    sample_dst = tmp_path / "assets" / "samples" / "Fort-Zeelandia.png"
    sample_dst.parent.mkdir(parents=True, exist_ok=True)
    sample_dst.write_bytes(sample_src.read_bytes())
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="preview-image",
        metadata=WorkflowMetadata(title="preview-image"),
        nodes=[
            NodeInstance(
                id="n0",
                type="LoadImage",
                pos={"x": 0, "y": 0},
                widgets={"path": "assets/samples/Fort-Zeelandia.png"},
            ),
            NodeInstance(id="n1", type="PreviewImage", pos={"x": 280, "y": 0}, widgets={}),
        ],
        links=[Link(id="l0", **{"from": ["n0", 0], "to": ["n1", 0], "type": "IMAGE"})],
    )
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]
    out = Executor(tmp_path).execute(workflow, target_nodes=["n1"])
    assert out.status == "completed", out.error
    assert out.outputs["n1"]["type"] == "IMAGE"
    assert out.outputs["n1"].get("path") == "assets/samples/Fort-Zeelandia.png"


def test_image_switch_selects_a_or_b(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    sample_src = Path(__file__).resolve().parents[1] / "assets" / "samples" / "Fort-Zeelandia.png"

    def _project(name: str) -> Path:
        project = tmp_path / name
        sample_dst = project / "assets" / "samples" / "Fort-Zeelandia.png"
        sample_dst.parent.mkdir(parents=True, exist_ok=True)
        sample_dst.write_bytes(sample_src.read_bytes())
        ModelRegistry(project).installer.install("flux-image")
        return project

    def _workflow(select: int) -> Workflow:
        return Workflow(
            schema_version="1.0.0",
            groovy_version="0.1.0",
            id=f"switch-{select}",
            metadata=WorkflowMetadata(title=f"switch-{select}"),
            nodes=[
                NodeInstance(
                    id="load",
                    type="LoadImage",
                    pos={"x": 0, "y": 0},
                    widgets={"path": "assets/samples/Fort-Zeelandia.png"},
                ),
                NodeInstance(
                    id="gen",
                    type="GenerateImage",
                    pos={"x": 0, "y": 120},
                    widgets={"model": "flux-image", "prompt": "stub still", "width": 128, "height": 128},
                ),
                NodeInstance(
                    id="sw",
                    type="SwitchImage",
                    pos={"x": 280, "y": 40},
                    widgets={"select": select},
                ),
            ],
            links=[
                Link(id="la", **{"from": ["load", 0], "to": ["sw", 0], "type": "IMAGE"}),
                Link(id="lb", **{"from": ["gen", 0], "to": ["sw", 1], "type": "IMAGE"}),
            ],
        )

    out_a = Executor(_project("a")).execute(_workflow(0), target_nodes=["sw"])
    assert out_a.status == "completed", out_a.error
    assert out_a.outputs["sw"].get("path") == "assets/samples/Fort-Zeelandia.png"

    out_b = Executor(_project("b")).execute(_workflow(1), target_nodes=["sw"])
    assert out_b.status == "completed", out_b.error
    assert out_b.outputs["sw"]["type"] == "IMAGE"
    assert out_b.outputs["sw"].get("path") != "assets/samples/Fort-Zeelandia.png"
    assert (tmp_path / "b" / str(out_b.outputs["sw"]["path"])).is_file()
