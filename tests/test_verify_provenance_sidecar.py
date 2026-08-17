from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from groovy.executor.audio import AudioBuffer
from groovy.executor.authenticity import verify_provenance_for_audio
from groovy.executor.cache import CacheStore


def _wav_and_buffer(project: Path, rel: str) -> tuple[AudioBuffer, str]:
    path = project / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (0.1 * np.sin(np.linspace(0, 2 * np.pi, 480, endpoint=False))).astype(np.float64)
    sf.write(path, pcm, 48000)
    cache = CacheStore(project)
    buffer = AudioBuffer.from_planar(pcm.reshape(1, -1), 48000, source_node_type="LoadAudio")
    cache.write_audio(buffer, pcm.reshape(1, -1))
    meta_path = cache.cache_dir / f"{buffer.id}.meta.json"
    meta = json.loads(meta_path.read_text())
    meta["source_path"] = rel
    meta_path.write_text(json.dumps(meta, indent=2))
    return buffer, hashlib.sha256(path.read_bytes()).hexdigest()


def test_verify_provenance_finds_sidecar_beside_audio(tmp_path: Path) -> None:
    buffer, digest = _wav_and_buffer(tmp_path, "exports/take.wav")
    sidecar = tmp_path / "exports" / "take.provenance.json"
    sidecar.write_text(
        json.dumps(
            {
                "contribution": {"class": "human_edited"},
                "origin": {"type": "render"},
                "artifact": {"file_hash": f"sha256:{digest}"},
            }
        )
    )
    check = verify_provenance_for_audio(
        CacheStore(tmp_path), buffer.id, source_path="exports/take.wav"
    )
    assert check["sidecar_found"] is True
    assert check["status"] == "verified"
    assert check["contribution_class"] == "human_edited"


def test_verify_provenance_finds_unique_sidecar_in_other_folder(tmp_path: Path) -> None:
    buffer, digest = _wav_and_buffer(tmp_path, "assets/uploads/take.wav")
    sidecar = tmp_path / "exports" / "trust_test" / "take.provenance.json"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text(
        json.dumps(
            {
                "contribution": {"class": "human_edited"},
                "origin": {"type": "render"},
                "artifact": {"file_hash": f"sha256:{digest}"},
            }
        )
    )
    check = verify_provenance_for_audio(
        CacheStore(tmp_path), buffer.id, source_path="assets/uploads/take.wav"
    )
    assert check["sidecar_found"] is True
    assert check["status"] == "verified"
    assert check["contribution_class"] == "human_edited"
