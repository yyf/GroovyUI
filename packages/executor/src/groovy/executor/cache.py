from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from groovy.executor.ambisonics import AmbisonicBuffer
from groovy.executor.audio import AudioBuffer, StemsBuffer
from groovy.executor.authenticity import AuthenticityReport
from groovy.executor.control import AutomationBuffer
from groovy.executor.midi import MidiBuffer
from groovy.executor.oba import ObjectScene
from groovy.executor.osc_live import OscBuffer


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

    def export_provenance_sidecar(self, cache_id: str, output_path: Path) -> Path:
        record = self.read_provenance(cache_id)
        if not record:
            raise FileNotFoundError(f"No provenance for cache entry: {cache_id}")
        sidecar = output_path.with_name(f"{output_path.stem}.provenance.json")
        sidecar.write_text(json.dumps(record, indent=2))
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
        interleaved = pcm.T.reshape(-1)
        buf = io.BytesIO()
        sf.write(
            buf, interleaved, self.read_meta(cache_id)["sample_rate"], format="WAV", subtype="FLOAT"
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

    def create_run_dir(self, job_id: str) -> Path:
        run_dir = self.runs_dir / job_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def write_manifest(self, job_id: str, manifest: dict) -> Path:
        run_dir = self.create_run_dir(job_id)
        path = run_dir / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2))
        return path
