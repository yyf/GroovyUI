from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
from groovy.executor.audio import AudioBuffer, StemsBuffer
from groovy.executor.audio_meta import (
    apply_file_probe,
    channel_layout_for_channels,
    channel_map_for_layout,
    inherit_format_meta,
    probe_audio_file,
)
from groovy.executor.authenticity import AuthenticityReport, verify_provenance_for_audio
from groovy.executor.control import AutomationBuffer
from groovy.executor.midi import MidiBuffer
from groovy.node import GroovyNode, register_node
from groovy.nodes.core.immersive import register_immersive
from groovy.nodes.core.live_io import register_live_io
from groovy.nodes.core.modular_io import register_modular_io
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
        VerifyProvenance,
        AuthenticitySummary,
        Prompt,
        LoadMIDI,
        ChannelConvert,
        Transcode,
        MultichannelNormalize,
        ControlCurve,
        MIDIToFloat,
        MIDINoteGate,
        AutomationApply,
        FloatMath,
        FloatRoute,
    )
    register_immersive()
    register_modular_io()
    register_live_io()


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

        probe = probe_audio_file(resolved)
        buffer = AudioBuffer.from_planar(
            pcm,
            sample_rate,
            source_node_type="LoadAudio",
            channel_layout=channel_layout_for_channels(pcm.shape[0]),
        )
        apply_file_probe(buffer, probe)
        meta_extra: dict = {"source_path": path}
        sidecar = resolved.with_name(f"{resolved.stem}.provenance.json")
        if sidecar.exists():
            meta_extra["imported_provenance"] = json.loads(sidecar.read_text())
        self._ctx.cache.write_audio(buffer, pcm)
        if meta_extra:
            meta_path = self._ctx.cache.cache_dir / f"{buffer.id}.meta.json"
            meta = json.loads(meta_path.read_text())
            meta.update(meta_extra)
            meta_path.write_text(json.dumps(meta, indent=2))
        return (buffer,)


@register_node
class SaveAudio(GroovyNode):
    RETURN_TYPES = ("STRING",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "path": (
                    "STRING",
                    {
                        "default": "exports",
                        "description": "Folder under the project directory (e.g. exports/podcast)",
                    },
                ),
                "filename": (
                    "STRING",
                    {
                        "default": "output.wav",
                        "description": "File name including extension",
                    },
                ),
                "format": ("STRING", {"default": "wav"}),
                "bit_depth": ("STRING", {"default": "float"}),
            },
        }

    @staticmethod
    def _resolve_output_relative(path: str, filename: str) -> str:
        folder = (path or "").strip().strip("/")
        name = (filename or "").strip().lstrip("/")
        if not name:
            name = "output.wav"
        # Legacy workflows stored the full relative path in filename only.
        if "/" in name and (not folder or folder == "exports"):
            return name
        if folder:
            return f"{folder}/{name}"
        return name

    def run(
        self,
        audio: AudioBuffer,
        path: str = "exports",
        filename: str = "output.wav",
        format: str = "wav",
        bit_depth: str = "float",
        **kwargs,
    ) -> tuple[str]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        folder = str(kwargs.get("path", path))
        name = str(kwargs.get("filename", filename))
        fmt = str(kwargs.get("format", format))
        depth = str(kwargs.get("bit_depth", bit_depth))
        relative = self._resolve_output_relative(folder, name)
        out_path = self._ctx.cache.resolve_project_path(relative)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        _, pcm = self._ctx.cache.load_audio(audio.id)
        interleaved = pcm.T
        subtype = "FLOAT" if depth == "float" else "PCM_24"
        sf.write(out_path, interleaved, audio.sample_rate, format=fmt.upper(), subtype=subtype)
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
        inherit_format_meta(buffer, audio)
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
        inherit_format_meta(buffer, audio)
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
        inherit_format_meta(buffer, audio)
        self._ctx.cache.write_audio(buffer, out)
        return (buffer,)


@register_node
class MultichannelNormalize(GroovyNode):
    CATEGORY = "GroovyUI/Immersive"
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "target_lufs": ("FLOAT", {"default": -23.0}),
                "target_peak_db": ("FLOAT", {"default": -1.0}),
                "mode": ("STRING", {"default": "lufs"}),
            },
        }

    def run(self, audio: AudioBuffer, **kwargs) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        target_lufs = float(kwargs.get("target_lufs", -23.0))
        target_peak_db = float(kwargs.get("target_peak_db", -1.0))
        mode = str(kwargs.get("mode", "lufs"))
        _, pcm = self._ctx.cache.load_audio(audio.id)
        out = pcm.copy()
        if mode == "peak":
            peak = np.max(np.abs(out)) or 1.0
            target_linear = 10 ** (target_peak_db / 20)
            out = out * (target_linear / peak)
            encoding = f"Peak normalize ({target_peak_db} dBFS)"
        else:
            import pyloudnorm as pyln

            meter = pyln.Meter(audio.sample_rate)
            interleaved = out.T
            loudness = meter.integrated_loudness(interleaved)
            if loudness > -100:
                out = pyln.normalize.loudness(interleaved, loudness, target_lufs).T
            encoding = f"EBU R128 integrated ({target_lufs} LUFS)"
        buffer = AudioBuffer.from_planar(
            out,
            audio.sample_rate,
            source_node_type="MultichannelNormalize",
            channel_layout=audio.channel_layout,
        )
        inherit_format_meta(
            buffer,
            audio,
            encoding_scheme=encoding,
            spatial_meta={**audio.spatial_meta, "loudness_mode": mode},
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


@register_node
class VerifyProvenance(GroovyNode):
    CATEGORY = "GroovyUI/Core"
    RETURN_TYPES = ("AUTHENTICITY",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "check_sidecar": ("BOOL", {"default": True}),
            },
        }

    def run(self, audio: AudioBuffer, check_sidecar: bool = True, **kwargs) -> tuple[AuthenticityReport]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        check_sidecar = bool(kwargs.get("check_sidecar", check_sidecar))
        meta = self._ctx.cache.read_meta(audio.id)
        source_path = meta.get("source_path")
        prov_check = verify_provenance_for_audio(
            self._ctx.cache,
            audio.id,
            source_path=str(source_path) if source_path else None,
            check_sidecar=check_sidecar,
        )
        report = AuthenticityReport.create({"provenance_check": prov_check})
        self._ctx.cache.write_authenticity(report)
        return (report,)


@register_node
class AuthenticitySummary(GroovyNode):
    CATEGORY = "GroovyUI/Core"
    RETURN_TYPES = ("AUTHENTICITY",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "provenance_report": ("AUTHENTICITY",),
                "ml_report": ("AUTHENTICITY",),
                "spoof_threshold": ("FLOAT", {"default": 0.5}),
            },
        }

    def run(
        self,
        provenance_report: AuthenticityReport | None = None,
        ml_report: AuthenticityReport | None = None,
        spoof_threshold: float = 0.5,
        **kwargs,
    ) -> tuple[AuthenticityReport]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        prov = kwargs.get("provenance_report", provenance_report)
        ml = kwargs.get("ml_report", ml_report)
        threshold = float(kwargs.get("spoof_threshold", spoof_threshold))
        from groovy.executor.authenticity import merge_authenticity_reports

        merged = merge_authenticity_reports(prov, ml, spoof_threshold=threshold)
        self._ctx.cache.write_authenticity(merged)
        return (merged,)


@register_node
class Prompt(GroovyNode):
    CATEGORY = "GroovyUI/Core"
    RETURN_TYPES = ("STRING",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "text": ("STRING", {"default": "Hello from GroovyUI.", "multiline": True}),
                "language": ("STRING", {"default": "en"}),
            },
        }

    def run(self, text: str = "Hello from GroovyUI.", **kwargs) -> tuple[str]:
        return (str(kwargs.get("text", text)),)


@register_node
class LoadMIDI(GroovyNode):
    CATEGORY = "GroovyUI/Core"
    PROVENANCE_CLASS = "human_recorded"
    RETURN_TYPES = ("MIDI",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"path": ("STRING", {"default": ""})},
            "optional": {
                "midi_kind": ("STRING", {"default": "control"}),
            },
        }

    def run(self, path: str = "", midi_kind: str = "control", **kwargs) -> tuple[MidiBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        path = str(kwargs.get("path", path))
        midi_kind = str(kwargs.get("midi_kind", midi_kind))
        resolved = self._ctx.cache.resolve_project_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"FILE_NOT_FOUND: {path}")
        midi = MidiBuffer.create(
            sample_rate=48000,
            frame_count=48000,
            source_node_type="LoadMIDI",
            midi_kind=midi_kind,
        )
        self._ctx.cache.write_midi(midi, resolved.read_bytes())
        return (midi,)


@register_node
class ChannelConvert(GroovyNode):
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {"layout": ("STRING", {"default": "mono"})},
        }

    def run(self, audio: AudioBuffer, layout: str = "mono", **kwargs) -> tuple[AudioBuffer]:
        layout = str(kwargs.get("layout", layout))
        _, pcm = self._ctx.cache.load_audio(audio.id)
        source_layout = audio.channel_layout
        if layout == "mono" and pcm.shape[0] > 1:
            pcm = pcm.mean(axis=0, keepdims=True)
        elif layout == "stereo" and pcm.shape[0] == 1:
            pcm = np.vstack([pcm[0], pcm[0]])
        elif layout == "stereo" and pcm.shape[0] == 6 and source_layout in {"5.1", "custom"}:
            fl, fr, fc, _lfe, bl, br = pcm
            scale = 0.70710678
            pcm = np.vstack([fl + scale * fc + scale * bl, fr + scale * fc + scale * br])
        elif layout == "stereo" and pcm.shape[0] == 8 and source_layout in {"7.1", "7.1.4", "custom"}:
            fl, fr, fc, _lfe, bl, br, sl, sr = pcm
            scale = 0.70710678
            pcm = np.vstack(
                [
                    fl + scale * fc + scale * bl + scale * sl,
                    fr + scale * fc + scale * br + scale * sr,
                ]
            )
        elif layout == "stereo" and pcm.shape[0] > 2:
            pcm = pcm[:2]
        buffer = AudioBuffer.from_planar(
            pcm,
            audio.sample_rate,
            source_node_type="ChannelConvert",
            channel_layout=layout,
        )
        format_overrides: dict = {
            "channel_map": channel_map_for_layout(layout, pcm.shape[0]),
        }
        if layout == "stereo" and source_layout in {"5.1", "7.1", "7.1.4", "custom"} and pcm.shape[0] == 2:
            format_overrides["encoding_scheme"] = "ITU-R BS.775 stereo downmix"
            format_overrides["layout_order"] = None
            format_overrides["spatial_meta"] = {
                **audio.spatial_meta,
                "downmixed_from": source_layout,
            }
        elif layout == "mono" and audio.channels > 1:
            format_overrides["encoding_scheme"] = f"Mono fold ({source_layout})"
            format_overrides["layout_order"] = None
        inherit_format_meta(buffer, audio, **format_overrides)
        self._ctx.cache.write_audio(buffer, pcm)
        return (buffer,)


@register_node
class Transcode(GroovyNode):
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "format": ("STRING", {"default": "flac"}),
                "path": ("STRING", {"default": ""}),
            },
        }

    def run(
        self,
        audio: AudioBuffer,
        format: str = "flac",
        path: str = "",
        **kwargs,
    ) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        fmt = str(kwargs.get("format", format)).lower()
        path = str(kwargs.get("path", path))
        _, pcm = self._ctx.cache.load_audio(audio.id)
        if not path:
            path = f"assets/exports/output.{fmt}"
        dest = self._ctx.cache.resolve_project_path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        exported_with = "soundfile"
        if fmt in {"mp3", "aac", "opus"}:
            import shutil
            import subprocess

            if shutil.which("ffmpeg"):
                wav_tmp = dest.with_suffix(".tmp.wav")
                sf.write(wav_tmp, pcm.T, audio.sample_rate, format="WAV", subtype="PCM_16")
                codec = {"mp3": "libmp3lame", "aac": "aac", "opus": "libopus"}[fmt]
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(wav_tmp),
                        "-acodec",
                        codec,
                        str(dest),
                    ],
                    check=True,
                    capture_output=True,
                )
                wav_tmp.unlink(missing_ok=True)
                exported_with = "ffmpeg"
            else:
                raise RuntimeError(f"ffmpeg required for {fmt} export (not found on PATH)")
        else:
            write_kwargs: dict = {"format": fmt.upper()}
            if fmt == "wav":
                write_kwargs["subtype"] = "PCM_16"
            sf.write(dest, pcm.T, audio.sample_rate, **write_kwargs)
        buffer = AudioBuffer.from_planar(
            pcm,
            audio.sample_rate,
            source_node_type="Transcode",
            channel_layout=audio.channel_layout,
        )
        inherit_format_meta(
            buffer,
            audio,
            spatial_meta={
                **audio.spatial_meta,
                "export_format": fmt.upper(),
                "export_path": path,
                "export_backend": exported_with,
            },
        )
        self._ctx.cache.write_audio(buffer, pcm)
        return (buffer,)


@register_node
class ControlCurve(GroovyNode):
    RETURN_TYPES = ("AUTOMATION",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "start_value": ("FLOAT", {"default": 0.0}),
                "end_value": ("FLOAT", {"default": 1.0}),
                "frame_count": ("INT", {"default": 48000}),
                "sample_rate": ("INT", {"default": 48000}),
            },
        }

    def run(
        self,
        start_value: float = 0.0,
        end_value: float = 1.0,
        frame_count: int = 48000,
        sample_rate: int = 48000,
        **kwargs,
    ) -> tuple[AutomationBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        start_value = float(kwargs.get("start_value", start_value))
        end_value = float(kwargs.get("end_value", end_value))
        frame_count = int(kwargs.get("frame_count", frame_count))
        sample_rate = int(kwargs.get("sample_rate", sample_rate))
        values = np.linspace(start_value, end_value, frame_count)
        curve = AutomationBuffer.from_values(values, sample_rate=sample_rate, source_node_type="ControlCurve")
        self._ctx.cache.write_automation(curve)
        return (curve,)


@register_node
class MIDIToFloat(GroovyNode):
    RETURN_TYPES = ("AUTOMATION",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"midi": ("MIDI",)},
            "optional": {
                "cc": ("INT", {"default": 7}),
                "default_value": ("FLOAT", {"default": 0.75}),
            },
        }

    def run(self, midi: MidiBuffer, cc: int = 7, default_value: float = 0.75, **kwargs) -> tuple[AutomationBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        cc = int(kwargs.get("cc", cc))
        default_value = float(kwargs.get("default_value", default_value))
        from groovy.executor.live_midi import automation_from_midi_events, load_midi_events

        events = load_midi_events(self._ctx.cache, midi.id)
        if events:
            values = automation_from_midi_events(
                events,
                frame_count=midi.frame_count,
                cc=cc,
                default_value=default_value,
            )
        else:
            values = [default_value] * midi.frame_count
        curve = AutomationBuffer.from_values(
            np.asarray(values, dtype=np.float64),
            sample_rate=midi.sample_rate,
            source_node_type="MIDIToFloat",
        )
        self._ctx.cache.write_automation(curve)
        return (curve,)


@register_node
class MIDINoteGate(GroovyNode):
    RETURN_TYPES = ("AUTOMATION",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"midi": ("MIDI",)},
            "optional": {
                "note": ("INT", {"default": 60}),
                "channel": ("INT", {"default": 1}),
            },
        }

    def run(self, midi: MidiBuffer, note: int = 60, channel: int = 1, **kwargs) -> tuple[AutomationBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        note = int(kwargs.get("note", note))
        channel = int(kwargs.get("channel", channel))
        from groovy.executor.live_midi import load_midi_events

        events = load_midi_events(self._ctx.cache, midi.id)
        values = np.zeros(midi.frame_count, dtype=np.float64)
        active = False
        for event in sorted(events, key=lambda item: int(item.get("frame", 0))):
            if event.get("type") not in {"note_on", "note_off"}:
                continue
            if int(event.get("channel", 0)) != channel:
                continue
            if int(event.get("note", -1)) != note:
                continue
            frame = max(0, min(midi.frame_count - 1, int(event.get("frame", 0))))
            if event.get("type") == "note_on" and float(event.get("velocity", 0)) > 0:
                active = True
            else:
                active = False
            values[frame:] = 1.0 if active else 0.0
        curve = AutomationBuffer.from_values(
            values, sample_rate=midi.sample_rate, source_node_type="MIDINoteGate"
        )
        self._ctx.cache.write_automation(curve)
        return (curve,)


@register_node
class AutomationApply(GroovyNode):
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "curve": ("AUTOMATION",),
                "gain": ("FLOAT", {"default": 1.0}),
            },
        }

    def run(
        self,
        audio: AudioBuffer,
        curve: AutomationBuffer | None = None,
        gain: float = 1.0,
        **kwargs,
    ) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        gain = float(kwargs.get("gain", gain))
        curve = kwargs.get("curve", curve)
        _, pcm = self._ctx.cache.load_audio(audio.id)
        if curve is not None:
            envelope = curve.resample_to(pcm.shape[1]) * gain
            pcm = pcm * envelope.reshape(1, -1)
        else:
            pcm = pcm * gain
        buffer = AudioBuffer.from_planar(
            pcm,
            audio.sample_rate,
            source_node_type="AutomationApply",
            channel_layout=audio.channel_layout,
        )
        inherit_format_meta(buffer, audio)
        self._ctx.cache.write_audio(buffer, pcm)
        return (buffer,)


@register_node
class FloatMath(GroovyNode):
    RETURN_TYPES = ("AUTOMATION",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "a": ("AUTOMATION",),
                "b": ("AUTOMATION",),
                "operation": ("STRING", {"default": "add"}),
            },
        }

    def run(
        self,
        a: AutomationBuffer | None = None,
        b: AutomationBuffer | None = None,
        operation: str = "add",
        **kwargs,
    ) -> tuple[AutomationBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        a = kwargs.get("a", a)
        b = kwargs.get("b", b)
        operation = str(kwargs.get("operation", operation))
        if a is None or b is None:
            raise ValueError("FloatMath requires two AUTOMATION inputs")
        length = max(a.frame_count, b.frame_count)
        va = a.resample_to(length)
        vb = b.resample_to(length)
        if operation == "multiply":
            values = va * vb
        else:
            values = va + vb
        curve = AutomationBuffer.from_values(
            values, sample_rate=a.sample_rate, source_node_type="FloatMath"
        )
        self._ctx.cache.write_automation(curve)
        return (curve,)


@register_node
class FloatRoute(GroovyNode):
    RETURN_TYPES = ("AUTOMATION",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "a": ("AUTOMATION",),
                "b": ("AUTOMATION",),
                "select": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0}),
            },
        }

    def run(
        self,
        a: AutomationBuffer | None = None,
        b: AutomationBuffer | None = None,
        select: float = 0.0,
        **kwargs,
    ) -> tuple[AutomationBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        a = kwargs.get("a", a)
        b = kwargs.get("b", b)
        select = float(kwargs.get("select", select))
        if a is None and b is None:
            raise ValueError("FloatRoute requires at least one AUTOMATION input")
        if a is None:
            return (b,)
        if b is None:
            return (a,)
        length = max(a.frame_count, b.frame_count)
        va = a.resample_to(length)
        vb = b.resample_to(length)
        blend = float(np.clip(select, 0.0, 1.0))
        values = va * (1.0 - blend) + vb * blend
        curve = AutomationBuffer.from_values(
            values, sample_rate=a.sample_rate, source_node_type="FloatRoute"
        )
        self._ctx.cache.write_automation(curve)
        return (curve,)

