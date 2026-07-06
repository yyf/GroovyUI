from __future__ import annotations

import numpy as np
import soundfile as sf
from groovy.executor.audio import AudioBuffer, StemsBuffer
from groovy.node import GroovyNode, register_node
from scipy import signal


def register_all() -> None:
    """Import side-effect registers all core nodes."""
    _ = (
        LoadAudio,
        SaveAudio,
        Resample,
        Trim,
        Mix,
        Normalize,
        Preview,
        StemPick,
    )


@register_node
class LoadAudio(GroovyNode):
    CATEGORY = "GroovyUI/Core"
    PROVENANCE_CLASS = "human_recorded"
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "path": ("STRING", {"default": ""}),
            },
            "optional": {
                "start_frame": ("INT", {"default": 0}),
                "end_frame": ("INT", {"default": -1}),
            },
        }

    def run(self, **kwargs) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        path = str(kwargs.get("path", ""))
        start_frame = int(kwargs.get("start_frame", 0))
        end_frame = int(kwargs.get("end_frame", -1))
        resolved = self._ctx.cache.resolve_project_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"FILE_NOT_FOUND: {path}")

        pcm, sample_rate = sf.read(resolved, dtype="float64", always_2d=True)
        pcm = pcm.T  # planar channels x frames

        start = max(0, start_frame)
        end = pcm.shape[1] if end_frame < 0 else min(pcm.shape[1], end_frame)
        pcm = pcm[:, start:end]

        buffer = AudioBuffer.from_planar(
            pcm,
            sample_rate,
            source_node_type="LoadAudio",
            channel_layout="mono" if pcm.shape[0] == 1 else "stereo",
        )
        self._ctx.cache.write_audio(buffer, pcm)
        return (buffer,)


@register_node
class SaveAudio(GroovyNode):
    RETURN_TYPES = ("STRING",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {},
        }

    def run(
        self,
        audio: AudioBuffer,
        filename: str = "output.wav",
        format: str = "wav",
        bit_depth: str = "float",
        **kwargs,
    ) -> tuple[str]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        filename = kwargs.get("filename", filename)
        out_path = self._ctx.cache.resolve_project_path(filename)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        _, pcm = self._ctx.cache.load_audio(audio.id)
        interleaved = pcm.T
        subtype = "FLOAT" if bit_depth == "float" else "PCM_24"
        sf.write(out_path, interleaved, audio.sample_rate, format=format.upper(), subtype=subtype)
        try:
            self._ctx.cache.export_provenance_sidecar(audio.id, out_path)
        except FileNotFoundError:
            pass
        return (str(out_path),)


@register_node
class Resample(GroovyNode):
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"audio": ("AUDIO",)}, "optional": {}}

    def run(
        self, audio: AudioBuffer, target_sample_rate: int = 48000, quality: str = "good", **kwargs
    ) -> tuple[AudioBuffer]:
        target_sample_rate = int(kwargs.get("target_sample_rate", target_sample_rate))
        _, pcm = self._ctx.cache.load_audio(audio.id)
        if audio.sample_rate == target_sample_rate:
            return (audio,)

        ratio = target_sample_rate / audio.sample_rate
        new_length = int(round(pcm.shape[1] * ratio))
        resampled = signal.resample(pcm, new_length, axis=1)

        buffer = AudioBuffer.from_planar(
            resampled,
            target_sample_rate,
            source_node_type="Resample",
            channel_layout=audio.channel_layout,
        )
        self._ctx.cache.write_audio(buffer, resampled)
        return (buffer,)


@register_node
class Trim(GroovyNode):
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"audio": ("AUDIO",)}, "optional": {}}

    def run(
        self, audio: AudioBuffer, start_frame: int = 0, end_frame: int = -1, **kwargs
    ) -> tuple[AudioBuffer]:
        start_frame = int(kwargs.get("start_frame", start_frame))
        end_frame = int(kwargs.get("end_frame", end_frame))
        _, pcm = self._ctx.cache.load_audio(audio.id)
        start = max(0, start_frame)
        end = pcm.shape[1] if end_frame < 0 else min(pcm.shape[1], end_frame)
        trimmed = pcm[:, start:end]
        buffer = AudioBuffer.from_planar(
            trimmed,
            audio.sample_rate,
            source_node_type="Trim",
            channel_layout=audio.channel_layout,
        )
        self._ctx.cache.write_audio(buffer, trimmed)
        return (buffer,)


@register_node
class Mix(GroovyNode):
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"a": ("AUDIO",), "b": ("AUDIO",)},
            "optional": {
                "gain_a": ("FLOAT", {"default": 1.0}),
                "gain_b": ("FLOAT", {"default": 1.0}),
            },
        }

    def run(
        self,
        a: AudioBuffer,
        b: AudioBuffer,
        gain_a: float = 1.0,
        gain_b: float = 1.0,
        **kwargs,
    ) -> tuple[AudioBuffer]:
        gain_a = float(kwargs.get("gain_a", gain_a))
        gain_b = float(kwargs.get("gain_b", gain_b))
        _, pcm_a = self._ctx.cache.load_audio(a.id)
        _, pcm_b = self._ctx.cache.load_audio(b.id)
        if a.sample_rate != b.sample_rate:
            raise ValueError("Sample rate mismatch — insert Resample node")
        if a.channels != b.channels:
            raise ValueError("Channel layout mismatch — insert ChannelConvert node")

        max_frames = max(pcm_a.shape[1], pcm_b.shape[1])
        if pcm_a.shape[1] < max_frames:
            pcm_a = np.pad(pcm_a, ((0, 0), (0, max_frames - pcm_a.shape[1])))
        if pcm_b.shape[1] < max_frames:
            pcm_b = np.pad(pcm_b, ((0, 0), (0, max_frames - pcm_b.shape[1])))

        mixed = pcm_a * gain_a + pcm_b * gain_b
        buffer = AudioBuffer.from_planar(
            mixed,
            a.sample_rate,
            source_node_type="Mix",
            channel_layout=a.channel_layout,
        )
        self._ctx.cache.write_audio(buffer, mixed)
        return (buffer,)


@register_node
class Normalize(GroovyNode):
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "mode": ("STRING", {"default": "lufs"}),
                "target_lufs": ("FLOAT", {"default": -16.0}),
                "target_peak_db": ("FLOAT", {"default": -1.0}),
            },
        }

    def run(self, audio: AudioBuffer, **kwargs) -> tuple[AudioBuffer]:
        mode = str(kwargs.get("mode", "lufs"))
        target_lufs = float(kwargs.get("target_lufs", -16.0))
        target_peak_db = float(kwargs.get("target_peak_db", -1.0))

        _, pcm = self._ctx.cache.load_audio(audio.id)
        out = pcm.copy()

        if mode == "peak":
            peak = np.max(np.abs(out)) or 1.0
            target_linear = 10 ** (target_peak_db / 20)
            out = out * (target_linear / peak)
        else:
            import pyloudnorm as pyln

            meter = pyln.Meter(audio.sample_rate)
            interleaved = out.T
            loudness = meter.integrated_loudness(interleaved)
            if loudness > -100:
                out = pyln.normalize.loudness(interleaved, loudness, target_lufs).T

        buffer = AudioBuffer.from_planar(
            out,
            audio.sample_rate,
            source_node_type="Normalize",
            channel_layout=audio.channel_layout,
        )
        self._ctx.cache.write_audio(buffer, out)
        return (buffer,)


@register_node
class Preview(GroovyNode):
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"audio": ("AUDIO",)}, "optional": {}}

    def run(self, audio: AudioBuffer, **kwargs) -> tuple[AudioBuffer]:
        return (audio,)


@register_node
class StemPick(GroovyNode):
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"stems": ("STEMS",)},
            "optional": {"stem": ("STRING", {"default": "vocals"})},
        }

    def run(self, stems: StemsBuffer, stem: str = "vocals", **kwargs) -> tuple[AudioBuffer]:
        stem = str(kwargs.get("stem", stem))
        if stem not in stems.stems:
            raise ValueError(f"Unknown stem '{stem}'. Available: {', '.join(stems.stems)}")
        return (stems.stems[stem],)
