from __future__ import annotations

from pathlib import Path

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
