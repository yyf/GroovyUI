from __future__ import annotations

import json
from pathlib import Path

import groovy.server.main as main
import pytest
from fastapi.testclient import TestClient
from groovy.server.activation_diagnostics import ActivationDiagnosticsStore


def test_activation_store_records_privacy_limited_first_audition(
    tmp_path: Path,
) -> None:
    store = ActivationDiagnosticsStore(tmp_path)
    session_id = "session_12345678"
    store.append(
        session_id=session_id,
        event="task_started",
        elapsed_ms=0,
        context={
            "source": "generate",
            "template_id": "podcast-denoise",
            "prompt": "private prompt",
            "path": "/private/audio.wav",
        },
    )
    store.append(
        session_id=session_id,
        event="render_completed",
        elapsed_ms=1200,
    )
    store.append(
        session_id=session_id,
        event="playback_started",
        elapsed_ms=1500,
        context={"preview_kind": "audio"},
    )

    summary = store.summary()

    assert summary["stored_locally"] is True
    assert summary["session_count"] == 1
    assert summary["latest_session"]["outcome"] == "audible"
    assert summary["latest_session"]["time_to_first_audible_ms"] == 1500
    records = [
        json.loads(line) for line in store.path.read_text().splitlines()
    ]
    assert records[0]["context"] == {
        "source": "generate",
        "template_id": "podcast-denoise",
    }
    assert "/private/audio.wav" not in store.path.read_text()
    assert "private prompt" not in store.path.read_text()

    store.clear()
    assert store.summary()["latest_session"] is None


def test_activation_store_rejects_unknown_events(tmp_path: Path) -> None:
    store = ActivationDiagnosticsStore(tmp_path)
    with pytest.raises(ValueError, match="Unsupported"):
        store.append(
            session_id="session_12345678",
            event="uploaded_audio",
            elapsed_ms=0,
        )


def test_activation_diagnostics_api_is_local_and_clearable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        main,
        "_activation_diagnostics",
        ActivationDiagnosticsStore(tmp_path),
    )
    client = TestClient(main.app)
    payload = {
        "session_id": "session_12345678",
        "event": "task_started",
        "elapsed_ms": 0,
        "context": {
            "source": "generate",
            "prompt": "must not persist",
        },
    }

    recorded = client.post("/api/diagnostics/activation", json=payload)
    summary = client.get("/api/diagnostics/activation")
    cleared = client.delete("/api/diagnostics/activation")

    assert recorded.status_code == 200
    assert recorded.json()["record"]["context"] == {"source": "generate"}
    assert summary.status_code == 200
    assert summary.json()["session_count"] == 1
    assert cleared.status_code == 200
    assert client.get("/api/diagnostics/activation").json()["session_count"] == 0
