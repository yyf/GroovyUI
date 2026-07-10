from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from groovy.executor.cancel import JobCancelled


def run_ai_worker(
    node_type: str,
    kwargs: dict[str, Any],
    project_dir: Path,
    *,
    timeout: int = 1200,
    cancel_check: Callable[[], bool] | None = None,
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
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(payload))
    proc.stdin.close()

    started = time.monotonic()
    while proc.poll() is None:
        if cancel_check and cancel_check():
            _terminate_worker(proc)
            raise JobCancelled()
        if time.monotonic() - started > timeout:
            _terminate_worker(proc)
            raise RuntimeError(f"AI worker timed out after {timeout}s")
        time.sleep(0.25)

    stdout = proc.stdout.read() if proc.stdout else ""
    stderr = proc.stderr.read() if proc.stderr else ""
    if proc.returncode != 0:
        err = stderr.strip() or stdout.strip() or "AI worker failed"
        raise RuntimeError(_clean_worker_error(err))
    data = _parse_worker_stdout(stdout)
    return data.get("outputs", [])


def _terminate_worker(proc: subprocess.Popen[str]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _parse_worker_stdout(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise RuntimeError("AI worker returned empty output")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise RuntimeError("AI worker returned invalid JSON")


def _serialize_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in kwargs.items():
        if hasattr(value, "stems"):
            out[key] = {"type": "STEMS", "stems_id": value.id}
        elif hasattr(value, "record") and hasattr(value, "id"):
            out[key] = {"type": "AUTHENTICITY", "authenticity_id": value.id}
        elif hasattr(value, "midi_kind") and hasattr(value, "id"):
            out[key] = {"type": "MIDI", "midi_id": value.id}
        elif hasattr(value, "values") and hasattr(value, "frame_count") and hasattr(value, "id"):
            out[key] = {"type": "AUTOMATION", "automation_id": value.id}
        elif hasattr(value, "objects") and hasattr(value, "beds"):
            out[key] = {"type": "OBA", "oba_id": value.id}
        elif hasattr(value, "layout_order") and hasattr(value, "channel_ordering"):
            out[key] = {"type": "AMBISONICS", "ambisonics_id": value.id}
        elif hasattr(value, "id") and hasattr(value, "frame_count") and hasattr(value, "sample_rate"):
            out[key] = {"type": "AUDIO", "cache_id": value.id}
            out[f"{key}_id"] = value.id
        else:
            out[key] = value
    if "audio" in kwargs and hasattr(kwargs["audio"], "id"):
        out["audio_id"] = kwargs["audio"].id
    if "stems" in kwargs and hasattr(kwargs["stems"], "id"):
        out["stems_id"] = kwargs["stems"].id
    if "midi" in kwargs and hasattr(kwargs["midi"], "midi_kind"):
        out["midi_id"] = kwargs["midi"].id
    if "reference_audio" in kwargs and hasattr(kwargs["reference_audio"], "id"):
        out["audio_id"] = kwargs["reference_audio"].id
    return out


def _clean_worker_error(stderr: str) -> str:
    text = stderr.strip()
    if not text:
        return "AI worker failed"

    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("RuntimeError:"):
            msg = stripped.removeprefix("RuntimeError:").strip()
            if msg and msg != "runtime.":
                return msg

    import re

    import_err = re.search(
        r"(ImportError|ModuleNotFoundError):(?:[^\n]|\n(?!Traceback|  File ))+",
        text,
        flags=re.IGNORECASE,
    )
    if import_err:
        return " ".join(import_err.group(0).split())

    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped.startswith(("OSError:", "ValueError:")):
            return stripped

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("Traceback"):
            continue
        if line.startswith("File "):
            continue
        if line in {"runtime.", "runtime", "ImportError:"}:
            continue
        if len(line) > 12:
            return line

    return lines[-1] if lines else "AI worker failed"
