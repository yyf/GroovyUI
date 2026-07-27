from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import soundfile as sf
from groovy.executor.audio import AudioBuffer
from groovy.executor.audio_meta import (
    apply_file_probe,
    channel_layout_for_channels,
    channel_map_for_layout,
    inherit_format_meta,
    probe_audio_file,
)
from groovy.executor.authenticity import AuthenticityReport, verify_provenance_for_audio
from groovy.executor.content_credentials import (
    build_content_credentials_manifest,
    process_content_credentials,
)
from groovy.executor.control import AutomationBuffer
from groovy.executor.media_io import read_audio_pcm, write_audio_ffmpeg, write_uses_ffmpeg
from groovy.executor.midi import MidiBuffer
from groovy.executor.project_paths import resolve_project_media_path
from groovy.executor.provenance import build_lineage_graph
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
        Note,
        VerifyProvenance,
        AuthenticitySummary,
        Prompt,
        LoadMIDI,
        ChannelConvert,
        Transcode,
        MultichannelNormalize,
        SignalGenerator,
        ControlCurve,
        MIDIToFloat,
        MIDINoteGate,
        AutomationApply,
        FloatMath,
        FloatRoute,
        Granulate,
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
                "path": ("STRING", {"default": "assets/samples/male-1.wav"}),
            },
            "optional": {
                "start_frame": ("INT", {"default": 0}),
                "end_frame": ("INT", {"default": -1}),
                "audio_stream": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 31,
                        "description": (
                            "Audio stream index for multi-stream files "
                            "(OpenSTEM .stem.mp4 mix = 0)"
                        ),
                    },
                ),
            },
        }

    def run(self, **kwargs) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        path = str(kwargs.get("path", ""))
        start_frame = int(kwargs.get("start_frame", 0))
        end_frame = int(kwargs.get("end_frame", -1))
        audio_stream = int(kwargs.get("audio_stream", 0))
        resolved, canonical_path = resolve_project_media_path(self._ctx.cache, path)

        try:
            pcm, sample_rate = read_audio_pcm(resolved, stream_index=audio_stream)
        except Exception as exc:
            raise RuntimeError(
                f"UNSUPPORTED_FORMAT: {canonical_path} — {exc}. "
                "Supported: WAV/FLAC/AIFF via libsndfile; "
                "MP4/M4A/AAC/MP3/OGG via ffmpeg."
            ) from exc

        start = max(0, start_frame)
        end = pcm.shape[1] if end_frame < 0 else min(pcm.shape[1], end_frame)
        pcm = pcm[:, start:end]

        probe = probe_audio_file(resolved)
        channel_count = pcm.shape[0]
        channel_layout = channel_layout_for_channels(channel_count)

        meta_extra: dict = {
            "source_path": canonical_path,
            "audio_stream": audio_stream,
        }
        sidecar = resolved.with_name(f"{resolved.stem}.provenance.json")
        if sidecar.exists():
            meta_extra["imported_provenance"] = json.loads(sidecar.read_text())

        # Multi-channel routing: for a loaded N-channel file, return N distinct AUDIO outputs
        # (one per channel). Each outlet preserves the original channel layout, but masks
        # all other channels to zeros so downstream nodes can independently process channels.
        if channel_count <= 1:
            buffer = AudioBuffer.from_planar(
                pcm,
                sample_rate,
                source_node_type="LoadAudio",
                channel_layout=channel_layout,
            )
            apply_file_probe(buffer, probe)
            self._ctx.cache.write_audio(buffer, pcm)
            if meta_extra:
                meta_path = self._ctx.cache.cache_dir / f"{buffer.id}.meta.json"
                meta = json.loads(meta_path.read_text())
                meta.update(meta_extra)
                meta_path.write_text(json.dumps(meta, indent=2))
            return (buffer,)

        buffers: list[AudioBuffer] = []
        for channel_index in range(channel_count):
            masked = np.zeros_like(pcm)
            masked[channel_index, :] = pcm[channel_index, :]

            buffer = AudioBuffer.from_planar(
                masked,
                sample_rate,
                source_node_type="LoadAudio",
                channel_layout=channel_layout,
            )
            apply_file_probe(buffer, probe)

            channel_meta = {**meta_extra, "channel_index": channel_index}
            self._ctx.cache.write_audio(buffer, masked)
            if channel_meta:
                meta_path = self._ctx.cache.cache_dir / f"{buffer.id}.meta.json"
                meta = json.loads(meta_path.read_text())
                meta.update(channel_meta)
                meta_path.write_text(json.dumps(meta, indent=2))

            buffers.append(buffer)

        return tuple(buffers)


@register_node
class SaveAudio(GroovyNode):
    RETURN_TYPES = ("STRING",)
    # Writes a timestamped file + provenance sidecar on every render; never cache.
    CACHEABLE = False
    BIT_DEPTH_SUBTYPES = {
        "16": "PCM_16",
        "24": "PCM_24",
        "32": "PCM_32",
        "float": "FLOAT",
    }

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
                        "description": (
                            "Base file name; its extension follows Format and a UTC timestamp "
                            "is appended when written"
                        ),
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

    @staticmethod
    def _timestamped_relative(relative: str, now: datetime | None = None) -> str:
        instant = now or datetime.now(UTC)
        stamp = (
            instant.strftime("%Y%m%dT%H%M%S")
            + f"{instant.microsecond // 1000:03d}Z"
        )
        path = Path(relative)
        return str(path.with_name(f"{path.stem}-{stamp}{path.suffix}"))

    @staticmethod
    def _with_format_extension(relative: str, format: str) -> str:
        extension = format.strip().lower()
        if not extension:
            raise ValueError("Audio format cannot be empty.")
        return str(Path(relative).with_suffix(f".{extension}"))

    @classmethod
    def _subtype_for(cls, format: str, bit_depth: str) -> str:
        fmt = format.strip().upper()
        depth = bit_depth.strip().lower()
        subtype = cls.BIT_DEPTH_SUBTYPES.get(depth)
        if subtype is None:
            choices = ", ".join(cls.BIT_DEPTH_SUBTYPES)
            raise ValueError(f"Unsupported bit depth: {bit_depth}. Choose one of: {choices}.")
        if not sf.check_format(fmt, subtype):
            raise ValueError(f"{format.upper()} does not support {bit_depth}-bit audio.")
        return subtype

    def run(
        self,
        audio: AudioBuffer | None = None,
        path: str = "exports",
        filename: str = "output.wav",
        format: str = "wav",
        bit_depth: str = "float",
        **kwargs,
    ) -> tuple[str]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        audio_in = kwargs["audio"] if "audio" in kwargs else audio
        if not isinstance(audio_in, AudioBuffer):
            raise TypeError(
                "SaveAudio needs AUDIO input — wire LoadAudio/Denoise/etc., "
                "not Preview text (wire Preview.audio or the original LoadAudio instead)"
            )
        folder = str(kwargs.get("path", path))
        name = str(kwargs.get("filename", filename))
        fmt = str(kwargs.get("format", format))
        depth = str(kwargs.get("bit_depth", bit_depth))
        relative = self._resolve_output_relative(folder, name)
        relative = self._with_format_extension(relative, fmt)
        relative = self._timestamped_relative(relative)
        out_path = self._ctx.cache.resolve_project_path(relative)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        unsigned_path = out_path.with_name(
            f".{out_path.stem}-{token}.unsigned{out_path.suffix}"
        )
        signed_path = out_path.with_name(
            f".{out_path.stem}-{token}.signed{out_path.suffix}"
        )
        sidecar_path = out_path.with_name(f"{out_path.stem}.provenance.json")

        _, pcm = self._ctx.cache.load_audio(audio_in.id)
        interleaved = pcm.T
        fmt_lower = fmt.strip().lower()
        if write_uses_ffmpeg(fmt_lower):
            write_audio_ffmpeg(
                unsigned_path,
                pcm,
                audio_in.sample_rate,
                format_name=fmt_lower,
            )
        else:
            subtype = self._subtype_for(fmt, depth)
            sf.write(
                unsigned_path,
                interleaved,
                audio_in.sample_rate,
                format=fmt.upper(),
                subtype=subtype,
            )
        # A successful SaveAudio render always produces the paired provenance
        # artifact. Missing provenance or a failed sidecar write must fail the
        # node instead of silently leaving an incomplete handoff.
        try:
            provenance = self._ctx.cache.read_provenance(audio_in.id)
            if not provenance:
                raise FileNotFoundError(
                    f"No provenance for cache entry: {audio_in.id}"
                )
            portable_provenance = {
                **provenance,
                "lineage": build_lineage_graph(self._ctx.cache, audio_in.id),
            }
            groovy_version = str(
                provenance.get("origin", {}).get("groovy_version") or "unknown"
            )
            manifest = build_content_credentials_manifest(
                portable_provenance,
                title=out_path.name,
                claim_generator=f"GroovyUI/{groovy_version}",
            )
            credentials = process_content_credentials(
                signer=self._ctx.content_credential_signer,
                mode=self._ctx.content_credentials_mode,
                source=unsigned_path,
                destination=signed_path,
                manifest=manifest,
            )
            signed_path.replace(out_path)
            self._ctx.cache.export_provenance_sidecar(
                audio_in.id,
                out_path,
                content_credentials=credentials.to_dict(),
            )
        except Exception as exc:
            unsigned_path.unlink(missing_ok=True)
            signed_path.unlink(missing_ok=True)
            out_path.unlink(missing_ok=True)
            sidecar_path.unlink(missing_ok=True)
            sidecar_path.with_suffix(f"{sidecar_path.suffix}.tmp").unlink(
                missing_ok=True
            )
            raise RuntimeError(
                f"SaveAudio could not write provenance sidecar or publish "
                f"complete export for {relative}: {exc}"
            ) from exc
        return (str(out_path),)


@register_node
class Resample(GroovyNode):
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "target_sample_rate": ("INT", {"default": 48000, "min": 8000, "max": 192000}),
                "quality": ("STRING", {"default": "good"}),
            },
        }

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
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "start_frame": ("INT", {"default": 0, "min": 0}),
                "end_frame": ("INT", {"default": -1}),
            },
        }

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
    """Terminal audition/inspection sink — wire audio and/or text."""

    PROVENANCE_PASSTHROUGH = True
    # Declared AUDIO for schema/handle; TEXT-only returns are emitted as TEXT via the executor.
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        # Slot 0 stays audio so existing templates (to: [preview, 0]) keep working.
        return {
            "required": {},
            "optional": {
                "audio": ("AUDIO",),
                "text": ("TEXT",),
            },
        }

    def run(self, **kwargs) -> tuple[AudioBuffer] | tuple[str]:
        # Prefer audio when present so waveform, transport, and SaveAudio chaining keep working.
        # Text may be wired alongside audio; the executor attaches it on output meta.
        audio_in = kwargs.get("audio")
        text_in = kwargs.get("text")
        if audio_in is None and text_in is None:
            raise ValueError("Preview needs a wired audio or text input")
        if audio_in is not None:
            return (audio_in,)
        return (str(text_in),)


@register_node
class Note(GroovyNode):
    """Canvas annotation — comments only; no sockets and no render output."""

    CATEGORY = "GroovyUI/Core"
    EXPORT_TIER = "STUDIO_ONLY"
    SAMPLE_ACCURATE = False
    DETERMINISTIC = True
    CACHEABLE = True
    PROVENANCE_CLASS = "human_edited"
    RETURN_TYPES = ()

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "text": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "description": "Freeform comment shown on the canvas.",
                    },
                ),
            },
        }

    def run(self, text: str = "", **kwargs) -> tuple:
        _ = str(kwargs.get("text", text))
        return ()


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
        resolved, _canonical_path = resolve_project_media_path(self._ctx.cache, path)
        from groovy.executor.live_midi import events_from_smf, write_midi_events_meta

        sample_rate = 48000
        midi_bytes = resolved.read_bytes()
        try:
            events, frame_count = events_from_smf(resolved, sample_rate=sample_rate)
        except Exception:
            events, frame_count = [], sample_rate
        midi = MidiBuffer.create(
            sample_rate=sample_rate,
            frame_count=frame_count,
            source_node_type="LoadMIDI",
            midi_kind=midi_kind,
        )
        self._ctx.cache.write_midi(midi, midi_bytes)
        if events:
            write_midi_events_meta(self._ctx.cache, midi, events)
        return (midi,)


@register_node
class SignalGenerator(GroovyNode):
    """Offline oscillator building block.

    Phase-accumulates *frequency* (Hz), then:
      y = amplitude · wave(φ + phase_mod)

    Patch classic FM/PM as:
      mod  = Osc(f_m, amplitude=I)          → I·sin(2π f_m t)
      out  = Osc(f_c, amplitude=A_c, phase_mod=mod)
           = A_c · sin(2π f_c t + I·sin(2π f_m t))

    With I = Δf / f_m via FloatMath(divide) into the modulator amplitude.
    """

    CATEGORY = "GroovyUI/Core"
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
                "waveform": ("STRING", {"default": "sine"}),
                "frequency_hz": ("FLOAT", {"default": 440.0, "min": 1.0, "max": 20000.0}),
                "amplitude_default": ("FLOAT", {"default": 0.4, "min": 0.0, "max": 8.0}),
                "duration_sec": ("FLOAT", {"default": 2.0, "min": 0.05, "max": 60.0}),
                "sample_rate": ("INT", {"default": 48000, "min": 8000, "max": 192000}),
            },
        }

    def run(self, **kwargs) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        freq_curve = kwargs.get("frequency")
        amp_curve = kwargs.get("amplitude")
        phase_mod = kwargs.get("phase_mod")
        waveform = str(kwargs.get("waveform", "sine")).lower().strip()
        freq_default = float(np.clip(float(kwargs.get("frequency_hz", 440.0)), 1.0, 20000.0))
        amp_default = float(np.clip(float(kwargs.get("amplitude_default", 0.4)), 0.0, 8.0))
        duration_sec = float(np.clip(float(kwargs.get("duration_sec", 2.0)), 0.05, 60.0))
        sample_rate = int(np.clip(int(kwargs.get("sample_rate", 48000)), 8000, 192000))
        frame_count = max(1, int(round(duration_sec * sample_rate)))

        freq = _automation_or_const(freq_curve, frame_count, freq_default)
        amp = _automation_or_const(amp_curve, frame_count, amp_default)
        freq = np.clip(freq, 1.0, 20000.0)
        amp = np.clip(amp, 0.0, 8.0)

        dphase = 2.0 * np.pi * freq / sample_rate
        phase = np.cumsum(dphase) - dphase

        if phase_mod is not None:
            _, mod_pcm = self._ctx.cache.load_audio(phase_mod.id)
            mono = mod_pcm.mean(axis=0) if mod_pcm.ndim == 2 else mod_pcm.reshape(-1)
            if mono.size != frame_count:
                x_old = np.linspace(0.0, 1.0, max(1, mono.size))
                x_new = np.linspace(0.0, 1.0, frame_count)
                mono = np.interp(x_new, x_old, mono.astype(np.float64))
            phase = phase + mono.astype(np.float64)

        wave = _oscillator_from_phase(phase, waveform) * amp
        pcm = wave.reshape(1, -1)
        buffer = AudioBuffer.from_planar(
            pcm,
            sample_rate,
            source_node_type="SignalGenerator",
            channel_layout="mono",
        )
        self._ctx.cache.write_audio(buffer, pcm)
        return (buffer,)


def _automation_or_const(
    curve: AutomationBuffer | None,
    frame_count: int,
    default: float,
) -> np.ndarray:
    if curve is None:
        return np.full(frame_count, float(default), dtype=np.float64)
    return np.asarray(curve.resample_to(frame_count), dtype=np.float64)


def _oscillator_from_phase(phase: np.ndarray, waveform: str) -> np.ndarray:
    """Band-limited-enough offline waveshapes from an unwrapped phase ramp."""
    if waveform in {"saw", "sawtooth"}:
        return 2.0 * (np.mod(phase / (2.0 * np.pi), 1.0) - 0.5)
    if waveform in {"square", "sq"}:
        return np.where(np.mod(phase, 2.0 * np.pi) < np.pi, 1.0, -1.0)
    if waveform in {"triangle", "tri"}:
        saw = 2.0 * (np.mod(phase / (2.0 * np.pi), 1.0) - 0.5)
        return 2.0 * np.abs(saw) - 1.0
    return np.sin(phase)


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
        if fmt in {"mp3", "aac", "opus", "mp4", "m4a"}:
            from groovy.executor.media_io import write_audio_ffmpeg, write_uses_ffmpeg

            if write_uses_ffmpeg(fmt) or fmt == "opus":
                if fmt == "opus":
                    import shutil
                    import subprocess

                    if not shutil.which("ffmpeg"):
                        raise RuntimeError("ffmpeg required for opus export (not found on PATH)")
                    wav_tmp = dest.with_suffix(".tmp.wav")
                    sf.write(wav_tmp, pcm.T, audio.sample_rate, format="WAV", subtype="PCM_16")
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            str(wav_tmp),
                            "-acodec",
                            "libopus",
                            str(dest),
                        ],
                        check=True,
                        capture_output=True,
                    )
                    wav_tmp.unlink(missing_ok=True)
                else:
                    write_audio_ffmpeg(dest, pcm, audio.sample_rate, format_name=fmt)
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
                # JSON list of {t,v} with t in [0,1]; edited in Node Helper curve UI.
                "points": (
                    "STRING",
                    {"default": '[{"t":0,"v":0},{"t":1,"v":1}]'},
                ),
            },
        }

    def run(
        self,
        start_value: float = 0.0,
        end_value: float = 1.0,
        frame_count: int = 48000,
        sample_rate: int = 48000,
        points: str = '[{"t":0,"v":0},{"t":1,"v":1}]',
        **kwargs,
    ) -> tuple[AutomationBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        from groovy.executor.control import values_from_curve_points

        start_value = float(kwargs.get("start_value", start_value))
        end_value = float(kwargs.get("end_value", end_value))
        frame_count = int(kwargs.get("frame_count", frame_count))
        sample_rate = int(kwargs.get("sample_rate", sample_rate))
        points = kwargs.get("points", points)
        values = values_from_curve_points(
            points,
            frame_count,
            start_value=start_value,
            end_value=end_value,
        )
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
        elif operation in {"divide", "div"}:
            values = va / np.maximum(vb, 1e-9)
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


def _grain_window(kind: str, length: int, alpha: float) -> np.ndarray:
    """Build a grain envelope. exp/tukey read tighter (more pointillist) than hann."""
    n = max(8, int(length))
    kind = (kind or "hann").strip().lower()
    alpha = float(np.clip(alpha, 0.05, 1.0))
    if kind in {"rect", "rectangular", "boxcar"}:
        return np.ones(n, dtype=np.float64)
    if kind == "tukey":
        # alpha = tapered fraction; higher → closer to Hann, lower → flatter center.
        tap = int(np.floor(alpha * (n - 1) / 2.0))
        if tap <= 0:
            return np.ones(n, dtype=np.float64)
        window = np.ones(n, dtype=np.float64)
        # Cosine taper quantized so Mac/Linux libm ulps cannot drift the golden.
        phase = np.arange(tap, dtype=np.float64) / tap
        taper = 0.5 * (1.0 + np.cos(np.pi * phase - np.pi))
        taper = np.round(taper * (1 << 24)) / (1 << 24)
        window[:tap] = taper
        window[-tap:] = taper[::-1]
        return window
    if kind in {"exp", "exponential"}:
        # Symmetric exponential — energy concentrated in the middle (pointillist).
        x = np.linspace(-1.0, 1.0, n, dtype=np.float64)
        window = np.exp(-3.5 * np.abs(x))
        return np.round(window * (1 << 24)) / (1 << 24)
    # Hann via raised-cosine; quantize to freeze cross-platform libm differences.
    if n == 1:
        return np.ones(1, dtype=np.float64)
    phase = np.arange(n, dtype=np.float64) / (n - 1)
    window = 0.5 - 0.5 * np.cos(2.0 * np.pi * phase)
    return np.round(window * (1 << 24)) / (1 << 24)


def _read_pitched_grain(
    planar: np.ndarray,
    src: int,
    grain: int,
    rate: float,
) -> np.ndarray:
    """Read `grain` samples starting near `src`, pitched by playback `rate` (2^(cents/1200))."""
    channels, n_samples = planar.shape
    rate = float(np.clip(rate, 0.25, 4.0))
    positions = src + np.arange(grain, dtype=np.float64) * rate
    positions = np.clip(positions, 0.0, max(0.0, n_samples - 1.000001))
    i0 = np.floor(positions).astype(np.int64)
    i1 = np.minimum(i0 + 1, n_samples - 1)
    frac = positions - i0
    out = np.empty((channels, grain), dtype=np.float64)
    for ch in range(channels):
        out[ch] = planar[ch, i0] * (1.0 - frac) + planar[ch, i1] * frac
    return out


@register_node
class Granulate(GroovyNode):
    """Offline granulator. Curves drive size, hop, pitch spread, density, and stereo width."""

    CATEGORY = "GroovyUI/Core"
    PROVENANCE_PASSTHROUGH = True
    RETURN_TYPES = ("AUDIO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"audio": ("AUDIO",)},
            "optional": {
                "grain_ms_curve": ("AUTOMATION",),
                "hop_ms_curve": ("AUTOMATION",),
                "pitch_cents_curve": ("AUTOMATION",),
                "density_curve": ("AUTOMATION",),
                "width_curve": ("AUTOMATION",),
                "grain_ms": ("FLOAT", {"default": 50.0, "min": 5.0, "max": 200.0}),
                "hop_ms": ("FLOAT", {"default": 20.0, "min": 1.0, "max": 100.0}),
                "pitch_cents": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1200.0}),
                "density": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 200.0}),
                "spray": ("INT", {"default": 1, "min": 1, "max": 16}),
                "width": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0}),
                "window": ("STRING", {"default": "hann"}),
                "window_alpha": ("FLOAT", {"default": 0.5, "min": 0.05, "max": 1.0}),
                "scatter_ms": ("FLOAT", {"default": 120.0, "min": 0.0, "max": 1000.0}),
                "wet_start": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0}),
                "wet_end": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
            },
        }

    def run(self, audio: AudioBuffer, **kwargs) -> tuple[AudioBuffer]:
        if not self._ctx:
            raise RuntimeError("Node context not bound")
        grain_ms = float(kwargs.get("grain_ms", 50.0))
        hop_ms = float(kwargs.get("hop_ms", 20.0))
        pitch_cents = float(kwargs.get("pitch_cents", 0.0))
        density = float(kwargs.get("density", 0.0))
        spray = max(1, int(kwargs.get("spray", 1)))
        width = float(np.clip(float(kwargs.get("width", 0.0)), 0.0, 1.0))
        window_kind = str(kwargs.get("window", "hann"))
        window_alpha = float(kwargs.get("window_alpha", 0.5))
        scatter_ms = float(kwargs.get("scatter_ms", 120.0))
        wet_start = float(np.clip(float(kwargs.get("wet_start", 0.0)), 0.0, 1.0))
        wet_end = float(np.clip(float(kwargs.get("wet_end", 1.0)), 0.0, 1.0))
        seed = int(kwargs.get("seed", 0))
        grain_curve: AutomationBuffer | None = kwargs.get("grain_ms_curve")
        hop_curve: AutomationBuffer | None = kwargs.get("hop_ms_curve")
        pitch_curve: AutomationBuffer | None = kwargs.get("pitch_cents_curve")
        density_curve: AutomationBuffer | None = kwargs.get("density_curve")
        width_curve: AutomationBuffer | None = kwargs.get("width_curve")

        _, pcm = self._ctx.cache.load_audio(audio.id)
        planar = np.asarray(pcm, dtype=np.float64)
        if planar.ndim == 1:
            planar = planar.reshape(1, -1)
        sr = int(audio.sample_rate)
        in_channels, n_samples = planar.shape
        if n_samples == 0:
            buffer = AudioBuffer.from_planar(
                planar,
                sr,
                source_node_type="Granulate",
                channel_layout=audio.channel_layout,
            )
            inherit_format_meta(buffer, audio)
            self._ctx.cache.write_audio(buffer, planar)
            return (buffer,)

        def series(curve: AutomationBuffer | None, constant: float, lo: float, hi: float) -> np.ndarray:
            if curve is not None:
                return np.clip(curve.resample_to(n_samples), lo, hi)
            return np.full(n_samples, constant, dtype=np.float64)

        grain_ms_series = series(grain_curve, grain_ms, 5.0, 200.0)
        hop_ms_series = series(hop_curve, hop_ms, 1.0, 100.0)
        pitch_series = series(pitch_curve, pitch_cents, 0.0, 1200.0)
        density_series = series(density_curve, density, 0.0, 200.0)
        width_series = series(width_curve, width, 0.0, 1.0)

        max_width = float(np.max(width_series)) if n_samples else 0.0
        out_channels = 2 if max_width > 1e-6 or in_channels >= 2 else 1
        if in_channels == 1 and out_channels == 2:
            source = np.vstack([planar, planar])
        elif in_channels > out_channels:
            source = planar[:out_channels]
        else:
            source = planar

        dry = source
        scatter = max(0, int(round(sr * scatter_ms / 1000.0)))
        rng = np.random.default_rng(seed)
        wet = np.zeros((out_channels, n_samples), dtype=np.float64)
        weight = np.zeros(n_samples, dtype=np.float64)

        onsets: list[int] = []
        out_pos = 0
        while out_pos < n_samples:
            onsets.append(out_pos)
            hop = max(1, int(round(sr * float(hop_ms_series[out_pos]) / 1000.0)))
            out_pos += hop

        dens_pos = 0
        while dens_pos < n_samples:
            d = float(density_series[dens_pos])
            if d > 0.05:
                onsets.append(dens_pos)
                dens_pos += max(1, int(round(sr / d)))
            else:
                dens_pos += max(1, int(round(sr * float(hop_ms_series[dens_pos]) / 1000.0)))

        for onset in sorted(set(onsets)):
            t = onset / max(n_samples - 1, 1)
            amount = wet_start + (wet_end - wet_start) * t
            grain = max(8, int(round(sr * float(grain_ms_series[onset]) / 1000.0)))
            window = _grain_window(window_kind, grain, window_alpha)
            spread = float(pitch_series[onset])
            width_amt = float(width_series[onset])
            scatter_amt = int(round(scatter * amount))
            for spray_i in range(spray):
                # Primary grain stays on the hop onset (golden-stable); spray copies get time jitter.
                if spray_i > 0 and scatter_amt > 0:
                    time_jitter = int(rng.integers(-scatter_amt, scatter_amt + 1))
                else:
                    time_jitter = 0
                place = int(np.clip(onset + time_jitter, 0, max(0, n_samples - 1)))
                src_jitter = int(rng.integers(-scatter_amt, scatter_amt + 1)) if scatter_amt > 0 else 0
                src = int(np.clip(onset + src_jitter, 0, max(0, n_samples - 1)))
                cents = float(rng.uniform(-spread, spread)) if spread > 0 else 0.0
                rate = float(2.0 ** (cents / 1200.0))
                if abs(rate - 1.0) < 1e-12:
                    take = min(grain, n_samples - place, n_samples - src)
                else:
                    take = min(grain, n_samples - place)
                if take <= 0:
                    continue
                if abs(rate - 1.0) < 1e-12:
                    chunk = np.asarray(source[:, src : src + take], dtype=np.float64)
                else:
                    chunk = _read_pitched_grain(source, src, take, rate)
                w = window[:take]
                if out_channels == 2:
                    pan = float(rng.uniform(-width_amt, width_amt)) if width_amt > 0 else 0.0
                    angle = (pan + 1.0) * (np.pi / 4.0)
                    gains = (np.cos(angle), np.sin(angle))
                    mono = np.mean(chunk, axis=0) if chunk.shape[0] > 1 else chunk[0]
                    for ch, g in enumerate(gains):
                        wet[ch, place : place + take] += mono * w * g
                else:
                    wet[:, place : place + take] += chunk[:out_channels] * w
                weight[place : place + take] += w

        safe_weight = np.maximum(weight, 1e-6)
        wet /= safe_weight
        env = np.linspace(wet_start, wet_end, n_samples, dtype=np.float64)
        if dry.shape[0] != out_channels:
            if dry.shape[0] == 1 and out_channels == 2:
                dry = np.vstack([dry, dry])
            else:
                dry = dry[:out_channels]
        out = dry * (1.0 - env) + wet * env
        peak = float(np.max(np.abs(out))) if out.size else 0.0
        if peak > 1.0:
            out = out / peak

        layout = "stereo" if out_channels == 2 else audio.channel_layout
        buffer = AudioBuffer.from_planar(
            out,
            sr,
            source_node_type="Granulate",
            channel_layout=layout,
        )
        inherit_format_meta(buffer, audio)
        if out_channels == 2:
            buffer.channel_layout = "stereo"
        self._ctx.cache.write_audio(buffer, out)
        return (buffer,)

