from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

InferenceMode = Literal["real", "stub"]


def inference_stub_active(*, project_dir: Path | None = None) -> bool:
    """Whether AI nodes should use stub inference.

    Precedence:
    1. ``GROOVY_INFERENCE_STUB`` env ``1/true/yes`` → stub (CI / forced stub)
    2. ``GROOVY_INFERENCE_STUB`` env ``0/false/no`` → real (forced real)
    3. Project ``.groovy/studio_settings.json`` ``inference_mode`` (default ``real``)
    """
    env = os.environ.get("GROOVY_INFERENCE_STUB", "").strip().lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False
    root = project_dir
    if root is None:
        env_dir = os.environ.get("GROOVY_PROJECT_DIR", "").strip()
        if not env_dir:
            return False
        root = Path(env_dir)
    return StudioSettingsStore(root).inference_mode() == "stub"


class StudioSettingsStore:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir.resolve()
        self.path = self.project_dir / ".groovy" / "studio_settings.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except json.JSONDecodeError:
            return {}

    def save(self, patch: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        for key, value in patch.items():
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        self.path.write_text(json.dumps(data, indent=2))
        return self.public_view(data)

    def inference_mode(self, data: dict[str, Any] | None = None) -> InferenceMode:
        raw = data if data is not None else self.load()
        mode = str(raw.get("inference_mode", "real")).strip().lower()
        return "stub" if mode == "stub" else "real"

    def public_view(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = data if data is not None else self.load()
        token = self.hf_token(raw)
        mode = self.inference_mode(raw)
        env_stub = os.environ.get("GROOVY_INFERENCE_STUB", "").strip().lower()
        env_forces_stub = env_stub in ("1", "true", "yes")
        env_forces_real = env_stub in ("0", "false", "no")
        if env_forces_stub:
            effective = "stub"
            effective_source = "environment"
        elif env_forces_real:
            effective = "real"
            effective_source = "environment"
        else:
            effective = mode
            effective_source = "settings"
        cache_dir = self.project_dir / ".groovy" / "cache"
        return {
            "hf_token_set": bool(token),
            "hf_token_source": (
                "environment"
                if os.environ.get("HF_TOKEN", "").strip()
                else ("settings" if raw.get("hf_token") else None)
            ),
            "inference_mode": mode,
            "inference_effective": effective,
            "inference_effective_source": effective_source,
            "inference_stub_active": effective == "stub",
            "project_dir": str(self.project_dir),
            "cache_dir": str(cache_dir),
            "nodes_schema_url": "/api/nodes",
        }

    def hf_token(self, data: dict[str, Any] | None = None) -> str | None:
        env = os.environ.get("HF_TOKEN", "").strip()
        if env:
            return env
        raw = data if data is not None else self.load()
        token = str(raw.get("hf_token", "")).strip()
        return token or None
