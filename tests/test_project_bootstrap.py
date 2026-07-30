from __future__ import annotations

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
