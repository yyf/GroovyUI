from __future__ import annotations

from pathlib import Path

from groovy.server.project_assets import resolve_uploaded_audio


def test_upload_reuses_existing_audio_that_has_sidecar(tmp_path: Path) -> None:
    audio = tmp_path / "exports" / "trust_test" / "take.wav"
    audio.parent.mkdir(parents=True)
    payload = b"pcm-bytes-here"
    audio.write_bytes(payload)
    audio.with_name("take.provenance.json").write_text("{}")

    path = resolve_uploaded_audio(tmp_path, "take.wav", payload)
    assert path == "exports/trust_test/take.wav"
    assert not (tmp_path / "assets" / "uploads" / "take.wav").exists()


def test_upload_copies_sidecar_into_uploads_when_no_matching_export(tmp_path: Path) -> None:
    src = tmp_path / "exports" / "take.wav"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"original")
    src.with_name("take.provenance.json").write_text('{"ok": true}')

    payload = b"different-bytes"
    path = resolve_uploaded_audio(tmp_path, "take.wav", payload)
    assert path == "assets/uploads/take.wav"
    sidecar = tmp_path / "assets" / "uploads" / "take.provenance.json"
    assert sidecar.is_file()
    assert sidecar.read_text() == '{"ok": true}'
