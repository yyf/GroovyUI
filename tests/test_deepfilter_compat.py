"""DeepFilterNet / torchaudio compatibility."""

from __future__ import annotations


def test_ensure_deepfilter_importable_patches_torchaudio(monkeypatch) -> None:
    import sys
    import types

    fake_ta = types.ModuleType("torchaudio")

    def load(_path: str):
        import numpy as np

        return np.zeros((1, 8), dtype="float32"), 16000

    fake_ta.load = load  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torchaudio", fake_ta)
    # Drop any prior backend stubs from other tests.
    sys.modules.pop("torchaudio.backend", None)
    sys.modules.pop("torchaudio.backend.common", None)

    from groovy.nodes.ai.deepfilter_compat import ensure_deepfilter_importable

    ensure_deepfilter_importable()
    assert hasattr(fake_ta, "AudioMetaData")
    assert hasattr(fake_ta, "info")
    assert "torchaudio.backend.common" in sys.modules
