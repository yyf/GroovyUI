from __future__ import annotations

import os
import time
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


def test_ensure_project_samples_copies_bundled_mp4(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "clip.mp4").write_bytes(b"ftyp")

    project = tmp_path / "workspace"
    copied = ensure_project_samples(project, bundled_dir=bundled)

    assert "assets/samples/clip.mp4" in copied
    assert (project / "assets" / "samples" / "clip.mp4").read_bytes() == b"ftyp"


def test_ensure_project_samples_skips_identical_existing(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    sample = bundled / "tone.wav"
    sample.write_bytes(b"same")

    project = tmp_path / "workspace"
    dest = project / "assets" / "samples"
    dest.mkdir(parents=True)
    existing = dest / "tone.wav"
    existing.write_bytes(b"same")
    # Match bundled mtime so bootstrap treats them as identical.
    os.utime(existing, (sample.stat().st_mtime, sample.stat().st_mtime))

    copied = ensure_project_samples(project, bundled_dir=bundled)
    assert copied == []
    assert existing.read_bytes() == b"same"


def test_ensure_project_samples_refreshes_when_bundled_changes(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    sample = bundled / "tone.wav"
    sample.write_bytes(b"new-bytes")

    project = tmp_path / "workspace"
    dest = project / "assets" / "samples"
    dest.mkdir(parents=True)
    existing = dest / "tone.wav"
    existing.write_bytes(b"old")
    # Make workspace copy older so refresh triggers.
    older = time.time() - 3600
    os.utime(existing, (older, older))

    copied = ensure_project_samples(project, bundled_dir=bundled)
    assert copied == ["assets/samples/tone.wav"]
    assert existing.read_bytes() == b"new-bytes"
