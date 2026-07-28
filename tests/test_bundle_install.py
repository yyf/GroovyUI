from __future__ import annotations

from pathlib import Path

import pytest

from groovy.registry import ModelRegistry
from groovy.registry.download import copy_bundle_file


def test_copy_bundle_file(tmp_path: Path) -> None:
    dest = tmp_path / "hello_weights.bin"
    copy_bundle_file(
        "hello_weights.bin",
        dest,
        expected_sha256="8319604c502600e28df191de7b48df61a28c63892d762c5910e5a724ad68ab45",
    )
    assert dest.exists()
    assert dest.read_bytes().startswith(b"GROOVYUI_VERIFY_WEIGHTS")


def test_bundle_model_install(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    state = registry.installer.install("groovy-verify-weights")
    assert state.status == "ready"
    weights = tmp_path / ".groovy" / "models" / "groovy-verify-weights" / "hello_weights.bin"
    assert weights.exists()


def test_ready_without_weights_retriggers_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub→real upgrades: status=ready but missing weight files must re-download."""
    from groovy.registry import installer as installer_mod
    from groovy.registry.models import InstallState

    registry = ModelRegistry(tmp_path)
    model_id = "rave-v1"
    registry.store.update(InstallState(model_id=model_id, status="ready"))
    model_dir = tmp_path / ".groovy" / "models" / model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "installed.json").write_text("{}")

    calls: list[str] = []

    def fake_download(url, dest, **kwargs):
        calls.append(Path(dest).name)
        dest.write_bytes(b"fake-weights")
        return dest

    monkeypatch.setattr(installer_mod, "download_file", fake_download)
    monkeypatch.setattr(installer_mod, "_install_python_deps", lambda *a, **k: None)
    monkeypatch.setattr(installer_mod, "_verify_imports", lambda *a, **k: None)
    monkeypatch.setattr(installer_mod, "_verify_runtime", lambda *a, **k: None)

    state = registry.installer.install(model_id)
    assert state.status == "ready"
    assert "sol_ordinario_fast.ts" in calls
    assert (model_dir / "sol_ordinario_fast.ts").exists()
