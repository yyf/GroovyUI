from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def run_ai_worker(
    node_type: str,
    kwargs: dict[str, Any],
    project_dir: Path,
    *,
    timeout: int = 1200,
) -> list[dict[str, Any]]:
    worker_cmd = shutil.which("groovy-ai-worker")
    if worker_cmd:
        cmd = [worker_cmd]
    else:
        cmd = [sys.executable, "-m", "groovy.nodes.ai.worker"]

    payload = {
        "node_type": node_type,
        "kwargs": _serialize_kwargs(kwargs),
        "project_dir": str(project_dir.resolve()),
    }
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip() or "AI worker failed"
        raise RuntimeError(_clean_worker_error(stderr))
    data = json.loads(proc.stdout)
    return data.get("outputs", [])


def _serialize_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in kwargs.items():
        if hasattr(value, "stems"):
            out[key] = {"type": "STEMS", "stems_id": value.id}
        elif hasattr(value, "id") and hasattr(value, "frame_count"):
            out[key] = {"type": "AUDIO", "cache_id": value.id}
            out[f"{key}_id"] = value.id
        else:
            out[key] = value
    if "audio" in kwargs and hasattr(kwargs["audio"], "id"):
        out["audio_id"] = kwargs["audio"].id
    if "stems" in kwargs and hasattr(kwargs["stems"], "id"):
        out["stems_id"] = kwargs["stems"].id
    return out


def _clean_worker_error(stderr: str) -> str:
    for line in reversed(stderr.strip().splitlines()):
        if line.startswith("RuntimeError:"):
            return line.removeprefix("RuntimeError:").strip()
    lines = [line for line in stderr.strip().splitlines() if line.strip()]
    return lines[-1] if lines else "AI worker failed"
