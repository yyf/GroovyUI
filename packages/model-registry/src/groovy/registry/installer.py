from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

from groovy.registry.catalog import ModelCatalog
from groovy.registry.download import DownloadError, copy_bundle_file, download_file
from groovy.registry.models import InstallState, ModelManifest
from groovy.registry.store import InstallStore
from groovy.registry.studio_settings import StudioSettingsStore, inference_stub_active


class ModelInstaller:
    def __init__(self, catalog: ModelCatalog, store: InstallStore, project_dir: Path) -> None:
        self.catalog = catalog
        self.store = store
        self.project_dir = project_dir
        self._settings = StudioSettingsStore(project_dir)

    def install(self, model_id: str) -> InstallState:
        manifest = self.catalog.get(model_id)
        if not manifest:
            return self.store.mark_failed(model_id, f"Unknown model: {model_id}")

        existing = self.store.get(model_id)
        if existing.status == "ready" and _imports_verified(manifest, project_dir=self.project_dir):
            return existing

        try:
            self.store.mark_progress(model_id, "downloading", 0.05)
            model_dir = self.project_dir / ".groovy" / "models" / model_id
            model_dir.mkdir(parents=True, exist_ok=True)
            if manifest.install.dev_stub:
                time.sleep(0.05)
                self.store.mark_progress(model_id, "verifying", 0.7)
                return self.store.mark_ready(model_id)

            _install_python_deps(manifest, model_id, self.store, project_dir=self.project_dir)

            weights = manifest.install.weights
            for index, weight in enumerate(weights):
                progress = 0.45 + (0.4 * (index + 1) / max(len(weights), 1))
                self.store.mark_progress(model_id, "downloading", progress)
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
                download_file(
                    url,
                    dest,
                    expected_sha256=weight.get("sha256"),
                    hf_token=self._settings.hf_token(),
                )

            self.store.mark_progress(model_id, "verifying", 0.92)
            _verify_imports(manifest, project_dir=self.project_dir)
            _verify_runtime(manifest, project_dir=self.project_dir)
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


def _install_python_deps(
    manifest: ModelManifest,
    model_id: str,
    store: InstallStore,
    *,
    project_dir: Path,
) -> None:
    if inference_stub_active(project_dir=project_dir):
        return
    deps = manifest.install.python_deps
    if not deps:
        return
    total = len(deps)
    for index, dep in enumerate(deps):
        package = str(dep.get("package", "")).strip()
        if not package:
            continue
        version = str(dep.get("version", "")).strip()
        requirement = f"{package}{version}" if version else package
        progress = 0.12 + (0.28 * (index + 1) / total)
        store.mark_progress(model_id, "downloading", progress)
        no_deps = bool(dep.get("no_deps"))
        _run_pip_install(requirement, no_deps=no_deps)


def _verify_runtime(manifest: ModelManifest, *, project_dir: Path | None = None) -> None:
    if inference_stub_active(project_dir=project_dir):
        return
    if manifest.install.dev_stub:
        return
    try:
        from groovy.nodes.ai.inference_env import model_inference_ready
    except ImportError:
        return
    if not model_inference_ready(manifest.id, dev_stub=False):
        raise RuntimeError(
            f"Inference runtime not ready for {manifest.id}. "
            "Reinstall from Model Browser (Cmd+K) — install pulls weights and Python deps automatically."
        )


def model_install_complete(
    manifest: ModelManifest,
    state: InstallState,
    *,
    project_dir: Path | None = None,
) -> bool:
    """True when registry install succeeded and runtime deps are importable."""
    if state.status != "ready":
        return False
    return _imports_verified(manifest, project_dir=project_dir)


def _imports_verified(manifest: ModelManifest, *, project_dir: Path | None = None) -> bool:
    if not _imports_verified_manifest(manifest, project_dir=project_dir):
        return False
    try:
        _verify_runtime(manifest, project_dir=project_dir)
        return True
    except RuntimeError:
        return False


def _imports_verified_manifest(
    manifest: ModelManifest, *, project_dir: Path | None = None
) -> bool:
    if not manifest.install.verify_imports:
        return True
    try:
        _verify_imports(manifest, project_dir=project_dir)
        return True
    except RuntimeError:
        return False


def _verify_imports(manifest: ModelManifest, *, project_dir: Path | None = None) -> None:
    if inference_stub_active(project_dir=project_dir):
        return
    missing: list[str] = []
    for module in manifest.install.verify_imports:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Inference packages not importable after install ({joined}). "
            "Reinstall from Model Browser (Cmd+K)."
        )


def _run_pip_install(requirement: str, *, no_deps: bool = False) -> None:
    if shutil.which("uv"):
        # uv-managed venvs do not ship pip; uv pip targets the active interpreter.
        command = ["uv", "pip", "install", "--python", sys.executable]
    else:
        command = [sys.executable, "-m", "pip", "install"]
    if no_deps:
        command.append("--no-deps")
    command.append(requirement)
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "package install failed").strip()
        raise RuntimeError(f"Failed to install {requirement}: {detail[:500]}")


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
    if "failed to install" in lowered or "pip install" in lowered:
        return "Python dependency install failed — retry from Model Browser (Cmd+K)."
    if "inference runtime not ready" in lowered or "not importable after install" in lowered:
        return "Python inference packages missing — reinstall from Model Browser (Cmd+K)."
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
