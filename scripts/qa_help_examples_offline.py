#!/usr/bin/env python3
"""Execute expanded Help examples that only use offline (non-AI) nodes."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "assets" / "samples"

OFFLINE_TYPES = {
    "Amplifier",
    "Attenuator",
    "AutomationApply",
    "AutomationToMIDI",
    "Benchmark",
    "ChannelConvert",
    "ChannelMerge",
    "Clock",
    "Comparator",
    "ControlCurve",
    "Envelope",
    "Filter",
    "Float",
    "FloatMath",
    "FloatRoute",
    "LFO",
    "LoadAudio",
    "LoadImage",
    "LoadMIDI",
    "LoadVideo",
    "Logic",
    "MIDINoteGate",
    "MIDIToFloat",
    "MatrixMixer",
    "Meter",
    "Mix",
    "ModuleInlet",
    "ModuleOutlet",
    "MultichannelNormalize",
    "MuxVideo",
    "NoiseGenerator",
    "Normalize",
    "Note",
    "Oscillator",
    "Pan",
    "PreviewAudio",
    "PreviewImage",
    "PreviewMidi",
    "SynthMidi",
    "PreviewVideo",
    "Prompt",
    "Quantizer",
    "Resample",
    "Reverb",
    "SampleAndHold",
    "SaveAudio",
    "SaveImage",
    "SaveMidi",
    "SaveVideo",
    "SignalGenerator",
    "SplitVideo",
    "Transcode",
    "Trim",
}


def dump_expanded_patches() -> list[dict]:
    script = r"""
import { writeFileSync } from "node:fs";
import {
  applyMinimalPatchToCanvas,
  getMinimalPatch,
  listCuratedMinimalPatchTypes,
} from "./src/nodeMinimalPatches.ts";

const curated = listCuratedMinimalPatchTypes();
const out = [];
for (const type of curated) {
  const patch = getMinimalPatch(type);
  if (!patch) continue;
  const base = {
    schema_version: "1.0.0",
    groovy_version: "0.1.0",
    id: "wf",
    metadata: { title: type },
    nodes: [{ id: "dropped", type, pos: { x: 240, y: 120 }, widgets: {} }],
    links: [],
    groups: [],
  };
  const { workflow, focusNodeId, expanded } = applyMinimalPatchToCanvas(
    base,
    patch,
    { x: 240, y: 120 },
    { expandNodeId: "dropped" },
  );
  out.push({ type, expanded, focusNodeId, workflow });
}
writeFileSync(process.argv[2], JSON.stringify(out));
"""
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "expanded.json"
        ts_path = Path(tmp) / "dump.mts"
        ts_path.write_text(script)
        # Run via vitest/vite-node from apps/studio for TS path aliases.
        cmd = [
            "npx",
            "--yes",
            "tsx",
            "-e",
            script.replace("./src/nodeMinimalPatches.ts", str(ROOT / "apps/studio/src/nodeMinimalPatches.ts")),
            str(out_path),
        ]
        # Prefer direct import through vitest node environment.
        dump_js = ROOT / "apps/studio" / "scripts" / "_dump_help_expanded.mjs"
        dump_js.parent.mkdir(parents=True, exist_ok=True)
        dump_js.write_text(
            """
import { writeFileSync } from "node:fs";
import {
  applyMinimalPatchToCanvas,
  getMinimalPatch,
  listCuratedMinimalPatchTypes,
} from "../src/nodeMinimalPatches.ts";

const outPath = process.argv[2];
const curated = listCuratedMinimalPatchTypes();
const out = [];
for (const type of curated) {
  const patch = getMinimalPatch(type);
  if (!patch) continue;
  const base = {
    schema_version: "1.0.0",
    groovy_version: "0.1.0",
    id: "wf",
    metadata: { title: type },
    nodes: [{ id: "dropped", type, pos: { x: 240, y: 120 }, widgets: {} }],
    links: [],
    groups: [],
  };
  const { workflow, focusNodeId, expanded } = applyMinimalPatchToCanvas(
    base,
    patch,
    { x: 240, y: 120 },
    { expandNodeId: "dropped" },
  );
  out.push({ type, expanded, focusNodeId, workflow });
}
writeFileSync(outPath, JSON.stringify(out));
"""
        )
        result = subprocess.run(
            ["npx", "tsx", str(dump_js), str(out_path)],
            cwd=ROOT / "apps/studio",
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            raise SystemExit(f"dump failed: {result.returncode}")
        return json.loads(out_path.read_text())


def seed_project(project: Path, workflow: dict) -> None:
    dest = project / "assets" / "samples"
    dest.mkdir(parents=True, exist_ok=True)
    needed = set()
    for node in workflow.get("nodes") or []:
        path = (node.get("widgets") or {}).get("path")
        if isinstance(path, str) and path.startswith("assets/samples/"):
            needed.add(Path(path).name)
    for name in needed:
        src = SAMPLES / name
        if src.is_file():
            shutil.copy2(src, dest / name)


def main() -> int:
    from groovy.executor import Executor
    from groovy.node import NODE_REGISTRY
    from groovy.nodes.ai import register_all as register_ai
    from groovy.nodes.core import register_all as register_core
    from groovy.schema.models import Link, NodeInstance, Workflow, WorkflowMetadata
    from groovy.schema.validate import validate_workflow

    register_core()
    register_ai()

    patches = dump_expanded_patches()
    offline = []
    skipped = []
    for item in patches:
        types = {n["type"] for n in item["workflow"]["nodes"]}
        if types <= OFFLINE_TYPES:
            offline.append(item)
        else:
            skipped.append(item["type"])

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for item in offline:
            name = item["type"]
            wf_raw = item["workflow"]
            nodes = [
                NodeInstance(
                    id=n["id"],
                    type=n["type"],
                    pos=n.get("pos") or {"x": 0, "y": 0},
                    widgets=n.get("widgets") or {},
                )
                for n in wf_raw["nodes"]
            ]
            links = [
                Link(
                    id=edge["id"],
                    **{
                        "from": list(edge["from"]),
                        "to": list(edge["to"]),
                        "type": edge["type"],
                    },
                )
                for edge in wf_raw.get("links") or []
            ]
            workflow = Workflow(
                schema_version="1.0.0",
                groovy_version="0.1.0",
                id=f"help-expand-{name}",
                metadata=WorkflowMetadata(title=name),
                nodes=nodes,
                links=links,
            )
            validation = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
            if not validation.valid:
                failures.append(f"{name} invalid: {[e.message for e in validation.errors]}")
                continue
            project = tmp_path / name
            seed_project(project, wf_raw)
            # Prefer a terminal Preview*/Save* if present; else focus.
            targets = [item["focusNodeId"]]
            for node in reversed(nodes):
                if node.type in {
                    "PreviewAudio",
                    "PreviewImage",
                    "PreviewVideo",
                    "SaveAudio",
                    "SaveImage",
                    "SaveMidi",
                    "SaveVideo",
                    "Benchmark",
                }:
                    targets = [node.id]
                    break
            result = Executor(project).execute(workflow, target_nodes=targets)
            if result.status != "completed":
                failures.append(f"{name}: {result.error}")
            else:
                print(f"OK {name}")

    print(f"offline={len(offline)} skipped_ai={len(skipped)}")
    if failures:
        print("FAILURES:")
        for row in failures:
            print(" -", row)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
