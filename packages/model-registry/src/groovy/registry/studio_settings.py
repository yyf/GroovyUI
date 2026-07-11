from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class StudioSettingsStore:
    def __init__(self, project_dir: Path) -> None:
        self.path = project_dir / ".groovy" / "studio_settings.json"
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

    def public_view(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = data if data is not None else self.load()
        token = self.hf_token(raw)
        return {
            "hf_token_set": bool(token),
            "hf_token_source": (
                "environment"
                if os.environ.get("HF_TOKEN", "").strip()
                else ("settings" if raw.get("hf_token") else None)
            ),
        }

    def hf_token(self, data: dict[str, Any] | None = None) -> str | None:
        env = os.environ.get("HF_TOKEN", "").strip()
        if env:
            return env
        raw = data if data is not None else self.load()
        token = str(raw.get("hf_token", "")).strip()
        return token or None
