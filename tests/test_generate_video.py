"""GenerateVideo + LTX-Video registry wiring and text-to-video template."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from groovy.executor import Executor
from groovy.executor.media_io import ffmpeg_available
from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.node import NODE_REGISTRY
from groovy.registry import ModelRegistry
from groovy.registry.catalog import ModelCatalog
from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata
from groovy.schema.validate import validate_workflow
from template_fixtures import require_template

register_core()
register_ai()


def _video_slot(output: dict) -> dict:
    """GenerateVideo returns MULTI (VIDEO + GENERATE_LOG); accept either shape."""
    if output.get("type") == "MULTI":
        return next(slot for slot in output["outputs"] if slot.get("type") == "VIDEO")
    assert output.get("type") == "VIDEO"
    return output


def test_generate_video_lists_ltx_video() -> None:
    assert "GenerateVideo" in NODE_REGISTRY
    models = NODE_REGISTRY["GenerateVideo"].COMPATIBLE_MODELS
    assert "ltx-2.3-q4" in models
    assert "ltx-video" in models
    assert "ltx-2.5" in models
    assert "wan-2.2-ti2v-5b" in models
    assert NODE_REGISTRY["GenerateVideo"].RETURN_TYPES == ("VIDEO", "GENERATE_LOG")
    assert NODE_REGISTRY["GenerateVideo"].OUTPUT_NAMES == ("video", "log")
    assert "SaveGenerateLog" in NODE_REGISTRY
    assert NODE_REGISTRY["SaveGenerateLog"].RETURN_TYPES == ("STRING",)
    assert NODE_REGISTRY["GenerateVideo"].INPUT_TYPES()["required"]["model"][1]["default"] == "ltx-2.3-q4"
    assert NODE_REGISTRY["GenerateVideo"].INPUT_TYPES()["optional"]["image"][0] == "IMAGE"
    assert NODE_REGISTRY["GenerateVideo"].INPUT_TYPES()["optional"]["video"][0] == "VIDEO"
    assert "LoadImage" in NODE_REGISTRY
    assert NODE_REGISTRY["LoadImage"].RETURN_TYPES == ("IMAGE",)


def test_load_image_and_optional_wire_to_generate_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LoadImage → GenerateVideo.image is optional; stub T2V still completes with image wired."""
    if not ffmpeg_available():
        pytest.skip("ffmpeg not on PATH")
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")

    assets = tmp_path / "assets" / "uploads"
    assets.mkdir(parents=True)
    # Minimal valid 1×1 PNG
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    (assets / "ref.png").write_bytes(png)

    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.0.0",
        id="generate-video-i2v-optional",
        metadata=WorkflowMetadata(title="generate-video-i2v-optional"),
        nodes=[
            NodeInstance(
                id="img",
                type="LoadImage",
                pos={"x": 0, "y": 0},
                widgets={"path": "assets/uploads/ref.png"},
            ),
            NodeInstance(
                id="n1",
                type="GenerateVideo",
                pos={"x": 240, "y": 0},
                widgets={
                    "model": "ltx-video",
                    "prompt": "animate the still",
                    "duration": 1.0,
                    "width": 320,
                    "height": 180,
                    "seed": 2,
                },
            ),
            NodeInstance(id="n2", type="PreviewVideo", pos={"x": 480, "y": 0}, widgets={}),
        ],
        links=[
            Link(id="l-img", **{"from": ["img", 0], "to": ["n1", 1], "type": "IMAGE"}),
            Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "VIDEO"}),
        ],
    )
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]
    registry = ModelRegistry(tmp_path)
    assert registry.installer.install("ltx-video").status == "ready"
    out = Executor(tmp_path).execute(workflow, target_nodes=["n2"])
    assert out.status == "completed", out.error
    assert out.outputs["img"]["type"] == "IMAGE"
    assert out.outputs["img"]["path"] == "assets/uploads/ref.png"
    assert _video_slot(out.outputs["n1"])["type"] == "VIDEO"


def test_optional_video_reference_wire_to_generate_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LoadVideo / ScanProcessor-style VIDEO → GenerateVideo.video validates and runs (stub)."""
    if not ffmpeg_available():
        pytest.skip("ffmpeg not on PATH")
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")

    sample = Path(__file__).resolve().parents[1] / "assets" / "samples" / "video480p.mov"
    if not sample.is_file():
        pytest.skip("assets/samples/video480p.mov not present")
    dest = tmp_path / "assets" / "samples" / "video480p.mov"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(sample.read_bytes())

    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.0.0",
        id="generate-video-vref-optional",
        metadata=WorkflowMetadata(title="generate-video-vref-optional"),
        nodes=[
            NodeInstance(
                id="vid",
                type="LoadVideo",
                pos={"x": 0, "y": 0},
                widgets={"path": "assets/samples/video480p.mov"},
            ),
            NodeInstance(
                id="n1",
                type="GenerateVideo",
                pos={"x": 240, "y": 0},
                widgets={
                    "model": "ltx-video",
                    "prompt": "restyle the reference clip",
                    "duration": 1.0,
                    "width": 320,
                    "height": 180,
                    "seed": 3,
                    "image_strength": 0.85,
                },
            ),
            NodeInstance(id="n2", type="PreviewVideo", pos={"x": 480, "y": 0}, widgets={}),
        ],
        links=[
            # GenerateVideo.video is slot 2 (text=0, image=1, video=2)
            Link(id="l-vid", **{"from": ["vid", 0], "to": ["n1", 2], "type": "VIDEO"}),
            Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "VIDEO"}),
        ],
    )
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]
    registry = ModelRegistry(tmp_path)
    assert registry.installer.install("ltx-video").status == "ready"
    out = Executor(tmp_path).execute(workflow, target_nodes=["n2"])
    assert out.status == "completed", out.error
    assert out.outputs["vid"]["type"] == "VIDEO"
    assert _video_slot(out.outputs["n1"])["type"] == "VIDEO"


def test_ltx_23_q4_seed_entry() -> None:
    from groovy.registry.compute import resolve_compute

    manifest = ModelCatalog().get("ltx-2.3-q4")
    assert manifest is not None
    assert manifest.status == "published"
    assert manifest.install.dev_stub is False
    assert "GenerateVideo" in manifest.compatible_nodes
    assert "text-to-video" in manifest.task_types
    assert "mlx" in manifest.tags
    assert manifest.hf_repo == "dgrauet/ltx-2.3-mlx-q4"
    assert manifest.download_size_mb_estimate >= 10_000
    resolved = resolve_compute(manifest)
    assert "apple" in resolved["presets"]
    assert "cuda" not in resolved["presets"] or resolved.get("requires_cuda") is False


def test_ltx_video_seed_entry() -> None:
    from groovy.registry.compute import resolve_compute

    manifest = ModelCatalog().get("ltx-video")
    assert manifest is not None
    assert manifest.status == "published"
    assert manifest.install.dev_stub is True
    assert "GenerateVideo" in manifest.compatible_nodes
    assert "text-to-video" in manifest.task_types
    assert "video" in manifest.tags
    assert manifest.license.commercial_ok is True
    assert manifest.vram_gb_estimate <= 2
    assert manifest.download_size_mb_estimate <= 50
    assert manifest.compute is not None
    assert manifest.compute.requires_cuda is False
    resolved = resolve_compute(manifest)
    assert "apple" in resolved["presets"]
    assert "cpu" in resolved["presets"]


def test_catalog_search_video_returns_t2v() -> None:
    catalog = ModelCatalog()
    ids = {m.id for m in catalog.search("video")}
    assert "ltx-2.3-q4" in ids
    assert "ltx-video" in ids
    assert "ltx-2.5" in ids
    assert "wan-2.2-ti2v-5b" in ids
    t2v = {m.id for m in catalog.search("", task_type="text-to-video")}
    assert "ltx-2.3-q4" in t2v
    assert "ltx-video" in t2v
    assert "ltx-2.5" in t2v
    assert "minimax-h3" in t2v


def test_ltx_video_mac_demo_works_without_stub_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MacBook demo model must render under Inference=Real (no GROOVY_INFERENCE_STUB)."""
    if not ffmpeg_available():
        pytest.skip("ffmpeg not on PATH")
    monkeypatch.delenv("GROOVY_INFERENCE_STUB", raising=False)

    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.0.0",
        id="generate-video-mac-demo",
        metadata=WorkflowMetadata(title="generate-video-mac-demo"),
        nodes=[
            NodeInstance(
                id="n1",
                type="GenerateVideo",
                pos={"x": 0, "y": 0},
                widgets={
                    "model": "ltx-video",
                    "prompt": "calm ocean at sunset",
                    "duration": 1.0,
                    "width": 320,
                    "height": 180,
                    "seed": 3,
                },
            ),
            NodeInstance(id="n2", type="PreviewVideo", pos={"x": 280, "y": 0}, widgets={}),
        ],
        links=[
            Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "VIDEO"}),
        ],
    )
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]
    registry = ModelRegistry(tmp_path)
    assert registry.installer.install("ltx-video").status == "ready"
    out = Executor(tmp_path).execute(workflow, target_nodes=["n2"])
    assert out.status == "completed", out.error
    video = _video_slot(out.outputs["n1"])
    assert video["type"] == "VIDEO"
    assert (tmp_path / video["path"]).is_file()


def test_generate_video_writes_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VIDEO outputs must write cache provenance so Compliance / Node Helper fill."""
    from groovy.executor.provenance import summarize_workflow_outputs

    if not ffmpeg_available():
        pytest.skip("ffmpeg not on PATH")
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")

    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.0.0",
        id="generate-video-provenance",
        metadata=WorkflowMetadata(title="generate-video-provenance"),
        nodes=[
            NodeInstance(
                id="n1",
                type="GenerateVideo",
                pos={"x": 0, "y": 0},
                widgets={
                    "model": "ltx-video",
                    "prompt": "ocean sunset",
                    "duration": 1.0,
                    "width": 320,
                    "height": 180,
                    "seed": 9,
                },
            ),
            NodeInstance(id="n2", type="PreviewVideo", pos={"x": 280, "y": 0}, widgets={}),
            NodeInstance(
                id="n3",
                type="SaveVideo",
                pos={"x": 560, "y": 0},
                widgets={"path": "exports", "filename": "prov.mp4"},
            ),
        ],
        links=[
            Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "VIDEO"}),
            Link(id="l2", **{"from": ["n2", 0], "to": ["n3", 0], "type": "VIDEO"}),
        ],
    )
    registry = ModelRegistry(tmp_path)
    assert registry.installer.install("ltx-video").status == "ready"
    executor = Executor(
        tmp_path,
        model_metadata_resolver=lambda mid: {"name": "LTX path demo", "version": "0"},
    )
    out = executor.execute(workflow, target_nodes=["n3"])
    assert out.status == "completed", out.error

    video_id = _video_slot(out.outputs["n1"])["video_id"]
    assert video_id
    record = executor.cache.read_provenance(video_id)
    assert record is not None
    assert record["contribution"]["class"] == "ai_generated"
    assert record["node"]["node_type"] == "GenerateVideo"
    assert any(m.get("registry_id") == "ltx-video" for m in record.get("models") or [])

    summary = summarize_workflow_outputs(executor.cache, out.outputs, target_node_id="n2")
    assert summary["contains_ai"] is True
    assert any(e["node_id"] == "n1" for e in summary["entries"])
    assert any(e["node_id"] == "n2" for e in summary["entries"])
    n1_entry = next(e for e in summary["entries"] if e["node_id"] == "n1")
    assert len(n1_entry["chain"]) >= 1
    assert n1_entry["lineage"]["nodes"]
    assert out.outputs["n3"].get("provenance_path")


def test_generate_video_cache_hit_backfills_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-fix VIDEO node-cache hits must still grow a provenance sidecar on re-render."""
    from groovy.executor.provenance import summarize_workflow_outputs

    if not ffmpeg_available():
        pytest.skip("ffmpeg not on PATH")
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")

    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.0.0",
        id="generate-video-cache-prov",
        metadata=WorkflowMetadata(title="generate-video-cache-prov"),
        nodes=[
            NodeInstance(
                id="n1",
                type="GenerateVideo",
                pos={"x": 0, "y": 0},
                widgets={
                    "model": "ltx-video",
                    "prompt": "ocean sunset",
                    "duration": 1.0,
                    "width": 320,
                    "height": 180,
                    "seed": 11,
                },
            ),
            NodeInstance(id="n2", type="PreviewVideo", pos={"x": 280, "y": 0}, widgets={}),
        ],
        links=[
            Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "VIDEO"}),
        ],
    )
    registry = ModelRegistry(tmp_path)
    assert registry.installer.install("ltx-video").status == "ready"
    executor = Executor(tmp_path)
    first = executor.execute(workflow, target_nodes=["n2"])
    assert first.status == "completed", first.error
    video_id = _video_slot(first.outputs["n1"])["video_id"]
    assert video_id
    # Simulate a clip rendered before VIDEO provenance existed.
    prov_path = executor.cache.cache_dir / f"{video_id}.provenance.json"
    assert prov_path.is_file()
    prov_path.unlink()
    assert executor.cache.read_provenance(video_id) is None

    second = executor.execute(workflow, target_nodes=["n2"])
    assert second.status == "completed", second.error
    assert _video_slot(second.outputs["n1"])["video_id"] == video_id
    record = executor.cache.read_provenance(video_id)
    assert record is not None
    assert record["contribution"]["class"] == "ai_generated"
    summary = summarize_workflow_outputs(executor.cache, second.outputs, target_node_id="n1")
    focus = next(e for e in summary["entries"] if e["node_id"] == "n1")
    assert focus["lineage"]["nodes"]


def test_generate_video_stub_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not ffmpeg_available():
        pytest.skip("ffmpeg not on PATH")
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")

    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.0.0",
        id="generate-video-stub",
        metadata=WorkflowMetadata(title="generate-video-stub"),
        nodes=[
            NodeInstance(
                id="n0",
                type="Prompt",
                pos={"x": 0, "y": 0},
                widgets={"text": "ocean sunset", "language": "en"},
            ),
            NodeInstance(
                id="n1",
                type="GenerateVideo",
                pos={"x": 240, "y": 0},
                widgets={
                    "model": "ltx-video",
                    "prompt": "ocean sunset",
                    "duration": 1.0,
                    "width": 320,
                    "height": 180,
                    "seed": 7,
                },
            ),
            NodeInstance(id="n2", type="PreviewVideo", pos={"x": 480, "y": 0}, widgets={}),
        ],
        links=[
            Link(id="l0", **{"from": ["n0", 0], "to": ["n1", 0], "type": "TEXT"}),
            Link(id="l1", **{"from": ["n1", 0], "to": ["n2", 0], "type": "VIDEO"}),
        ],
    )
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    registry = ModelRegistry(tmp_path)
    state = registry.installer.install("ltx-video")
    assert state.status == "ready", state.error

    out = Executor(tmp_path).execute(workflow, target_nodes=["n2"])
    assert out.status == "completed", out.error
    video = _video_slot(out.outputs["n1"])
    assert video["type"] == "VIDEO"
    assert out.outputs["n2"]["type"] == "VIDEO"
    clip_path = tmp_path / video["path"]
    assert clip_path.is_file()
    assert clip_path.stat().st_size > 0


def test_text_to_video_template_schema_and_stub_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not ffmpeg_available():
        pytest.skip("ffmpeg not on PATH")
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    path = require_template("text-to-video")
    data = json.loads(path.read_text())
    assert "featured" in data["metadata"]["tags"]
    assert "text-to-video" in data["metadata"]["tags"]
    gen = next(node for node in data["nodes"] if node["type"] == "GenerateVideo")
    assert gen["widgets"]["model"] == "ltx-2.3-q4"
    assert "Pointillism" in str(gen["widgets"].get("prompt", ""))
    assert "ambient city soundscape" in str(gen["widgets"].get("prompt", ""))
    assert 0.0 < float(gen["widgets"].get("image_strength", 1.0)) <= 1.0
    load = next(node for node in data["nodes"] if node["type"] == "LoadImage")
    assert load["widgets"].get("path") == "assets/samples/Fort-Zeelandia.png"
    gen_img = next(node for node in data["nodes"] if node["type"] == "GenerateImage")
    assert gen_img["widgets"]["model"] == "flux-klein-4b"
    switch = next(node for node in data["nodes"] if node["type"] == "SwitchImage")
    assert int(switch["widgets"].get("select", 0)) == 1
    assert any(node["type"] == "PreviewImage" for node in data["nodes"])
    assert any(node["type"] == "SaveImage" for node in data["nodes"])
    assert any(
        link["from"] == ["n-genimg", 0] and link["to"] == ["n-preview-img", 0] and link["type"] == "IMAGE"
        for link in data["links"]
    ), "GenerateImage must wire to PreviewImage"
    assert any(
        link["from"] == ["n-genimg", 0] and link["to"] == ["n-save-img", 0] and link["type"] == "IMAGE"
        for link in data["links"]
    ), "GenerateImage must wire to SaveImage"
    save_img = next(node for node in data["nodes"] if node["type"] == "SaveImage")
    assert save_img["widgets"].get("filename") == "text-to-video-still.png"
    prompts = [node for node in data["nodes"] if node["type"] == "Prompt"]
    assert len(prompts) >= 2
    video_prompt = next(node for node in prompts if node["id"] == "n0")
    image_prompt = next(node for node in prompts if node["id"] == "n-img-prompt")
    assert "Pointillism" in str(video_prompt["widgets"].get("text", ""))
    assert "documentary still" in str(image_prompt["widgets"].get("text", ""))
    assert video_prompt["widgets"]["text"] != image_prompt["widgets"]["text"]
    note = next(node for node in data["nodes"] if node["type"] == "Note")
    # Note sits below the graph so its 420px width does not cover GenerateVideo.
    assert float(note["pos"]["y"]) >= 400.0
    assert any(node["type"] == "Prompt" for node in data["nodes"])
    assert any(node["type"] == "PreviewVideo" for node in data["nodes"])
    assert any(node["type"] == "SaveVideo" for node in data["nodes"])
    assert any(node["type"] == "SaveGenerateLog" for node in data["nodes"])
    save = next(node for node in data["nodes"] if node["type"] == "SaveVideo")
    assert save["widgets"].get("filename") == "text-to-video.mp4"
    gen_inputs = NODE_REGISTRY["GenerateVideo"].INPUT_TYPES()["optional"]
    assert "image" in gen_inputs
    assert gen_inputs["image"][0] == "IMAGE"
    assert "video" in gen_inputs
    assert gen_inputs["video"][0] == "VIDEO"
    assert "image_strength" in gen_inputs
    assert "GenerateImage" in NODE_REGISTRY
    assert "SwitchImage" in NODE_REGISTRY
    assert any(
        link["from"] == ["n-img", 0] and link["to"] == ["n-switch", 0] and link["type"] == "IMAGE"
        for link in data["links"]
    ), "LoadImage must wire to SwitchImage.a"
    assert any(
        link["from"] == ["n-img-prompt", 0] and link["to"] == ["n-genimg", 0] and link["type"] == "TEXT"
        for link in data["links"]
    ), "Image Prompt must wire to GenerateImage (separate from video Prompt)"
    assert not any(
        link["from"] == ["n0", 0] and link["to"] == ["n-genimg", 0]
        for link in data["links"]
    ), "Video Prompt must not feed GenerateImage"
    assert any(
        link["from"] == ["n-genimg", 0] and link["to"] == ["n-switch", 1] and link["type"] == "IMAGE"
        for link in data["links"]
    ), "GenerateImage must wire to SwitchImage.b"
    assert any(
        link["from"] == ["n-switch", 0] and link["to"] == ["n1", 1] and link["type"] == "IMAGE"
        for link in data["links"]
    ), "SwitchImage must wire to GenerateVideo.image"
    assert any(
        link["from"] == ["n1", 1]
        and link["to"] == ["n-log", 0]
        and link["type"] == "GENERATE_LOG"
        for link in data["links"]
    ), "GenerateVideo.log must wire to SaveGenerateLog"

    # Stub project needs the bundled still for LoadImage.
    sample_src = Path(__file__).resolve().parents[1] / "assets" / "samples" / "Fort-Zeelandia.png"
    sample_dst = tmp_path / "assets" / "samples" / "Fort-Zeelandia.png"
    sample_dst.parent.mkdir(parents=True, exist_ok=True)
    sample_dst.write_bytes(sample_src.read_bytes())

    workflow = Workflow.model_validate(data)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    assert result.valid, [e.message for e in result.errors]

    # Stub env: Real MLX / mflux weights are optional; stub still produces PreviewVideo + PreviewImage.
    # select=1 → SwitchImage keeps GenerateImage (prunes LoadImage).
    registry = ModelRegistry(tmp_path)
    registry.installer.install("ltx-2.3-q4")
    registry.installer.install("flux-klein-4b")
    out = Executor(tmp_path).execute(
        workflow,
        target_nodes=["n3", "n-log", "n-preview-img", "n-save-img", "n-img-log"],
    )
    assert out.status == "completed", out.error
    assert "n-img" not in out.outputs
    assert out.outputs["n-genimg"]["type"] == "MULTI"
    assert out.outputs["n-genimg"]["outputs"][0]["type"] == "IMAGE"
    assert out.outputs["n-genimg"]["outputs"][1]["type"] == "GENERATE_LOG"
    assert out.outputs["n-genimg"]["outputs"][1].get("generate_log_id")
    assert out.outputs["n-preview-img"]["type"] == "IMAGE"
    assert out.outputs["n-save-img"]["type"] == "STRING"
    assert out.outputs["n-save-img"].get("path")
    assert out.outputs["n-switch"]["type"] == "IMAGE"
    assert out.outputs["n-switch"].get("path") == out.outputs["n-genimg"]["outputs"][0].get("path")
    assert out.outputs["n-img-log"]["type"] == "STRING"
    assert out.outputs["n-img-log"].get("path")
    assert out.outputs["n1"]["type"] == "MULTI"
    assert out.outputs["n1"]["outputs"][0]["type"] == "VIDEO"
    assert out.outputs["n1"]["outputs"][1]["type"] == "GENERATE_LOG"
    assert out.outputs["n1"]["outputs"][1].get("generate_log_id")
    assert out.outputs["n2"]["type"] == "VIDEO"
    assert out.outputs["n3"]["type"] == "STRING"
    assert out.outputs["n3"].get("path")
    assert out.outputs["n-log"]["type"] == "STRING"
    log_rel = out.outputs["n-log"]["path"]
    assert str(log_rel).endswith(".json")
    log_path = tmp_path / str(log_rel)
    assert log_path.is_file()
    log_payload = json.loads(log_path.read_text())
    assert "Pointillism" in log_payload.get("prompt", "")
    assert log_payload.get("timing", {}).get("generate_ms") is not None
    assert log_payload.get("hardware", {}).get("accelerator")
    assert log_payload.get("model_config", {}).get("model") == "ltx-2.3-q4"
    assert log_payload.get("output", {}).get("format") == "mp4"
