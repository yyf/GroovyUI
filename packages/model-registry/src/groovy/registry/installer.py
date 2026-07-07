from __future__ import annotations

import time
from pathlib import Path

from groovy.registry.catalog import ModelCatalog
from groovy.registry.download import DownloadError, copy_bundle_file, download_file
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
            model_dir = self.project_dir / ".groovy" / "models" / model_id
            model_dir.mkdir(parents=True, exist_ok=True)
            if manifest.install.dev_stub:
                time.sleep(0.05)
                self.store.mark_progress(model_id, "verifying", 0.7)
                return self.store.mark_ready(model_id)
            for weight in manifest.install.weights:
                bundle = weight.get("bundle")
                if bundle:
                    filename = weight.get("filename") or str(bundle)
                    dest = model_dir / filename
                    copy_bundle_file(str(bundle), dest, expected_sha256=weight.get("sha256"))
                    continue
                url = weight.get("url")
                if not url:
                    continue
                filename = weight.get("filename") or _filename_from_url(url)
                dest = model_dir / filename
                download_file(url, dest, expected_sha256=weight.get("sha256"))
            self.store.mark_progress(model_id, "verifying", 0.9)
            if manifest.install.weights or manifest.install.python_deps:
                return self.store.mark_ready(model_id)
            raise NotImplementedError("Weight download not configured")
        except DownloadError as exc:
            return self.store.mark_failed(model_id, str(exc))
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


def _filename_from_url(url: str) -> str:
    from urllib.parse import urlparse

    path = urlparse(url).path
    return Path(path).name or "weights.bin"


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
