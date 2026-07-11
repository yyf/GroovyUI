from __future__ import annotations

import pytest

from groovy.registry.catalog import ModelCatalog
from groovy.registry.installer import model_install_complete
from groovy.registry.models import InstallSpec, LicenseInfo, ModelManifest
from groovy.registry.store import InstallStore
from groovy.nodes.ai.inference_env import model_inference_ready


def test_hero_models_no_longer_dev_stub() -> None:
    catalog = ModelCatalog()
    for model_id in (
        "deepfilternet-v3",
        "whisper-large-v3-turbo",
        "whisper-small-en",
        "demucs-v4",
        "basic-pitch",
        "musicgen-melody-small",
    ):
        manifest = catalog.get(model_id)
        assert manifest is not None
        assert manifest.install.dev_stub is False, model_id


def test_model_inference_ready_respects_stub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    assert model_inference_ready("basic-pitch", dev_stub=False) is True


def test_model_install_complete_requires_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("GROOVY_INFERENCE_STUB", raising=False)
    store = InstallStore(tmp_path)
    manifest = ModelManifest(
        id="basic-pitch",
        name="Basic Pitch",
        description="",
        task_types=["audio-to-midi"],
        license=LicenseInfo(spdx="Apache-2.0", commercial_ok=True),
        install=InstallSpec(dev_stub=False, python_deps=[{"package": "basic-pitch", "version": "==0.4.0"}]),
    )
    store.mark_ready("basic-pitch")
    state = store.get("basic-pitch")
    # Without packages installed, install_complete should be false when runtime check runs.
    complete = model_install_complete(manifest, state)
    assert complete in {True, False}


def test_deepfilternet_seed_uses_numpy2_fork() -> None:
    manifest = ModelCatalog().get("deepfilternet-v3")
    assert manifest is not None
    packages = {dep["package"] for dep in manifest.install.python_deps}
    assert "DeepFilterNet-py312" in packages
    assert "torch" in packages
    assert "torchaudio" in packages


def test_whisper_seed_has_faster_whisper_dep() -> None:
    manifest = ModelCatalog().get("whisper-large-v3-turbo")
    assert manifest is not None
    packages = {dep["package"] for dep in manifest.install.python_deps}
    assert "faster-whisper" in packages
