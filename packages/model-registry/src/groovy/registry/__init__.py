from __future__ import annotations

from groovy.registry.catalog import ModelCatalog
from groovy.registry.installer import ModelInstaller
from groovy.registry.store import InstallStore

__all__ = ["ModelCatalog", "ModelInstaller", "InstallStore", "ModelRegistry"]


class ModelRegistry:
    def __init__(self, project_dir) -> None:
        from pathlib import Path

        self.project_dir = Path(project_dir).resolve()
        overlay_path = self.project_dir / ".groovy" / "registry" / "catalog_overlay.json"
        self.catalog = ModelCatalog(overlay_path=overlay_path)
        self.store = InstallStore(self.project_dir)
        self.installer = ModelInstaller(self.catalog, self.store, self.project_dir)
        self.draft_dir = self.project_dir / ".groovy" / "registry" / "drafts"
        self.overlay_path = overlay_path
