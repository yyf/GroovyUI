from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from groovy.registry.models import InstallState


class InstallStore:
    def __init__(self, project_dir: Path) -> None:
        self.root = project_dir / ".groovy" / "models"
        self.root.mkdir(parents=True, exist_ok=True)
        self._state_path = self.root / "install_state.json"
        self._state: dict[str, InstallState] = {}
        self._load()

    def _load(self) -> None:
        if not self._state_path.exists():
            return
        raw = json.loads(self._state_path.read_text())
        self._state = {k: InstallState.model_validate(v) for k, v in raw.items()}

    def _save(self) -> None:
        payload = {k: v.model_dump() for k, v in self._state.items()}
        self._state_path.write_text(json.dumps(payload, indent=2))

    def get(self, model_id: str) -> InstallState:
        return self._state.get(model_id, InstallState(model_id=model_id))

    def all(self) -> dict[str, InstallState]:
        return dict(self._state)

    def update(self, state: InstallState) -> InstallState:
        self._state[state.model_id] = state
        self._save()
        return state

    def mark_ready(self, model_id: str, version: str = "0.1.0-dev") -> InstallState:
        state = InstallState(
            model_id=model_id,
            status="ready",
            version=version,
            progress=1.0,
            installed_at=datetime.now(UTC).isoformat(),
            error=None,
        )
        marker = self.root / model_id / "installed.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"model_id": model_id, "version": version}, indent=2))
        return self.update(state)

    def mark_failed(self, model_id: str, error: str) -> InstallState:
        state = self.get(model_id)
        state.status = "failed"
        state.error = error
        state.progress = 0.0
        return self.update(state)

    def mark_progress(self, model_id: str, status: str, progress: float) -> InstallState:
        state = self.get(model_id)
        state.status = status
        state.progress = progress
        state.error = None
        return self.update(state)
