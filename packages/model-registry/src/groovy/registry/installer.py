from __future__ import annotations

import time
from pathlib import Path

from groovy.registry.catalog import ModelCatalog
from groovy.registry.models import InstallState, ModelManifest
from groovy.registry.store import InstallStore


class ModelInstaller:
    def __init__(self, catalog: ModelCatalog, store: InstallStore, project_dir: Path) -> None:
        self.catalog = catalog
        self.store = store
        self.project_dir = project_dir

    def install(self, model_id: str) -> InstallState:
        manifest = self.catalog.get(model_id)
        if not manifest:
            return self.store.mark_failed(model_id, f"Unknown model: {model_id}")

        existing = self.store.get(model_id)
        if existing.status == "ready":
            return existing

        try:
            self.store.mark_progress(model_id, "downloading", 0.2)
            time.sleep(0.05)
            self.store.mark_progress(model_id, "verifying", 0.7)
            if manifest.install.dev_stub:
                return self.store.mark_ready(model_id)
            if not manifest.install.weights:
                return self.store.mark_ready(model_id)
            raise NotImplementedError("Weight download not implemented yet")
        except Exception as exc:
            return self.store.mark_failed(model_id, str(exc))

    def recovery_suggestions(self, model_id: str) -> dict:
        manifest = self.catalog.get(model_id)
        state = self.store.get(model_id)
        similar = self.catalog.similar(model_id) if manifest else []
        return {
            "model_id": model_id,
            "error": state.error,
            "summary": _human_error(state.error or ""),
            "similar_models": [_card(m, self.store.get(m.id)) for m in similar[:4]],
        }


def _human_error(error: str) -> str:
    lowered = error.lower()
    if "checksum" in lowered:
        return "Checksum mismatch — download may be corrupted."
    if "disk" in lowered or "space" in lowered:
        return "Not enough disk space for model weights."
    if "network" in lowered or "connection" in lowered:
        return "Network error while downloading model weights."
    if "cuda" in lowered or "gpu" in lowered:
        return "GPU/CUDA requirement not met for this model."
    return error or "Install failed for an unknown reason."


def _card(manifest: ModelManifest, state: InstallState) -> dict:
    return {
        "id": manifest.id,
        "name": manifest.name,
        "task_types": manifest.task_types,
        "license": manifest.license.model_dump(),
        "vram_gb_estimate": manifest.vram_gb_estimate,
        "install_status": state.status,
    }
