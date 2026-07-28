from __future__ import annotations

import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from groovy.registry.catalog import ModelCatalog
from groovy.registry.download import (
    DownloadCancelled,
    DownloadError,
    copy_bundle_file,
    download_file,
)
from groovy.registry.models import InstallState, ModelManifest
from groovy.registry.store import InstallStore
from groovy.registry.studio_settings import StudioSettingsStore, inference_stub_active


class ModelInstaller:
    def __init__(self, catalog: ModelCatalog, store: InstallStore, project_dir: Path) -> None:
        self.catalog = catalog
        self.store = store
        self.project_dir = project_dir
        self._settings = StudioSettingsStore(project_dir)

    def install(
        self,
        model_id: str,
        *,
        cancel_check: Callable[[], bool] | None = None,
    ) -> InstallState:
        manifest = self.catalog.get(model_id)
        if not manifest:
            return self.store.mark_failed(model_id, f"Unknown model: {model_id}")

        existing = self.store.get(model_id)
        if (
            existing.status == "ready"
            and _imports_verified(manifest, project_dir=self.project_dir)
            and _weights_present(manifest, self.project_dir / ".groovy" / "models" / model_id)
        ):
            return existing

        def cancelled() -> bool:
            return bool(cancel_check and cancel_check())

        try:
            if cancelled():
                return self.store.mark_cancelled(model_id)
            self.store.mark_progress(model_id, "downloading", 0.05)
            model_dir = self.project_dir / ".groovy" / "models" / model_id
            model_dir.mkdir(parents=True, exist_ok=True)
            if manifest.install.dev_stub:
                time.sleep(0.05)
                if cancelled():
                    return self.store.mark_cancelled(model_id)
                self.store.mark_progress(model_id, "verifying", 0.7)
                return self.store.mark_ready(model_id)

            _install_python_deps(
                manifest,
                model_id,
                self.store,
                project_dir=self.project_dir,
                cancel_check=cancel_check,
            )

            weights = manifest.install.weights
            for index, weight in enumerate(weights):
                if cancelled():
                    return self.store.mark_cancelled(model_id)
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
                    cancel_check=cancel_check,
                )

            if cancelled():
                return self.store.mark_cancelled(model_id)
            self.store.mark_progress(model_id, "verifying", 0.92)
            _verify_imports(manifest, project_dir=self.project_dir)
            _verify_runtime(manifest, project_dir=self.project_dir)
            if manifest.install.weights or manifest.install.python_deps:
                return self.store.mark_ready(model_id)
            raise NotImplementedError("Weight download not configured")
        except DownloadCancelled:
            return self.store.mark_cancelled(model_id)
        except DownloadError as exc:
            return self.store.mark_failed(model_id, str(exc))
        except Exception as exc:
            return self.store.mark_failed(model_id, str(exc))

    def uninstall(self, model_id: str) -> dict[str, Any]:
        """Delete local weight files and reset install status.

        Does not uninstall shared Python packages from the environment.
        """
        model_dir = self.store.model_dir(model_id)
        freed_bytes = self.store.directory_size_bytes(model_dir) if model_dir.exists() else 0
        if model_dir.exists():
            shutil.rmtree(model_dir)
        state = self.store.clear(model_id)
        return {
            "model_id": model_id,
            "install": state.model_dump(),
            "freed_mb": round(freed_bytes / (1024 * 1024), 1),
            "models_used_mb": round(self.store.directory_size_bytes() / (1024 * 1024), 1),
            "models_dir": str(self.store.root),
            "python_packages_removed": False,
            "note": "Removed local model weights only; shared Python packages were left installed.",
        }

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
    cancel_check: Callable[[], bool] | None = None,
) -> None:
    if inference_stub_active(project_dir=project_dir):
        return
    deps = manifest.install.python_deps
    if not deps:
        return
    total = len(deps)
    for index, dep in enumerate(deps):
        if cancel_check and cancel_check():
            raise DownloadCancelled("Install cancelled before dependency install")
        package = str(dep.get("package", "")).strip()
        if not package:
            continue
        version = str(dep.get("version", "")).strip()
        requirement = f"{package}{version}" if version else package
        progress = 0.12 + (0.28 * (index + 1) / total)
        store.mark_progress(model_id, "downloading", progress)
        no_deps = bool(dep.get("no_deps"))
        _run_pip_install(requirement, no_deps=no_deps, cancel_check=cancel_check)
    # f5-tts (and occasionally other Hub packages) declare a dependency on an
    # unrelated PyPI package also named ``groovy``, which shadows this workspace.
    _purge_conflicting_pypi_groovy()


def purge_conflicting_pypi_groovy() -> bool:
    """Remove PyPI ``groovy`` if it shadows the GroovyUI workspace namespace.

    Gradio (and occasionally Hub packages) depend on an unrelated PyPI package also
    named ``groovy``, which occupies ``site-packages/groovy`` and breaks
    ``import groovy.nodes`` for the AI worker. Returns True when a purge ran.
    """
    try:
        import groovy
    except ImportError:
        return False
    path = (getattr(groovy, "__file__", None) or "").replace("\\", "/")
    if "/site-packages/groovy/" not in path and not path.endswith("/site-packages/groovy/__init__.py"):
        return False
    try:
        import groovy.nodes  # noqa: F401

        return False
    except ImportError:
        pass
    _run_pip_uninstall("groovy")
    return True


def _purge_conflicting_pypi_groovy() -> None:
    purge_conflicting_pypi_groovy()


def _run_pip_uninstall(package: str) -> None:
    if shutil.which("uv"):
        command = ["uv", "pip", "uninstall", "--python", sys.executable, package]
    else:
        command = [sys.executable, "-m", "pip", "uninstall", "-y", package]
    subprocess.run(command, check=False, capture_output=True, text=True)


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


def _run_pip_install(
    requirement: str,
    *,
    no_deps: bool = False,
    cancel_check: Callable[[], bool] | None = None,
) -> None:
    if shutil.which("uv"):
        # uv-managed venvs do not ship pip; uv pip targets the active interpreter.
        command = ["uv", "pip", "install", "--python", sys.executable]
    else:
        command = [sys.executable, "-m", "pip", "install"]
    if no_deps:
        command.append("--no-deps")
    command.append(requirement)
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        while proc.poll() is None:
            if cancel_check and cancel_check():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                raise DownloadCancelled(f"Install cancelled while installing {requirement}")
            time.sleep(0.4)
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            detail = (stderr or stdout or "package install failed").strip()
            raise RuntimeError(f"Failed to install {requirement}: {detail[:500]}")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def _weights_present(manifest: ModelManifest, model_dir: Path) -> bool:
    """True when every declared weight/bundle file exists under the model dir.

    Stub installs can leave status=ready with no files; upgrading a seed entry
    from ``dev_stub`` to real weights must re-enter the download path.
    """
    weights = manifest.install.weights
    if not weights:
        return True
    for weight in weights:
        filename = weight.get("filename")
        if not filename:
            bundle = weight.get("bundle")
            filename = str(bundle) if bundle else _filename_from_url(str(weight.get("url") or ""))
        if not filename or not (model_dir / filename).is_file():
            return False
    return True


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
