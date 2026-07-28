from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from groovy.nodes.ai.inference import timbre_transfer_audio


def test_timbre_transfer_stub_when_inference_stub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "1")
    pcm = np.random.randn(1, 4000).astype(np.float64) * 0.1
    out = timbre_transfer_audio(
        pcm,
        sample_rate=16000,
        model_id="rave-v1",
        fidelity=0.7,
        project_dir=tmp_path,
    )
    assert out.shape == pcm.shape
    assert float(np.max(np.abs(out))) <= 1.0 + 1e-6


def test_timbre_transfer_requires_install_when_real(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GROOVY_INFERENCE_STUB", raising=False)
    monkeypatch.setenv("GROOVY_INFERENCE_STUB", "0")
    # Force "real" path: torch available, stub off, missing checkpoint → runner error or install error.
    monkeypatch.setattr("groovy.nodes.ai.inference_env.inference_stub_enabled", lambda: False)
    monkeypatch.setattr("groovy.nodes.ai.inference_env.rave_available", lambda: True)

    def _boom(*_a, **_k):
        raise RuntimeError("RAVE checkpoint not found")

    monkeypatch.setattr("groovy.nodes.ai.backends.rave_runner.transfer_pcm", _boom)
    pcm = np.zeros((1, 1000), dtype=np.float64)
    with pytest.raises(RuntimeError, match="RAVE checkpoint not found"):
        timbre_transfer_audio(
            pcm,
            sample_rate=48000,
            model_id="rave-v1",
            fidelity=1.0,
            project_dir=tmp_path,
        )


def test_rave_v1_seed_is_not_dev_stub() -> None:
    from groovy.registry.catalog import ModelCatalog

    manifest = ModelCatalog().get("rave-v1")
    assert manifest is not None
    assert manifest.install.dev_stub is False
    assert any(w.get("filename") == "sol_ordinario_fast.ts" for w in manifest.install.weights)
