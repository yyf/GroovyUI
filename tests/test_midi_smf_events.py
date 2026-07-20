from __future__ import annotations

from pathlib import Path

import pytest
from groovy.executor.live_midi import events_from_smf

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_MID = ROOT / "assets" / "samples" / "automation_cc7.mid"


@pytest.mark.skipif(not SAMPLE_MID.exists(), reason="bundled automation_cc7.mid missing")
def test_events_from_smf_reads_notes_and_cc7() -> None:
    events, frames = events_from_smf(SAMPLE_MID, sample_rate=48000)
    assert frames == pytest.approx(48000 * 4, abs=4800)
    assert any(e.get("type") == "note_on" and e.get("note") == 60 for e in events)
    cc7 = [e for e in events if e.get("type") == "cc" and e.get("num") == 7]
    assert len(cc7) >= 4
    assert cc7[0]["value"] == pytest.approx(40 / 127.0, abs=0.01)
