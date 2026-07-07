from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from groovy.executor import Executor
from groovy.schema.models import Workflow


def run_batch_render(
    executor: Executor,
    workflow: Workflow,
    *,
    input_dir: str,
    file_glob: str = "*.{wav,flac,WAV,FLAC}",
    load_node_id: str | None = None,
    target_nodes: list[str] | None = None,
) -> dict[str, Any]:
    """Run workflow once per audio file in input_dir, patching LoadAudio path each time."""
    project_dir = executor.project_dir
    in_root = executor.cache.resolve_project_path(input_dir)
    if not in_root.is_dir():
        raise FileNotFoundError(f"INPUT_DIR_NOT_FOUND: {input_dir}")

    load_id = load_node_id or _first_load_audio_id(workflow)
    if not load_id:
        raise ValueError("No LoadAudio node found — set load_node_id explicitly.")

    patterns = [p.strip() for p in file_glob.split(",") if p.strip()]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(in_root.glob(pattern))
    files = sorted({f.resolve() for f in files if f.is_file()})

    runs: list[dict[str, Any]] = []
    for file_path in files:
        try:
            rel = file_path.relative_to(project_dir)
        except ValueError as exc:
            raise ValueError(f"Input file escapes project directory: {file_path}") from exc

        patched = _patch_load_path(workflow, load_id, rel.as_posix())
        result = executor.execute(patched, target_nodes=target_nodes)
        runs.append(
            {
                "input_path": rel.as_posix(),
                "status": result.status,
                "job_id": result.job_id,
                "outputs": result.outputs,
                "error": result.error,
                "manifest_path": result.manifest_path,
            }
        )

    completed = sum(1 for run in runs if run["status"] == "completed")
    return {
        "input_dir": input_dir,
        "file_glob": file_glob,
        "load_node_id": load_id,
        "total": len(runs),
        "completed": completed,
        "failed": len(runs) - completed,
        "runs": runs,
    }


def _first_load_audio_id(workflow: Workflow) -> str | None:
    for node in workflow.nodes:
        if node.type == "LoadAudio":
            return node.id
    return None


def _patch_load_path(workflow: Workflow, load_node_id: str, path: str) -> Workflow:
    data = json.loads(workflow.model_dump_json(by_alias=True))
    for node in data["nodes"]:
        if node["id"] == load_node_id:
            node.setdefault("widgets", {})["path"] = path
            break
    return Workflow.model_validate(data)
