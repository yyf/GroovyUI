from __future__ import annotations

import pytest

from groovy.executor.worker import _clean_worker_error, _parse_worker_stdout

TORCHAUDIO_TRACE = """\
Traceback (most recent call last):
  File "worker.py", line 1, in main
    processor = AutoProcessor.from_pretrained("facebook/musicgen-melody")
ImportError: 
MusicgenMelodyProcessor requires the torchaudio library but it was not found in your environment. Please install it and restart your
runtime.
"""


def test_parse_worker_stdout_plain_json() -> None:
    data = _parse_worker_stdout('{"outputs": [{"type": "MIDI", "midi_id": "abc"}]}')
    assert data["outputs"][0]["midi_id"] == "abc"


def test_parse_worker_stdout_with_log_prefix() -> None:
    stdout = (
        "Predicting MIDI for /tmp/input.wav...\n"
        '{"outputs": [{"type": "MIDI", "midi_id": "abc"}]}'
    )
    data = _parse_worker_stdout(stdout)
    assert data["outputs"][0]["midi_id"] == "abc"


def test_parse_worker_stdout_empty_raises() -> None:
    with pytest.raises(RuntimeError, match="empty output"):
        _parse_worker_stdout("")


def test_clean_worker_error_import_error_not_runtime_dot() -> None:
    msg = _clean_worker_error(TORCHAUDIO_TRACE)
    assert "torchaudio" in msg.lower()
    assert msg != "runtime."


def test_clean_worker_error_runtime_error_line() -> None:
    stderr = "Traceback...\nRuntimeError: Model not installed: basic-pitch"
    assert _clean_worker_error(stderr) == "Model not installed: basic-pitch"
