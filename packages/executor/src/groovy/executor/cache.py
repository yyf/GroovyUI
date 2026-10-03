from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from groovy.executor.ambisonics import AmbisonicBuffer
from groovy.executor.audio import AudioBuffer, StemsBuffer
from groovy.executor.authenticity import AuthenticityReport
from groovy.executor.control import AutomationBuffer
from groovy.executor.midi import MidiBuffer
from groovy.executor.oba import ObjectScene
from groovy.executor.osc_live import OscBuffer
from groovy.executor.trajectory import TrajectoryBuffer
from groovy.executor.video import VideoClip


class CacheStore:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir.resolve()
        self.cache_dir = self.project_dir / ".groovy" / "cache"
        self.runs_dir = self.project_dir / ".groovy" / "runs"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def resolve_project_path(self, relative: str) -> Path:
        candidate = (self.project_dir / relative).resolve()
        if not str(candidate).startswith(str(self.project_dir)):
            raise ValueError(f"Path escapes project directory: {relative}")
        return candidate

    def write_audio(self, buffer: AudioBuffer, pcm: np.ndarray) -> AudioBuffer:
        f64_path = self.cache_dir / f"{buffer.id}.f64"
        pcm = np.asarray(pcm, dtype=np.float64)
        if pcm.ndim == 1:
            pcm = pcm.reshape(1, -1)
        pcm.tofile(f64_path)

        meta_path = self.cache_dir / f"{buffer.id}.meta.json"
        buffer.path = str(f64_path)
        meta_path.write_text(json.dumps(buffer.to_meta(), indent=2))

        return buffer

    def write_stems(self, stems: StemsBuffer, stem_pcm: dict[str, np.ndarray]) -> StemsBuffer:
        for name, buffer in stems.stems.items():
            self.write_audio(buffer, stem_pcm[name])
        meta_path = self.cache_dir / f"{stems.id}.stems.meta.json"
        meta_path.write_text(json.dumps(stems.to_meta(), indent=2))
        return stems

    def load_stems(self, stems_id: str) -> StemsBuffer:
        meta_path = self.cache_dir / f"{stems_id}.stems.meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Stems cache not found: {stems_id}")
        meta = json.loads(meta_path.read_text())
        stem_buffers: dict[str, AudioBuffer] = {}
        for name, ref in meta["stems"].items():
            buffer, _ = self.load_audio(ref["id"])
            stem_buffers[name] = buffer
        return StemsBuffer(
            id=meta["id"],
            sample_rate=meta["sample_rate"],
            channels=meta["channels"],
            frame_count=meta["frame_count"],
            stems=stem_buffers,
        )

    def read_meta(self, cache_id: str) -> dict:
        meta_path = self.cache_dir / f"{cache_id}.meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Cache entry not found: {cache_id}")
        return json.loads(meta_path.read_text())

    def load_audio(self, cache_id: str) -> tuple[AudioBuffer, np.ndarray]:
        meta = self.read_meta(cache_id)
        buffer = AudioBuffer(
            id=meta["id"],
            sample_rate=meta["sample_rate"],
            channels=meta["channels"],
            frame_count=meta["frame_count"],
            channel_layout=meta.get("channel_layout", "mono"),
            channel_map=meta.get("channel_map", []),
            layout_order=meta.get("layout_order"),
            encoding_scheme=meta.get("encoding_scheme"),
            file_format=meta.get("file_format"),
            file_subtype=meta.get("file_subtype"),
            spatial_meta=meta.get("spatial_meta", {}),
            path=str(self.cache_dir / f"{cache_id}.f64"),
            source_node=meta.get("source_node"),
            source_node_type=meta.get("source_node_type"),
            content_hash=meta.get("content_hash"),
        )
        pcm = buffer.data
        return buffer, pcm

    def write_provenance(self, cache_id: str, record: dict) -> None:
        path = self.cache_dir / f"{cache_id}.provenance.json"
        path.write_text(json.dumps(record, indent=2))

    def read_provenance(self, cache_id: str) -> dict | None:
        path = self.cache_dir / f"{cache_id}.provenance.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def export_provenance_sidecar(
        self,
        cache_id: str,
        output_path: Path,
        *,
        content_credentials: dict[str, Any] | None = None,
    ) -> Path:
        record = self.read_provenance(cache_id)
        if not record:
            raise FileNotFoundError(f"No provenance for cache entry: {cache_id}")
        from groovy.executor.audio_meta import probe_audio_file
        from groovy.executor.provenance import (
            apply_record_integrity,
            build_lineage_graph,
            disclosure_summary,
        )

        digest = hashlib.sha256()
        with output_path.open("rb") as audio_file:
            for chunk in iter(lambda: audio_file.read(1024 * 1024), b""):
                digest.update(chunk)
        probe = probe_audio_file(output_path)
        extension = output_path.suffix.lower()
        media_types = {
            ".aif": "audio/aiff",
            ".aiff": "audio/aiff",
            ".flac": "audio/flac",
            ".wav": "audio/wav",
        }
        sample_rate = int(probe["sample_rate"])
        duration_seconds = float(probe["duration_seconds"])
        exported_record = dict(record)
        exported_record["artifact"] = {
            "filename": output_path.name,
            "media_type": media_types.get(extension, "application/octet-stream"),
            "format": probe["file_format"],
            "subtype": probe["file_subtype"],
            "sample_rate": sample_rate,
            "channels": int(probe["channels"]),
            "channel_layout": probe["channel_layout"],
            "channel_map": probe["channel_map"],
            "frame_count": int(round(duration_seconds * sample_rate)),
            "duration_seconds": duration_seconds,
            "file_size_bytes": output_path.stat().st_size,
            "file_hash": f"sha256:{digest.hexdigest()}",
            "source_audio_content_hash": record.get("content_hash"),
        }
        lineage = build_lineage_graph(self, cache_id)
        exported_record["lineage"] = lineage
        exported_record["disclosure"] = {
            "summary": disclosure_summary(lineage["nodes"]),
            "not_legal_advice": True,
        }
        license_rows: dict[str, dict[str, Any]] = {}
        for lineage_node in lineage["nodes"]:
            for model in lineage_node.get("models") or []:
                model_id = str(model.get("registry_id") or "")
                if model_id and model.get("license"):
                    license_rows[model_id] = {
                        "registry_id": model_id,
                        "name": model.get("name"),
                        "license": model["license"],
                    }
        exported_record["compliance"] = {
            "models": list(license_rows.values()),
            "review_required": True,
            "disclaimer": "Verify model and source-asset licenses before distribution.",
        }
        exported_record["content_credentials"] = content_credentials or {
            "status": "off",
            "mode": "off",
            "verified": False,
        }
        exported_record = apply_record_integrity(exported_record)
        sidecar = output_path.with_name(f"{output_path.stem}.provenance.json")
        temporary = sidecar.with_suffix(f"{sidecar.suffix}.tmp")
        temporary.write_text(json.dumps(exported_record, indent=2))
        temporary.replace(sidecar)
        return sidecar

    def write_midi(self, midi: MidiBuffer, midi_bytes: bytes | None = None) -> MidiBuffer:
        mid_path = self.cache_dir / f"{midi.id}.mid"
        if midi_bytes is not None:
            mid_path.write_bytes(midi_bytes)
        midi.path = str(mid_path)
        meta_path = self.cache_dir / f"{midi.id}.midi.meta.json"
        meta_path.write_text(json.dumps(midi.to_meta(), indent=2))
        return midi

    def load_midi(self, midi_id: str) -> MidiBuffer:
        meta_path = self.cache_dir / f"{midi_id}.midi.meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"MIDI cache not found: {midi_id}")
        meta = json.loads(meta_path.read_text())
        return MidiBuffer(
            id=meta["id"],
            sample_rate=meta["sample_rate"],
            frame_count=meta["frame_count"],
            ppq=meta.get("ppq", 480),
            midi_kind=meta.get("midi_kind", "transcript"),
            format=meta.get("format", "smf"),
            tracks=meta.get("tracks", 1),
            path=meta.get("path"),
            tempo_bpm=meta.get("tempo_map", [{"bpm": 120}])[0].get("bpm", 120),
            source_node=meta.get("source_node"),
            source_node_type=meta.get("source_node_type"),
        )

    def midi_roll(self, midi_id: str) -> dict:
        midi = self.load_midi(midi_id)
        mid_path = self.cache_dir / f"{midi_id}.mid"
        if not mid_path.exists():
            raise FileNotFoundError(f"MIDI file not found: {midi_id}")
        duration = midi.frame_count / max(midi.sample_rate, 1)
        notes: list[dict] = []
        try:
            from pretty_midi import PrettyMIDI

            pm = PrettyMIDI(str(mid_path))
            duration = max(duration, float(pm.get_end_time()))
            for instrument in pm.instruments:
                for note in instrument.notes:
                    notes.append(
                        {
                            "start": round(note.start, 4),
                            "end": round(note.end, 4),
                            "pitch": int(note.pitch),
                            "velocity": int(note.velocity),
                            "drum": bool(instrument.is_drum),
                        }
                    )
        except ImportError:
            pass
        pitches = [note["pitch"] for note in notes]
        min_pitch = max(0, (min(pitches) if pitches else 60) - 2)
        max_pitch = min(127, (max(pitches) if pitches else 72) + 2)
        if min_pitch >= max_pitch:
            max_pitch = min(127, min_pitch + 12)
        return {
            "midi_id": midi_id,
            "duration": duration,
            "notes": notes,
            "min_pitch": min_pitch,
            "max_pitch": max_pitch,
        }

    def midi_preview_wav_bytes(self, midi_id: str, *, sample_rate: int = 48_000) -> bytes:
        """Offline audition: synthesize cached SMF to WAV (not realtime / not a DAW feature)."""
        import io

        import soundfile as sf

        midi = self.load_midi(midi_id)
        mid_path = self.cache_dir / f"{midi_id}.mid"
        if not mid_path.exists():
            raise FileNotFoundError(f"MIDI file not found: {midi_id}")

        duration = max(0.25, midi.frame_count / max(midi.sample_rate, 1))
        pcm: np.ndarray | None = None
        try:
            from pretty_midi import PrettyMIDI

            pm = PrettyMIDI(str(mid_path))
            duration = max(duration, float(pm.get_end_time()))
            audio = pm.synthesize(fs=sample_rate)
            if audio.size:
                target_frames = int(round(duration * sample_rate))
                if audio.size < target_frames:
                    padded = np.zeros(target_frames, dtype=np.float64)
                    padded[: audio.size] = audio
                    audio = padded
                elif audio.size > target_frames:
                    audio = audio[:target_frames]
                pcm = np.asarray(audio, dtype=np.float64).reshape(1, -1)
        except ImportError:
            pass

        if pcm is None:
            pcm = np.zeros((1, int(duration * sample_rate)), dtype=np.float64)

        buf = io.BytesIO()
        sf.write(buf, pcm.reshape(-1), sample_rate, format="WAV", subtype="FLOAT")
        return buf.getvalue()

    def is_midi_cache(self, cache_id: str) -> bool:
        return (self.cache_dir / f"{cache_id}.midi.meta.json").exists()

    def write_authenticity(self, report: AuthenticityReport) -> AuthenticityReport:
        meta_path = self.cache_dir / f"{report.id}.authenticity.json"
        meta_path.write_text(json.dumps(report.to_meta(), indent=2))
        return report

    def load_authenticity(self, report_id: str) -> AuthenticityReport:
        meta_path = self.cache_dir / f"{report_id}.authenticity.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Authenticity report not found: {report_id}")
        meta = json.loads(meta_path.read_text())
        record = {k: v for k, v in meta.items() if k not in {"id", "type"}}
        return AuthenticityReport(id=meta["id"], record=record)

    def write_sample_check(self, report: Any) -> Any:
        from groovy.executor.sample_integrity import SampleCheckReport

        if not isinstance(report, SampleCheckReport):
            raise TypeError("write_sample_check expects SampleCheckReport")
        meta_path = self.cache_dir / f"{report.id}.sample_check.json"
        meta_path.write_text(json.dumps(report.to_meta(), indent=2))
        return report

    def load_sample_check(self, report_id: str) -> Any:
        from groovy.executor.sample_integrity import SampleCheckReport

        meta_path = self.cache_dir / f"{report_id}.sample_check.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Sample check report not found: {report_id}")
        meta = json.loads(meta_path.read_text())
        record = {k: v for k, v in meta.items() if k not in {"id", "type"}}
        return SampleCheckReport(id=meta["id"], record=record)

    def write_automation(self, curve: AutomationBuffer) -> AutomationBuffer:
        f64_path = self.cache_dir / f"{curve.id}.automation.f64"
        curve.values.astype(np.float64).tofile(f64_path)
        curve.path = str(f64_path)
        meta_path = self.cache_dir / f"{curve.id}.automation.meta.json"
        meta_path.write_text(json.dumps(curve.to_meta(), indent=2))
        return curve

    def load_automation(self, automation_id: str) -> AutomationBuffer:
        meta_path = self.cache_dir / f"{automation_id}.automation.meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Automation cache not found: {automation_id}")
        meta = json.loads(meta_path.read_text())
        values = np.fromfile(self.cache_dir / f"{automation_id}.automation.f64", dtype=np.float64)
        return AutomationBuffer(
            id=meta["id"],
            sample_rate=meta["sample_rate"],
            frame_count=meta["frame_count"],
            values=values,
            path=str(self.cache_dir / f"{automation_id}.automation.f64"),
            source_node_type=meta.get("source_node_type"),
        )

    def read_node_cache(self, workflow_id: str, node_id: str) -> dict[str, Any] | None:
        path = self.cache_dir / "node_state" / workflow_id / f"{node_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def write_node_cache(
        self, workflow_id: str, node_id: str, *, signature: str, output_meta: dict[str, Any]
    ) -> None:
        state_dir = self.cache_dir / "node_state" / workflow_id
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / f"{node_id}.json"
        path.write_text(json.dumps({"signature": signature, "output": output_meta}, indent=2))

    def preview_wav_bytes(self, cache_id: str) -> bytes:
        import io

        import soundfile as sf

        _, pcm = self.load_audio(cache_id)
        # Planar (channels, frames) → soundfile expects (frames, channels).
        # Do not flatten stereo to mono: that doubles duration and breaks seek UI.
        frames = pcm if pcm.ndim == 1 else pcm.T
        buf = io.BytesIO()
        sf.write(
            buf,
            frames,
            self.read_meta(cache_id)["sample_rate"],
            format="WAV",
            subtype="PCM_16",
        )
        return buf.getvalue()

    def waveform_peaks(self, cache_id: str, width: int = 512) -> dict:
        _, pcm = self.load_audio(cache_id)
        mono = pcm.mean(axis=0)
        if len(mono) == 0:
            return {"peaks": [], "duration": 0.0}
        chunk = max(1, len(mono) // width)
        peaks = [float(np.max(np.abs(mono[i : i + chunk]))) for i in range(0, len(mono), chunk)]
        peaks = peaks[:width]
        sr = self.read_meta(cache_id)["sample_rate"]
        return {"peaks": peaks, "duration": len(mono) / sr}

    def meter_envelopes(self, cache_id: str, width: int = 256) -> dict:
        """Per-channel peak envelopes for Inspector meter scrubbing (not live DSP).

        Supports AUDIO and AMBISONICS cache ids; labels follow inlet metadata
        (FOA W/Y/Z/X, HOA ACN, stereo L/R, …).
        """
        from groovy.executor.meter import channel_labels_for_layout, resolve_meter_layout

        meta = self.read_meta(cache_id)
        if meta.get("type") == "AMBISONICS":
            _, pcm = self.load_ambisonics(cache_id)
            layout_order = meta.get("layout_order")
            channel_layout = meta.get("channel_layout") or "ambisonics"
            spatial_meta = dict(meta.get("spatial_meta") or {})
            spatial_meta.setdefault("channel_ordering", meta.get("channel_ordering"))
            spatial_meta.setdefault("encoding_scheme", meta.get("encoding_scheme"))
        else:
            _, pcm = self.load_audio(cache_id)
            layout_order = meta.get("layout_order")
            channel_layout = meta.get("channel_layout")
            spatial_meta = dict(meta.get("spatial_meta") or {})
        if pcm.ndim == 1:
            pcm = pcm.reshape(1, -1)
        channels, frames = pcm.shape
        width = max(16, min(int(width), 2048))
        if frames <= 0 or channels <= 0:
            return {
                "channels": [],
                "labels": [],
                "duration": 0.0,
                "width": 0,
                "sample_rate": int(meta.get("sample_rate") or 48000),
                "layout": "auto",
            }
        chunk = max(1, frames // width)
        envelopes: list[list[float]] = []
        for ch in range(channels):
            peaks = [
                float(np.max(np.abs(pcm[ch, i : i + chunk])))
                for i in range(0, frames, chunk)
            ]
            envelopes.append(peaks[:width])
        effective = resolve_meter_layout(
            layout_widget="auto",
            channel_count=channels,
            channel_layout=channel_layout,
            spatial_meta=spatial_meta,
            layout_order=int(layout_order) if layout_order is not None else None,
        )
        labels = channel_labels_for_layout(effective, channels)
        sr = int(meta.get("sample_rate") or 48000)
        return {
            "channels": envelopes,
            "labels": labels,
            "duration": frames / max(sr, 1),
            "width": len(envelopes[0]) if envelopes else 0,
            "sample_rate": sr,
            "layout": effective,
        }

    def spectrogram_tiles(
        self,
        cache_id: str,
        *,
        width: int = 512,
        height: int = 48,
        floor_db: float = -72.0,
    ) -> dict:
        """Log-magnitude STFT tiles for minimal transport spectrogram (dBFS relative to clip peak)."""
        import scipy.signal
        from scipy.ndimage import zoom

        width = max(16, min(width, 2048))
        height = max(16, min(height, 128))

        mono: np.ndarray
        sr: int
        if self.is_midi_cache(cache_id):
            import io

            import soundfile as sf

            wav_bytes = self.midi_preview_wav_bytes(cache_id)
            samples, sr = sf.read(io.BytesIO(wav_bytes), dtype="float64", always_2d=True)
            mono = samples.mean(axis=1).astype(np.float64) if samples.ndim == 2 else samples.astype(np.float64)
        else:
            meta = self.read_meta(cache_id)
            _, pcm = self.load_audio(cache_id)
            mono = pcm.mean(axis=0).astype(np.float64)
            sr = int(meta["sample_rate"])

        duration = len(mono) / max(sr, 1)
        if len(mono) == 0:
            return {
                "width": 0,
                "height": 0,
                "values": [],
                "duration": 0.0,
                "min_db": floor_db,
                "max_db": 0.0,
                "sample_rate": sr,
                "max_freq_hz": sr / 2,
            }

        nperseg = int(min(2048, max(128, 2 ** int(np.ceil(np.log2(len(mono) / max(width, 1)))))))
        nperseg = min(nperseg, len(mono))
        if nperseg < 32:
            nperseg = max(8, len(mono))
        noverlap = max(0, min(nperseg // 2, nperseg - 1))
        _f, t_stft, zxx = scipy.signal.stft(
            mono,
            fs=sr,
            nperseg=nperseg,
            noverlap=noverlap,
            window="hann",
            boundary="zeros",
            padded=True,
        )
        magnitude = np.abs(zxx)
        peak = float(np.max(magnitude))
        if peak < 1e-12:
            peak = 1e-12
        db = 20.0 * np.log10(np.maximum(magnitude, 1e-12) / peak)
        db = np.clip(db, floor_db, 0.0)

        # Resample STFT onto the same uniform time grid as waveform peaks (0 … duration).
        t_uniform = (np.arange(width, dtype=np.float64) + 0.5) / width * duration
        db_time = np.vstack([np.interp(t_uniform, t_stft, row) for row in db]).astype(np.float64)

        zoom_y = height / max(db_time.shape[0], 1)
        resized = zoom(db_time, (zoom_y, 1), order=1)
        resized = np.clip(resized[:height, :width], floor_db, 0.0)

        return {
            "width": width,
            "height": height,
            "values": resized.reshape(-1).astype(np.float64).tolist(),
            "duration": duration,
            "min_db": floor_db,
            "max_db": 0.0,
            "sample_rate": sr,
            "max_freq_hz": sr / 2,
        }

    def write_trajectory(self, trajectory: TrajectoryBuffer) -> TrajectoryBuffer:
        points_path = self.cache_dir / f"{trajectory.id}.trajectory.json"
        payload = {
            "points": trajectory.points,
            "source": trajectory.source,
            "object_id": trajectory.object_id,
            "spatial_meta": trajectory.spatial_meta,
        }
        points_path.write_text(json.dumps(payload, indent=2))
        trajectory.path = str(points_path)
        meta_path = self.cache_dir / f"{trajectory.id}.meta.json"
        meta_path.write_text(json.dumps(trajectory.to_meta(), indent=2))
        return trajectory

    def load_trajectory(self, trajectory_id: str) -> TrajectoryBuffer:
        meta_path = self.cache_dir / f"{trajectory_id}.meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Trajectory cache not found: {trajectory_id}")
        meta = json.loads(meta_path.read_text())
        if meta.get("type") != "TRAJECTORY":
            raise ValueError(f"Cache entry is not a trajectory: {trajectory_id}")
        points_path = self.cache_dir / f"{trajectory_id}.trajectory.json"
        if not points_path.exists():
            raise FileNotFoundError(f"Trajectory points not found: {trajectory_id}")
        payload = json.loads(points_path.read_text())
        return TrajectoryBuffer(
            id=meta["id"],
            sample_rate=int(meta["sample_rate"]),
            frame_count=int(meta["frame_count"]),
            points=list(payload.get("points") or []),
            source=payload.get("source", meta.get("source", "authored")),
            object_id=str(payload.get("object_id", meta.get("object_id", "obj_0"))),
            path=str(points_path),
            source_node_type=meta.get("source_node_type"),
            spatial_meta=dict(payload.get("spatial_meta") or meta.get("spatial_meta") or {}),
        )

    def write_ambisonics(self, buffer: AmbisonicBuffer, pcm: np.ndarray) -> AmbisonicBuffer:
        f64_path = self.cache_dir / f"{buffer.id}.ambi.f64"
        pcm = np.asarray(pcm, dtype=np.float64)
        if pcm.ndim == 1:
            pcm = pcm.reshape(1, -1)
        pcm.tofile(f64_path)
        buffer.path = str(f64_path)
        meta_path = self.cache_dir / f"{buffer.id}.meta.json"
        meta_path.write_text(json.dumps(buffer.to_meta(), indent=2))
        return buffer

    def load_ambisonics(self, ambisonics_id: str) -> tuple[AmbisonicBuffer, np.ndarray]:
        meta = self.read_meta(ambisonics_id)
        if meta.get("type") != "AMBISONICS":
            raise ValueError(f"Cache entry is not ambisonics: {ambisonics_id}")
        buffer = AmbisonicBuffer(
            id=meta["id"],
            sample_rate=meta["sample_rate"],
            frame_count=meta["frame_count"],
            layout_order=meta.get("layout_order", 1),
            channels=meta.get("channels", 4),
            path=str(self.cache_dir / f"{ambisonics_id}.ambi.f64"),
            source_node_type=meta.get("source_node_type"),
            spatial_meta=meta.get("spatial_meta", {}),
        )
        pcm = np.fromfile(buffer.path, dtype=np.float64).reshape(buffer.channels, buffer.frame_count)
        return buffer, pcm

    def write_object_scene(self, scene: ObjectScene) -> ObjectScene:
        meta_path = self.cache_dir / f"{scene.id}.oba.json"
        meta_path.write_text(json.dumps(scene.to_meta(), indent=2))
        return scene

    def load_object_scene(self, scene_id: str) -> ObjectScene:
        meta_path = self.cache_dir / f"{scene_id}.oba.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Object scene not found: {scene_id}")
        meta = json.loads(meta_path.read_text())
        return ObjectScene(
            id=meta["id"],
            sample_rate=meta["sample_rate"],
            frame_count=meta["frame_count"],
            beds=meta.get("beds", []),
            objects=meta.get("objects", []),
            dynamics=meta.get("dynamics", []),
            adm_path=meta.get("adm_path"),
            source_node_type=meta.get("source_node_type"),
        )

    def write_osc(self, buffer: OscBuffer) -> OscBuffer:
        meta_path = self.cache_dir / f"{buffer.id}.osc.json"
        meta_path.write_text(json.dumps({**buffer.to_meta(), "events": buffer.events}, indent=2))
        return buffer

    def load_osc(self, osc_id: str) -> OscBuffer:
        meta_path = self.cache_dir / f"{osc_id}.osc.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"OSC cache not found: {osc_id}")
        meta = json.loads(meta_path.read_text())
        return OscBuffer(
            id=meta["id"],
            sample_rate=meta["sample_rate"],
            frame_count=meta["frame_count"],
            events=meta.get("events", []),
            source_node_type=meta.get("source_node_type"),
        )

    def write_video(self, clip: VideoClip) -> VideoClip:
        meta_path = self.cache_dir / f"{clip.id}.video.json"
        meta_path.write_text(
            json.dumps(
                {
                    "id": clip.id,
                    "path": clip.path,
                    "source_node_type": clip.source_node_type,
                    "source_video_path": clip.source_video_path,
                    "width": clip.width,
                    "height": clip.height,
                },
                indent=2,
            )
        )
        return clip

    def load_video(self, video_id: str) -> VideoClip:
        meta_path = self.cache_dir / f"{video_id}.video.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Video cache not found: {video_id}")
        meta = json.loads(meta_path.read_text())
        return VideoClip(
            id=meta["id"],
            path=meta["path"],
            source_node_type=meta.get("source_node_type"),
            source_video_path=meta.get("source_video_path"),
            width=meta.get("width"),
            height=meta.get("height"),
        )

    def create_run_dir(self, job_id: str) -> Path:
        run_dir = self.runs_dir / job_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def write_manifest(self, job_id: str, manifest: dict) -> Path:
        run_dir = self.create_run_dir(job_id)
        path = run_dir / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2))
        return path
