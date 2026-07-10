from __future__ import annotations

import shutil
from pathlib import Path

from groovy.server.bootstrap import ensure_project_samples


def test_ensure_project_samples_copies_bundled_wav(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    sample = bundled / "dialogue_48k.wav"
    sample.write_bytes(b"RIFF")

    project = tmp_path / "workspace"
    copied = ensure_project_samples(project, bundled_dir=bundled)

    assert copied == ["assets/samples/dialogue_48k.wav"]
    assert (project / "assets" / "samples" / "dialogue_48k.wav").read_bytes() == b"RIFF"


def test_ensure_project_samples_skips_existing(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "tone.wav").write_bytes(b"new")

    project = tmp_path / "workspace"
    dest = project / "assets" / "samples"
    dest.mkdir(parents=True)
    existing = dest / "tone.wav"
    existing.write_bytes(b"old")

    copied = ensure_project_samples(project, bundled_dir=bundled)
    assert copied == []
    assert existing.read_bytes() == b"old"
