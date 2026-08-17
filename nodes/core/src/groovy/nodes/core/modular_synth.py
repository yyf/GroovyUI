"""Offline modular-synth building blocks (patch-bay DSP, not live CV hardware)."""

from __future__ import annotations

import numpy as np
from scipy import signal as scipy_signal

from groovy.executor.audio import AudioBuffer
from groovy.executor.control import AutomationBuffer
from groovy.executor.audio_meta import inherit_format_meta
from groovy.executor.midi import MidiBuffer
from groovy.node import GroovyNode, register_node

WAVEFORMS = ("sine", "saw", "square", "triangle")
NOISE_COLORS = ("white", "pink", "brown")
FILTER_TYPES = ("lowpass", "highpass", "bandpass", "notch")
LOGIC_OPS = ("and", "or", "xor", "not")
QUANTIZE_SCALES = ("chromatic", "major", "minor", "pentatonic")


def register_modular_synth() -> None:
    _ = (
        NoiseGenerator,
        Oscillator,
        MatrixMixer,
        Filter,
        Amplifier,
        Envelope,
        LFO,
        Attenuator,
        Reverb,
        Logic,
        Comparator,
        SampleAndHold,
        Quantizer,
        Clock,
        AutomationToMIDI,
    )


def automation_or_const(
    curve: AutomationBuffer | None,
    frame_count: int,
    default: float,
) -> np.ndarray:
    if curve is None:
        return np.full(frame_count, float(default), dtype=np.float64)
    return np.asarray(curve.resample_to(frame_count), dtype=np.float64)


def oscillator_from_phase(phase: np.ndarray, waveform: str) -> np.ndarray:
    waveform = waveform.lower().strip()
    if waveform in {"saw", "sawtooth"}:
        return 2.0 * (np.mod(phase / (2.0 * np.pi), 1.0) - 0.5)
    if waveform in {"square", "sq"}:
        return np.where(np.mod(phase, 2.0 * np.pi) < np.pi, 1.0, -1.0)
    if waveform in {"triangle", "tri"}:
        saw = 2.0 * (np.mod(phase / (2.0 * np.pi), 1.0) - 0.5)
        return 2.0 * np.abs(saw) - 1.0
    return np.sin(phase)


def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    white = rng.standard_normal(n)
    b = np.array([0.049922035, -0.095993537, 0.050612699, -0.004408786])
    a = np.array([1.0, -2.494956002, 2.017265875, -0.522189400])
    pink = scipy_signal.lfilter(b, a, white)
    peak = float(np.max(np.abs(pink))) or 1.0
    return (pink / peak).astype(np.float64)


def brown_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    white = rng.standard_normal(n)
    brown = np.cumsum(white)
    brown -= np.mean(brown)
    peak = float(np.max(np.abs(brown))) or 1.0
    return (brown / peak).astype(np.float64)


def adsr_values(
    frame_count: int,
    sample_rate: int,
    *,
    attack_ms: float,
    decay_ms: float,
    sustain: float,
    release_ms: float,
) -> np.ndarray:
    attack = max(1, int(attack_ms * 0.001 * sample_rate))
    decay = max(1, int(decay_ms * 0.001 * sample_rate))
    release = max(1, int(release_ms * 0.001 * sample_rate))
    sustain = float(np.clip(sustain, 0.0, 1.0))
    sustain_len = max(0, frame_count - attack - decay - release)
    parts: list[np.ndarray] = [
        np.linspace(0.0, 1.0, attack, endpoint=False),
        np.linspace(1.0, sustain, decay, endpoint=False),
    ]
    if sustain_len > 0:
        parts.append(np.full(sustain_len, sustain, dtype=np.float64))
    parts.append(np.linspace(sustain, 0.0, release, endpoint=True))
    env = np.concatenate(parts)
    if len(env) < frame_count:
        env = np.pad(env, (0, frame_count - len(env)))
    return env[:frame_count].astype(np.float64)


def _scale_degrees(scale: str) -> np.ndarray:
    scale = scale.lower().strip()
    if scale == "major":
        return np.array([0, 2, 4, 5, 7, 9, 11], dtype=np.int32)
    if scale == "minor":
        return np.array([0, 2, 3, 5, 7, 8, 10], dtype=np.int32)
    if scale in {"pentatonic", "penta"}:
        return np.array([0, 2, 4, 7, 9], dtype=np.int32)
    return np.arange(12, dtype=np.int32)


def hz_to_midi_note(hz: np.ndarray | float) -> np.ndarray:
    """Map Hz CV to MIDI note numbers (A4=440 → 69)."""
    hz_arr = np.maximum(np.asarray(hz, dtype=np.float64), 8.1757989156)
    notes = np.rint(69.0 + 12.0 * np.log2(hz_arr / 440.0)).astype(np.int32)
    return np.clip(notes, 0, 127)


def automation_to_midi_events(
    hz: np.ndarray,
    *,
    gate: np.ndarray | None = None,
    threshold: float = 0.5,
    velocity: float = 0.8,
    channel: int = 0,
) -> list[dict]:
    """Turn stepwise Hz CV into note_on/note_off events (one note per pitch plateau)."""
    notes = hz_to_midi_note(hz).reshape(-1)
    n = int(notes.size)
    if n == 0:
        return []
    if gate is None:
        gated = np.ones(n, dtype=bool)
    else:
        gated = np.asarray(gate, dtype=np.float64).reshape(-1)[:n] >= float(threshold)
        if gated.size < n:
            gated = np.pad(gated, (0, n - gated.size), constant_values=False)
    events: list[dict] = []
    i = 0
    vel = float(np.clip(velocity, 0.0, 1.0))
    ch = int(channel)
    while i < n:
        if not gated[i]:
            i += 1
            continue
        note = int(notes[i])
        start = i
        i += 1
        while i < n and gated[i] and int(notes[i]) == note:
            i += 1
        end = max(start, i - 1)
        events.append(
            {"frame": start, "type": "note_on", "channel": ch, "note": note, "velocity": vel}
        )
        events.append(
            {"frame": end, "type": "note_off", "channel": ch, "note": note, "velocity": 0.0}
        )
    return events


def quantize_cv(values: np.ndarray, *, root_hz: float, scale: str) -> np.ndarray:
    degrees = _scale_degrees(scale)
    out = np.empty_like(values, dtype=np.float64)
    for i, v in enumerate(values.astype(np.float64)):
        if abs(v) > 8.0:
            midi = 69.0 + 12.0 * np.log2(max(v, 1.0) / 440.0)
        else:
            midi = 69.0 + 12.0 * np.log2(max(root_hz, 1.0) / 440.0) + float(v) * 12.0
        octave = int(np.floor(midi / 12.0))
        pc = midi - octave * 12.0
        nearest = int(degrees[int(np.argmin(np.abs(degrees.astype(np.float64) - (pc % 12))))])
        q_midi = octave * 12.0 + nearest
        out[i] = 440.0 * (2.0 ** ((q_midi - 69.0) / 12.0))
    return out


def _write_audio(
    ctx,
    pcm: np.ndarray,
    sample_rate: int,
    *,
    source: str,
    channel_layout: str = "mono",
    inherit_from: AudioBuffer | None = None,
) -> AudioBuffer:
    buffer = AudioBuffer.from_planar(
        pcm,
        sample_rate,
        source_node_type=source,
        channel_layout=channel_layout,
    )
    if inherit_from is not None:
        inherit_format_meta(buffer, inherit_from)
    ctx.cache.write_audio(buffer, pcm)
    return buffer


def _write_automation(ctx, values: np.ndarray, sample_rate: int, source: str) -> AutomationBuffer:
    curve = AutomationBuffer.from_values(values, sample_rate=sample_rate, source_node_type=source)
    ctx.cache.write_automation(curve)
    return curve


def _load_mono(ctx, audio: AudioBuffer, frame_count: int | None = None) -> np.ndarray:
    _, pcm = ctx.cache.load_audio(audio.id)
    mono = pcm.mean(axis=0) if pcm.ndim == 2 else pcm.reshape(-1)
    mono = mono.astype(np.float64)
    if frame_count is not None and mono.size != frame_count:
        x_old = np.linspace(0.0, 1.0, max(1, mono.size))
        x_new = np.linspace(0.0, 1.0, frame_count)
        mono = np.interp(x_new, x_old, mono)
    return mono


def _butter_btype(ftype: str) -> str:
    if ftype in {"highpass", "hp"}:
        return "highpass"
    if ftype in {"bandpass", "bp"}:
        return "bandpass"
    if ftype in {"notch", "bandstop"}:
        return "bandstop"
    return "lowpass"


def _butter_sos(ftype: str, cutoff_hz: float, sample_rate: int, q: float) -> np.ndarray:
    nyq = sample_rate / 2.0
    btype = _butter_btype(ftype)
    if btype in {"bandpass", "bandstop"}:
        width = max(cutoff_hz / max(q, 0.1), 20.0)
        low = max(20.0, cutoff_hz - width / 2) / nyq
        high = min(nyq - 1.0, cutoff_hz + width / 2) / nyq
        if high <= low:
            high = min(0.99, low + 0.01)
        return scipy_signal.butter(2, [low, high], btype=btype, output="sos")
    wn = float(np.clip(cutoff_hz / nyq, 1e-4, 0.99))
    return scipy_signal.butter(2, wn, btype=btype, output="sos")


@register_node
class NoiseGenerator(GroovyNode):
    """White / pink / brown noise source."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_CLASS = "human_edited"
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "color": ("STRING", {"default": "white", "choices": list(NOISE_COLORS)}),
                "amplitude": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0}),
                "duration_sec": ("FLOAT", {"default": 2.0, "min": 0.05, "max": 60.0}),
                "sample_rate": ("INT", {"default": 48000, "min": 8000, "max": 192000}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2_147_483_647}),
            },
        }

    def run(self, **kwargs) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        color = str(kwargs.get("color", "white")).lower().strip()
        amp = float(np.clip(float(kwargs.get("amplitude", 0.25)), 0.0, 1.0))
        duration_sec = float(np.clip(float(kwargs.get("duration_sec", 2.0)), 0.05, 60.0))
        sample_rate = int(np.clip(int(kwargs.get("sample_rate", 48000)), 8000, 192000))
        seed = int(kwargs.get("seed", 0))
        frame_count = max(1, int(round(duration_sec * sample_rate)))
        rng = np.random.default_rng(seed)
        if color == "pink":
            noise = pink_noise(frame_count, rng)
        elif color in {"brown", "brownian", "red"}:
            noise = brown_noise(frame_count, rng)
        else:
            noise = rng.standard_normal(frame_count)
            peak = float(np.max(np.abs(noise))) or 1.0
            noise = noise / peak
        pcm = (noise * amp).reshape(1, -1)
        return (_write_audio(self._ctx, pcm, sample_rate, source="NoiseGenerator"),)


@register_node
class Oscillator(GroovyNode):
    """Modular oscillator (AUDIO). Supports CV frequency/amplitude and phase_mod FM."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_CLASS = "human_edited"
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "frequency": ("AUTOMATION",),
                "amplitude": ("AUTOMATION",),
                "phase_mod": ("AUDIO",),
                "waveform": ("STRING", {"default": "sine", "choices": list(WAVEFORMS)}),
                "frequency_hz": ("FLOAT", {"default": 220.0, "min": 1.0, "max": 20000.0}),
                "amplitude_default": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 8.0}),
                "duration_sec": ("FLOAT", {"default": 2.0, "min": 0.05, "max": 60.0}),
                "sample_rate": ("INT", {"default": 48000, "min": 8000, "max": 192000}),
            },
        }

    def run(self, **kwargs) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        waveform = str(kwargs.get("waveform", "sine"))
        freq_default = float(np.clip(float(kwargs.get("frequency_hz", 220.0)), 1.0, 20000.0))
        amp_default = float(np.clip(float(kwargs.get("amplitude_default", 0.35)), 0.0, 8.0))
        duration_sec = float(np.clip(float(kwargs.get("duration_sec", 2.0)), 0.05, 60.0))
        sample_rate = int(np.clip(int(kwargs.get("sample_rate", 48000)), 8000, 192000))
        frame_count = max(1, int(round(duration_sec * sample_rate)))
        freq = np.clip(automation_or_const(kwargs.get("frequency"), frame_count, freq_default), 1.0, 20000.0)
        amp = np.clip(automation_or_const(kwargs.get("amplitude"), frame_count, amp_default), 0.0, 8.0)
        dphase = 2.0 * np.pi * freq / sample_rate
        phase = np.cumsum(dphase) - dphase
        phase_mod = kwargs.get("phase_mod")
        if phase_mod is not None:
            phase = phase + _load_mono(self._ctx, phase_mod, frame_count)
        wave = oscillator_from_phase(phase, waveform) * amp
        return (_write_audio(self._ctx, wave.reshape(1, -1), sample_rate, source="Oscillator"),)


@register_node
class MatrixMixer(GroovyNode):
    """N×M AUDIO matrix — each input×output crosspoint has a gain knob (4×4)."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_PASSTHROUGH = True
    MATRIX_SIZE = 4
    RETURN_TYPES = ("AUDIO", "AUDIO", "AUDIO", "AUDIO")
    OUTPUT_NAMES = ("out_0", "out_1", "out_2", "out_3")

    @classmethod
    def INPUT_TYPES(cls):
        size = cls.MATRIX_SIZE
        optional: dict = {f"in_{i}": ("AUDIO",) for i in range(size)}
        for i in range(size):
            for j in range(size):
                # Default: unity into bus 0 (legacy single-mix behavior), muted elsewhere.
                default = 1.0 if j == 0 else 0.0
                optional[f"gain_{i}_{j}"] = ("FLOAT", {"default": default, "min": 0.0, "max": 4.0})
        return {"required": {}, "optional": optional}

    @classmethod
    def describe(cls) -> dict:
        schema = super().describe()
        schema["outputs"] = [{"name": name, "type": "AUDIO"} for name in cls.OUTPUT_NAMES]
        return schema

    @staticmethod
    def _crosspoint_gain(kwargs: dict, in_idx: int, out_idx: int) -> float:
        key = f"gain_{in_idx}_{out_idx}"
        if key in kwargs and kwargs[key] is not None:
            return float(np.clip(float(kwargs[key]), 0.0, 4.0))
        # Legacy templates used gain_0..gain_3 as per-input levels into a single mix.
        if out_idx == 0:
            legacy = kwargs.get(f"gain_{in_idx}")
            if legacy is not None:
                return float(np.clip(float(legacy), 0.0, 4.0))
            return 1.0
        return 0.0

    def run(self, **kwargs) -> tuple[AudioBuffer, AudioBuffer, AudioBuffer, AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        size = self.MATRIX_SIZE
        loaded: list[tuple[int, AudioBuffer, np.ndarray]] = []
        sample_rate = 48000
        frame_count = 1
        channels = 1
        for i in range(size):
            buf = kwargs.get(f"in_{i}")
            if buf is None:
                continue
            _, pcm = self._ctx.cache.load_audio(buf.id)
            pcm = pcm.astype(np.float64)
            loaded.append((i, buf, pcm))
            sample_rate = buf.sample_rate
            frame_count = max(frame_count, int(pcm.shape[1]))
            channels = max(channels, int(pcm.shape[0]))
        if not loaded:
            raise ValueError("MatrixMixer requires at least one AUDIO input")

        aligned: list[tuple[int, AudioBuffer, np.ndarray]] = []
        for i, buf, pcm in loaded:
            if pcm.shape[1] != frame_count:
                x_old = np.linspace(0.0, 1.0, max(1, pcm.shape[1]))
                x_new = np.linspace(0.0, 1.0, frame_count)
                pcm = np.vstack([np.interp(x_new, x_old, ch) for ch in pcm])
            if pcm.shape[0] < channels:
                pcm = np.vstack([pcm, np.zeros((channels - pcm.shape[0], frame_count))])
            elif pcm.shape[0] > channels:
                pcm = pcm[:channels]
            aligned.append((i, buf, pcm))

        layout = "mono" if channels == 1 else ("stereo" if channels == 2 else "custom")
        inherit_from = aligned[0][1]
        outs: list[AudioBuffer] = []
        for j in range(size):
            mix = np.zeros((channels, frame_count), dtype=np.float64)
            for i, _buf, pcm in aligned:
                gain = self._crosspoint_gain(kwargs, i, j)
                if gain == 0.0:
                    continue
                mix += pcm * gain
            outs.append(
                _write_audio(
                    self._ctx,
                    mix,
                    sample_rate,
                    source="MatrixMixer",
                    channel_layout=layout,
                    inherit_from=inherit_from,
                )
            )
        return (outs[0], outs[1], outs[2], outs[3])


@register_node
class Filter(GroovyNode):
    """Biquad filter (VCF) with optional cutoff AUTOMATION in Hz."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "cutoff": ("AUTOMATION",),
                "filter_type": ("STRING", {"default": "lowpass", "choices": list(FILTER_TYPES)}),
                "cutoff_hz": ("FLOAT", {"default": 1200.0, "min": 20.0, "max": 20000.0}),
                "q": ("FLOAT", {"default": 0.707, "min": 0.1, "max": 20.0}),
            },
        }

    def run(self, audio: AudioBuffer, **kwargs) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        _, pcm = self._ctx.cache.load_audio(audio.id)
        pcm = pcm.astype(np.float64)
        ftype = str(kwargs.get("filter_type", "lowpass")).lower().strip()
        cutoff_hz = float(np.clip(float(kwargs.get("cutoff_hz", 1200.0)), 20.0, audio.sample_rate * 0.45))
        q = float(np.clip(float(kwargs.get("q", 0.707)), 0.1, 20.0))
        cutoff_curve = kwargs.get("cutoff")
        frames = pcm.shape[1]
        if cutoff_curve is not None:
            cut = np.clip(
                automation_or_const(cutoff_curve, frames, cutoff_hz),
                20.0,
                audio.sample_rate * 0.45,
            )
            out = np.zeros_like(pcm)
            block = max(64, frames // 64)
            for start in range(0, frames, block):
                end = min(frames, start + block)
                fc = float(np.median(cut[start:end]))
                sos = _butter_sos(ftype, fc, audio.sample_rate, q)
                out[:, start:end] = scipy_signal.sosfilt(sos, pcm[:, start:end], axis=1)
            pcm = out
        else:
            sos = _butter_sos(ftype, cutoff_hz, audio.sample_rate, q)
            pcm = scipy_signal.sosfilt(sos, pcm, axis=1)
        return (
            _write_audio(
                self._ctx,
                pcm,
                audio.sample_rate,
                source="Filter",
                channel_layout=audio.channel_layout,
                inherit_from=audio,
            ),
        )


@register_node
class Amplifier(GroovyNode):
    """VCA — multiply AUDIO by gain and optional AUTOMATION CV."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "cv": ("AUTOMATION",),
                "gain": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 8.0}),
            },
        }

    def run(self, audio: AudioBuffer, **kwargs) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        _, pcm = self._ctx.cache.load_audio(audio.id)
        gain = float(np.clip(float(kwargs.get("gain", 1.0)), 0.0, 8.0))
        cv = kwargs.get("cv")
        if cv is not None:
            env = automation_or_const(cv, pcm.shape[1], 1.0) * gain
            pcm = pcm.astype(np.float64) * env.reshape(1, -1)
        else:
            pcm = pcm.astype(np.float64) * gain
        return (
            _write_audio(
                self._ctx,
                pcm,
                audio.sample_rate,
                source="Amplifier",
                channel_layout=audio.channel_layout,
                inherit_from=audio,
            ),
        )


@register_node
class Envelope(GroovyNode):
    """ADSR envelope → AUTOMATION (one-shot over duration)."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_CLASS = "human_edited"
    RETURN_TYPES = ("AUTOMATION",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "attack_ms": ("FLOAT", {"default": 10.0, "min": 0.1, "max": 5000.0}),
                "decay_ms": ("FLOAT", {"default": 100.0, "min": 0.1, "max": 5000.0}),
                "sustain": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0}),
                "release_ms": ("FLOAT", {"default": 200.0, "min": 0.1, "max": 10000.0}),
                "duration_sec": ("FLOAT", {"default": 2.0, "min": 0.05, "max": 60.0}),
                "sample_rate": ("INT", {"default": 48000, "min": 8000, "max": 192000}),
            },
        }

    def run(self, **kwargs) -> tuple[AutomationBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        sample_rate = int(np.clip(int(kwargs.get("sample_rate", 48000)), 8000, 192000))
        duration_sec = float(np.clip(float(kwargs.get("duration_sec", 2.0)), 0.05, 60.0))
        frame_count = max(1, int(round(duration_sec * sample_rate)))
        values = adsr_values(
            frame_count,
            sample_rate,
            attack_ms=float(kwargs.get("attack_ms", 10.0)),
            decay_ms=float(kwargs.get("decay_ms", 100.0)),
            sustain=float(kwargs.get("sustain", 0.7)),
            release_ms=float(kwargs.get("release_ms", 200.0)),
        )
        return (_write_automation(self._ctx, values, sample_rate, "Envelope"),)


@register_node
class LFO(GroovyNode):
    """Low-frequency oscillator → AUTOMATION."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_CLASS = "human_edited"
    RETURN_TYPES = ("AUTOMATION",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "waveform": ("STRING", {"default": "sine", "choices": list(WAVEFORMS)}),
                "rate_hz": ("FLOAT", {"default": 2.0, "min": 0.01, "max": 40.0}),
                "amplitude": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 8.0}),
                "offset": ("FLOAT", {"default": 0.0, "min": -8.0, "max": 8.0}),
                "duration_sec": ("FLOAT", {"default": 2.0, "min": 0.05, "max": 60.0}),
                "sample_rate": ("INT", {"default": 48000, "min": 8000, "max": 192000}),
            },
        }

    def run(self, **kwargs) -> tuple[AutomationBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        sample_rate = int(np.clip(int(kwargs.get("sample_rate", 48000)), 8000, 192000))
        duration_sec = float(np.clip(float(kwargs.get("duration_sec", 2.0)), 0.05, 60.0))
        frame_count = max(1, int(round(duration_sec * sample_rate)))
        rate = float(np.clip(float(kwargs.get("rate_hz", 2.0)), 0.01, 40.0))
        amp = float(np.clip(float(kwargs.get("amplitude", 1.0)), 0.0, 8.0))
        offset = float(kwargs.get("offset", 0.0))
        waveform = str(kwargs.get("waveform", "sine"))
        t = np.arange(frame_count, dtype=np.float64) / sample_rate
        values = oscillator_from_phase(2.0 * np.pi * rate * t, waveform) * amp + offset
        return (_write_automation(self._ctx, values, sample_rate, "LFO"),)


@register_node
class Attenuator(GroovyNode):
    """Scale AUDIO by amount (0–4). For CV scaling use FloatMath multiply."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "amount": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 4.0}),
            },
        }

    def run(self, audio: AudioBuffer, **kwargs) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        amount = float(np.clip(float(kwargs.get("amount", 0.5)), 0.0, 4.0))
        _, pcm = self._ctx.cache.load_audio(audio.id)
        pcm = pcm.astype(np.float64) * amount
        return (
            _write_audio(
                self._ctx,
                pcm,
                audio.sample_rate,
                source="Attenuator",
                channel_layout=audio.channel_layout,
                inherit_from=audio,
            ),
        )


def _comb_filter(x: np.ndarray, delay: int, feedback: float, damp: float) -> np.ndarray:
    """Feedback comb with one-pole damping in the loop (Schroeder-style)."""
    delay = max(1, int(delay))
    out = np.empty_like(x)
    buf = np.zeros(delay, dtype=np.float64)
    idx = 0
    filter_state = 0.0
    damp = float(np.clip(damp, 0.0, 0.98))
    feedback = float(np.clip(feedback, 0.0, 0.97))
    for i in range(x.shape[0]):
        delayed = buf[idx]
        filter_state = delayed * (1.0 - damp) + filter_state * damp
        out[i] = x[i] + filter_state
        buf[idx] = x[i] + filter_state * feedback
        idx += 1
        if idx >= delay:
            idx = 0
    return out


def _allpass_filter(x: np.ndarray, delay: int, feedback: float = 0.5) -> np.ndarray:
    delay = max(1, int(delay))
    out = np.empty_like(x)
    buf = np.zeros(delay, dtype=np.float64)
    idx = 0
    feedback = float(np.clip(feedback, 0.0, 0.9))
    for i in range(x.shape[0]):
        buffered = buf[idx]
        out[i] = -x[i] + buffered
        buf[idx] = x[i] + buffered * feedback
        idx += 1
        if idx >= delay:
            idx = 0
    return out


def schroeder_reverb_mono(
    dry: np.ndarray,
    sample_rate: int,
    *,
    room_sec: float,
    damping: float,
) -> np.ndarray:
    """Compact Schroeder reverb via short IR + FFT convolution (fast on long buffers)."""
    room_sec = float(np.clip(room_sec, 0.15, 4.0))
    damping = float(np.clip(damping, 0.05, 0.95))
    feedback = float(np.clip(0.72 + 0.2 * min(room_sec / 2.5, 1.0), 0.55, 0.92))
    ir_len = max(64, int(round(sample_rate * min(room_sec * 1.4, 2.8))))
    impulse = np.zeros(ir_len, dtype=np.float64)
    impulse[0] = 1.0
    comb_ms = (29.7, 37.1, 41.1, 43.7)
    ir = np.zeros(ir_len, dtype=np.float64)
    for ms in comb_ms:
        delay = max(1, int(sample_rate * ms * 0.001 * (0.85 + 0.15 * room_sec)))
        ir += _comb_filter(impulse, delay, feedback, damping)
    ir *= 0.25
    ir = _allpass_filter(ir, max(1, int(sample_rate * 0.005)), 0.5)
    ir = _allpass_filter(ir, max(1, int(sample_rate * 0.0017)), 0.5)
    wet = scipy_signal.fftconvolve(dry, ir, mode="full")[: dry.shape[0]]
    return wet.astype(np.float64, copy=False)


@register_node
class Reverb(GroovyNode):
    """Lightweight Schroeder reverb — optional mix AUTOMATION for evolving wet amount."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "mix_cv": ("AUTOMATION",),
                "mix": ("FLOAT", {"default": 0.18, "min": 0.0, "max": 1.0}),
                "room_sec": ("FLOAT", {"default": 1.2, "min": 0.15, "max": 4.0}),
                "damping": ("FLOAT", {"default": 0.45, "min": 0.05, "max": 0.95}),
            },
        }

    def run(self, audio: AudioBuffer, **kwargs) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        _, pcm = self._ctx.cache.load_audio(audio.id)
        pcm = pcm.astype(np.float64)
        mix_default = float(np.clip(float(kwargs.get("mix", 0.18)), 0.0, 1.0))
        room_sec = float(kwargs.get("room_sec", 1.2))
        damping = float(kwargs.get("damping", 0.45))
        frames = pcm.shape[1]
        mix = np.clip(automation_or_const(kwargs.get("mix_cv"), frames, mix_default), 0.0, 1.0)
        wet = np.zeros_like(pcm)
        for ch in range(pcm.shape[0]):
            wet[ch] = schroeder_reverb_mono(pcm[ch], audio.sample_rate, room_sec=room_sec, damping=damping)
        mix_row = mix.reshape(1, -1)
        out = pcm * (1.0 - mix_row) + wet * mix_row
        peak = float(np.max(np.abs(out))) if out.size else 0.0
        if peak > 1.0:
            out *= 1.0 / peak
        return (
            _write_audio(
                self._ctx,
                out,
                audio.sample_rate,
                source="Reverb",
                channel_layout=audio.channel_layout,
                inherit_from=audio,
            ),
        )


@register_node
class Logic(GroovyNode):
    """Boolean logic on gate-like AUTOMATION streams (thresholded)."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_CLASS = "human_edited"
    RETURN_TYPES = ("AUTOMATION",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "a": ("AUTOMATION",),
                "b": ("AUTOMATION",),
                "operation": ("STRING", {"default": "and", "choices": list(LOGIC_OPS)}),
                "threshold": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0}),
            },
        }

    def run(self, **kwargs) -> tuple[AutomationBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        a = kwargs.get("a")
        b = kwargs.get("b")
        if a is None:
            raise ValueError("Logic requires AUTOMATION input a")
        op = str(kwargs.get("operation", "and")).lower().strip()
        thr = float(kwargs.get("threshold", 0.5))
        length = a.frame_count if b is None else max(a.frame_count, b.frame_count)
        ga = automation_or_const(a, length, 0.0) >= thr
        if op == "not":
            values = (~ga).astype(np.float64)
        else:
            if b is None:
                raise ValueError(f"Logic {op} requires AUTOMATION input b")
            gb = automation_or_const(b, length, 0.0) >= thr
            if op == "or":
                values = (ga | gb).astype(np.float64)
            elif op == "xor":
                values = (ga ^ gb).astype(np.float64)
            else:
                values = (ga & gb).astype(np.float64)
        return (_write_automation(self._ctx, values, a.sample_rate, "Logic"),)


@register_node
class Comparator(GroovyNode):
    """Compare AUTOMATION (or AUDIO as mono) against threshold → gate AUTOMATION."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_CLASS = "human_edited"
    RETURN_TYPES = ("AUTOMATION",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "signal": ("AUTOMATION",),
                "audio": ("AUDIO",),
                "threshold": ("FLOAT", {"default": 0.0, "min": -8.0, "max": 8.0}),
            },
        }

    def run(self, **kwargs) -> tuple[AutomationBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        thr = float(kwargs.get("threshold", 0.0))
        curve = kwargs.get("signal")
        audio = kwargs.get("audio")
        if curve is not None:
            values = (curve.values.astype(np.float64) >= thr).astype(np.float64)
            sr = curve.sample_rate
        elif audio is not None:
            mono = _load_mono(self._ctx, audio)
            values = (mono >= thr).astype(np.float64)
            sr = audio.sample_rate
        else:
            raise ValueError("Comparator requires signal or audio")
        return (_write_automation(self._ctx, values, sr, "Comparator"),)


@register_node
class SampleAndHold(GroovyNode):
    """Sample AUTOMATION (or AUDIO mono) on rising edges of clock AUTOMATION."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_CLASS = "human_edited"
    RETURN_TYPES = ("AUTOMATION",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"clock": ("AUTOMATION",)},
            "optional": {
                "signal": ("AUTOMATION",),
                "audio": ("AUDIO",),
                "threshold": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0}),
            },
        }

    def run(self, clock: AutomationBuffer, **kwargs) -> tuple[AutomationBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        thr = float(kwargs.get("threshold", 0.5))
        length = clock.frame_count
        clk = automation_or_const(clock, length, 0.0)
        sig_curve = kwargs.get("signal")
        audio = kwargs.get("audio")
        if sig_curve is not None:
            src = automation_or_const(sig_curve, length, 0.0)
        elif audio is not None:
            src = _load_mono(self._ctx, audio, length)
        else:
            src = np.zeros(length, dtype=np.float64)
        gate = clk >= thr
        edges = np.zeros(length, dtype=bool)
        edges[0] = gate[0]
        edges[1:] = gate[1:] & ~gate[:-1]
        out = np.zeros(length, dtype=np.float64)
        held = float(src[0]) if length else 0.0
        for i in range(length):
            if edges[i]:
                held = float(src[i])
            out[i] = held
        return (_write_automation(self._ctx, out, clock.sample_rate, "SampleAndHold"),)


@register_node
class Quantizer(GroovyNode):
    """Quantize AUTOMATION CV to musical scale frequencies (Hz)."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_CLASS = "human_edited"
    RETURN_TYPES = ("AUTOMATION",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"cv": ("AUTOMATION",)},
            "optional": {
                "scale": ("STRING", {"default": "major", "choices": list(QUANTIZE_SCALES)}),
                "root_hz": ("FLOAT", {"default": 220.0, "min": 20.0, "max": 2000.0}),
            },
        }

    def run(self, cv: AutomationBuffer, **kwargs) -> tuple[AutomationBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        scale = str(kwargs.get("scale", "major"))
        root_hz = float(np.clip(float(kwargs.get("root_hz", 220.0)), 20.0, 2000.0))
        values = quantize_cv(cv.values, root_hz=root_hz, scale=scale)
        return (_write_automation(self._ctx, values, cv.sample_rate, "Quantizer"),)


@register_node
class Clock(GroovyNode):
    """Pulse-train AUTOMATION clock (BPM or Hz)."""

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_CLASS = "human_edited"
    RETURN_TYPES = ("AUTOMATION",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "bpm": ("FLOAT", {"default": 120.0, "min": 1.0, "max": 480.0}),
                "pulse_ms": ("FLOAT", {"default": 10.0, "min": 0.5, "max": 200.0}),
                "duration_sec": ("FLOAT", {"default": 2.0, "min": 0.05, "max": 60.0}),
                "sample_rate": ("INT", {"default": 48000, "min": 8000, "max": 192000}),
            },
        }

    def run(self, **kwargs) -> tuple[AutomationBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        sample_rate = int(np.clip(int(kwargs.get("sample_rate", 48000)), 8000, 192000))
        duration_sec = float(np.clip(float(kwargs.get("duration_sec", 2.0)), 0.05, 60.0))
        bpm = float(np.clip(float(kwargs.get("bpm", 120.0)), 1.0, 480.0))
        pulse_ms = float(np.clip(float(kwargs.get("pulse_ms", 10.0)), 0.5, 200.0))
        frame_count = max(1, int(round(duration_sec * sample_rate)))
        period = max(1, int(round(sample_rate * 60.0 / bpm)))
        pulse = max(1, int(round(pulse_ms * 0.001 * sample_rate)))
        values = np.zeros(frame_count, dtype=np.float64)
        for start in range(0, frame_count, period):
            end = min(frame_count, start + pulse)
            values[start:end] = 1.0
        return (_write_automation(self._ctx, values, sample_rate, "Clock"),)


@register_node
class AutomationToMIDI(GroovyNode):
    """Convert Hz AUTOMATION (and optional gate) into MIDI note events.

    Offline sequencer read of a Quantizer/S&H plateau — not a live MIDI callback.
    """

    CATEGORY = "GroovyUI/Modular"
    PROVENANCE_CLASS = "human_edited"
    SAMPLE_ACCURATE = True
    DETERMINISTIC = True
    DURATION_LOCKED = True
    RETURN_TYPES = ("MIDI",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"cv": ("AUTOMATION",)},
            "optional": {
                "gate": ("AUTOMATION",),
                "threshold": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0}),
                "velocity": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0}),
                "midi_kind": ("STRING", {"default": "score"}),
            },
        }

    def run(self, cv: AutomationBuffer, **kwargs) -> tuple[MidiBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        from groovy.executor.live_midi import smf_bytes_from_note_events, write_midi_events_meta

        gate = kwargs.get("gate")
        threshold = float(np.clip(float(kwargs.get("threshold", 0.5)), 0.0, 1.0))
        velocity = float(np.clip(float(kwargs.get("velocity", 0.8)), 0.0, 1.0))
        midi_kind = str(kwargs.get("midi_kind", "score") or "score")
        hz = np.asarray(cv.values, dtype=np.float64)
        gate_values = None if gate is None else np.asarray(gate.resample_to(hz.size), dtype=np.float64)
        events = automation_to_midi_events(
            hz,
            gate=gate_values,
            threshold=threshold,
            velocity=velocity,
        )
        midi = MidiBuffer.create(
            sample_rate=int(cv.sample_rate),
            frame_count=int(cv.frame_count),
            source_node_type="AutomationToMIDI",
            midi_kind=midi_kind,
        )
        smf = smf_bytes_from_note_events(events, sample_rate=int(cv.sample_rate))
        write_midi_events_meta(self._ctx.cache, midi, events, midi_bytes=smf)
        return (midi,)
