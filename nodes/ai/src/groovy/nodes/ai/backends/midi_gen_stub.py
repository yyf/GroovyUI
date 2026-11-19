"""Path-demo text → MIDI (pretty_midi). Deterministic from prompt + seed."""

from __future__ import annotations

import hashlib
from pathlib import Path


# C major / A minor pentatonic-ish pools for stub variety.
_SCALES = (
    (60, 62, 64, 65, 67, 69, 71, 72),  # C major
    (57, 60, 62, 64, 67, 69, 72, 74),  # A minor-ish
    (62, 64, 66, 67, 69, 71, 73, 74),  # D major
    (55, 58, 60, 62, 65, 67, 70, 72),  # G minor-ish
)


def generate_stub_midi(
    prompt: str,
    *,
    dest: Path,
    seed: int = 0,
    duration_sec: float = 8.0,
    tempo_bpm: float = 120.0,
) -> Path:
    """Write a short multi-note SMF derived from the prompt (no ML weights)."""
    import pretty_midi

    text = (prompt or "").strip() or "melody"
    digest = hashlib.sha256(f"{text}|{seed}".encode()).digest()
    scale = _SCALES[digest[0] % len(_SCALES)]
    n_notes = 8 + (digest[1] % 12)
    duration = max(2.0, min(32.0, float(duration_sec)))
    step = duration / max(n_notes, 1)
    bpm = max(60.0, min(180.0, float(tempo_bpm)))

    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    piano = pretty_midi.Instrument(program=0, name="melody")
    t = 0.0
    for i in range(n_notes):
        pitch = scale[(digest[2 + (i % 20)] + i * 3) % len(scale)]
        # Occasional octave jump.
        if digest[(i + 5) % len(digest)] % 7 == 0:
            pitch = min(96, pitch + 12)
        note_len = step * (0.45 + (digest[(i + 9) % len(digest)] % 40) / 100.0)
        velocity = 64 + (digest[(i + 11) % len(digest)] % 48)
        piano.notes.append(
            pretty_midi.Note(
                velocity=int(velocity),
                pitch=int(pitch),
                start=t,
                end=min(duration, t + note_len),
            )
        )
        t += step * (0.7 + (digest[(i + 13) % len(digest)] % 40) / 100.0)
        if t >= duration:
            break

    # Light left-hand pad on root.
    pad = pretty_midi.Instrument(program=48, name="pad")
    root = scale[0] - 12
    pad.notes.append(
        pretty_midi.Note(velocity=40, pitch=max(36, root), start=0.0, end=duration * 0.95)
    )
    pm.instruments.extend([piano, pad])

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(dest))
    return dest
