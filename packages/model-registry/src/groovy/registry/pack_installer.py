from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from groovy.registry.packs import NodePackManifest, get_pack


@dataclass
class PackInstallState:
    pack_id: str
    status: str
    version: str | None = None
    installed_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "status": self.status,
            "version": self.version,
            "installed_at": self.installed_at,
            "error": self.error,
        }


class PackInstaller:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.packs_dir = self.project_dir / ".groovy" / "packs"
        self.packs_dir.mkdir(parents=True, exist_ok=True)

    def list_installed(self) -> list[dict[str, Any]]:
        installed: list[dict[str, Any]] = []
        for path in sorted(self.packs_dir.glob("*/manifest.json")):
            data = json.loads(path.read_text())
            state_path = path.parent / "install_state.json"
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            installed.append({**data, **state})
        return installed

    def install(self, pack_id: str, *, consent: bool = True) -> PackInstallState:
        if not consent:
            return PackInstallState(pack_id=pack_id, status="rejected", error="User consent required")
        manifest = get_pack(pack_id)
        if not manifest:
            return PackInstallState(pack_id=pack_id, status="failed", error=f"Unknown pack: {pack_id}")

        dest_dir = self.packs_dir / pack_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "manifest.json").write_text(json.dumps(manifest.to_dict(), indent=2))
        installed_at = datetime.now(UTC).isoformat()
        state = PackInstallState(
            pack_id=pack_id,
            status="installed",
            version=manifest.version,
            installed_at=installed_at,
        )
        (dest_dir / "install_state.json").write_text(json.dumps(state.to_dict(), indent=2))
        return state

    def get_state(self, pack_id: str) -> PackInstallState | None:
        state_path = self.packs_dir / pack_id / "install_state.json"
        if not state_path.exists():
            return None
        data = json.loads(state_path.read_text())
        return PackInstallState(**data)
