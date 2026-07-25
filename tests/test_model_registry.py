from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from groovy.registry import ModelRegistry
from groovy.registry.catalog import ModelCatalog
from groovy.registry.installer import _install_python_deps
from groovy.registry.models import InstallSpec, LicenseInfo, ModelManifest
from groovy.registry.store import InstallStore
import groovy.server.main as main
import groovy.registry.installer as installer_mod


def test_catalog_search_denoise() -> None:
    catalog = ModelCatalog()
    results = catalog.search("denoise podcast")
    ids = {m.id for m in results}
    assert "deepfilternet-v3" in ids


def test_model_install_dev_stub(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    state = registry.installer.install("cosyvoice-300m")
    assert state.status == "ready"
    marker = tmp_path / ".groovy" / "models" / "cosyvoice-300m" / "installed.json"
    assert marker.exists()


def test_install_python_deps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []

    def fake_pip(requirement: str, *, no_deps: bool = False, cancel_check=None) -> None:
        calls.append((requirement, no_deps))

    monkeypatch.delenv("GROOVY_INFERENCE_STUB", raising=False)
    monkeypatch.setattr("groovy.registry.installer._run_pip_install", fake_pip)
    monkeypatch.setattr("groovy.registry.installer._purge_conflicting_pypi_groovy", lambda: None)
    manifest = ModelManifest(
        id="test-deps",
        name="Test deps",
        description="",
        task_types=["denoise"],
        license=LicenseInfo(spdx="MIT", commercial_ok=True),
        install=InstallSpec(python_deps=[{"package": "DeepFilterNet-py312", "version": ">=0.5.7"}]),
    )
    store = InstallStore(tmp_path)
    _install_python_deps(manifest, "test-deps", store, project_dir=tmp_path)
    assert calls == [("DeepFilterNet-py312>=0.5.7", False)]


def test_run_pip_install_prefers_uv(monkeypatch: pytest.MonkeyPatch) -> None:
    from groovy.registry import installer as installer_mod

    captured: list[list[str]] = []

    class FakeProc:
        returncode = 0

        def poll(self):
            return 0

        def communicate(self):
            return ("", "")

        def terminate(self):
            return None

        def kill(self):
            return None

        def wait(self, timeout=None):
            return 0

    def fake_popen(command, **kwargs):
        captured.append(command)
        return FakeProc()

    monkeypatch.setattr(installer_mod.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(installer_mod.subprocess, "Popen", fake_popen)
    installer_mod._run_pip_install("torch>=2.0.0")
    assert captured[0][:4] == ["uv", "pip", "install", "--python"]
    assert captured[0][-1] == "torch>=2.0.0"


def test_install_python_deps_no_deps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []

    def fake_pip(requirement: str, *, no_deps: bool = False, cancel_check=None) -> None:
        calls.append((requirement, no_deps))

    monkeypatch.delenv("GROOVY_INFERENCE_STUB", raising=False)
    monkeypatch.setattr("groovy.registry.installer._run_pip_install", fake_pip)
    monkeypatch.setattr("groovy.registry.installer._purge_conflicting_pypi_groovy", lambda: None)
    manifest = ModelManifest(
        id="basic-pitch",
        name="Basic Pitch",
        description="",
        task_types=["audio-to-midi"],
        license=LicenseInfo(spdx="Apache-2.0", commercial_ok=True),
        install=InstallSpec(
            python_deps=[{"package": "basic-pitch", "version": "==0.4.0", "no_deps": True}],
            verify_imports=["basic_pitch.note_creation"],
        ),
    )
    store = InstallStore(tmp_path)
    _install_python_deps(manifest, "basic-pitch", store, project_dir=tmp_path)
    assert calls == [("basic-pitch==0.4.0", True)]


def test_basic_pitch_seed_includes_package() -> None:
    manifest = ModelCatalog().get("basic-pitch")
    assert manifest is not None
    packages = {dep["package"] for dep in manifest.install.python_deps}
    assert "basic-pitch" in packages
    assert manifest.install.verify_imports == ["basic_pitch.note_creation", "onnxruntime"]


def test_install_status_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_PROJECT_DIR", str(tmp_path))
    main.PROJECT_DIR = tmp_path
    main._registry = ModelRegistry(tmp_path)
    main._install_threads.clear()
    client = TestClient(main.app)

    started = client.post("/api/models/deepfilternet-v3/install")
    assert started.status_code == 202
    status = client.get("/api/models/deepfilternet-v3/install/status")
    assert status.status_code == 200
    assert status.json()["status"] in {"ready", "downloading", "verifying", "failed"}


def test_similar_models_on_failure(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    registry.store.mark_failed("demucs-v4", "checksum mismatch")
    recovery = registry.installer.recovery_suggestions("demucs-v4")
    assert recovery["error"]
    assert len(recovery["similar_models"]) >= 1
