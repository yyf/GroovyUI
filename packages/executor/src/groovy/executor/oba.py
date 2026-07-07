from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

from groovy.executor.audio import AudioBuffer


@dataclass
class ObjectScene:
    """Runtime object-based audio scene (beds + spatial objects)."""

    id: str
    sample_rate: int
    frame_count: int
    beds: list[dict[str, Any]] = field(default_factory=list)
    objects: list[dict[str, Any]] = field(default_factory=list)
    dynamics: list[dict[str, Any]] = field(default_factory=list)
    adm_path: str | None = None
    source_node_type: str | None = None

    def to_meta(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "OBA",
            "format": "object_scene",
            "sample_rate": self.sample_rate,
            "frame_count": self.frame_count,
            "beds": self.beds,
            "objects": self.objects,
            "dynamics": self.dynamics,
            "adm_path": self.adm_path,
            "source_node_type": self.source_node_type,
            "encoding_scheme": "GroovyUI ObjectScene",
            "created_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def create(
        cls,
        *,
        sample_rate: int,
        frame_count: int,
        source_node_type: str = "ObjectFromAudio",
    ) -> ObjectScene:
        return cls(
            id=str(uuid.uuid4()),
            sample_rate=sample_rate,
            frame_count=frame_count,
            source_node_type=source_node_type,
        )


def pan_mono_to_stereo(signal: np.ndarray, azimuth_deg: float, gain_db: float = 0.0) -> np.ndarray:
    """Equal-power pan mono signal to stereo by azimuth (degrees, 0 = front)."""
    mono = signal.reshape(-1)
    az = math.radians(azimuth_deg)
    angle = (az + math.pi / 2) / 2
    gain = 10 ** (gain_db / 20.0)
    left = math.cos(angle) * gain * mono
    right = math.sin(angle) * gain * mono
    return np.vstack([left, right])


def pan_mono_to_51(signal: np.ndarray, azimuth_deg: float, gain_db: float = 0.0) -> np.ndarray:
    """Pan mono signal to 5.1 (FL, FR, FC, LFE, BL, BR) with simple azimuth law."""
    mono = signal.reshape(-1)
    gain = 10 ** (gain_db / 20.0) * mono
    az = math.radians(azimuth_deg)
    front = max(0.0, math.cos(az))
    back = max(0.0, -math.cos(az))
    left = max(0.0, math.sin(az))
    right = max(0.0, -math.sin(az))
    norm = front + back + left + right
    if norm < 1e-9:
        front = 1.0
        norm = 1.0
    front /= norm
    back /= norm
    left /= norm
    right /= norm
    fl = gain * (front * 0.5 + left * 0.5)
    fr = gain * (front * 0.5 + right * 0.5)
    fc = gain * (front * 0.35)
    bl = gain * (back * 0.5 + left * 0.5)
    br = gain * (back * 0.5 + right * 0.5)
    lfe = np.zeros_like(mono)
    return np.vstack([fl, fr, fc, lfe, bl, br])


def _sorted_dynamics_for_object(
    scene: ObjectScene, object_id: str
) -> list[dict[str, Any]]:
    frames = [
        dyn
        for dyn in scene.dynamics
        if dyn.get("object_id") == object_id
    ]
    return sorted(frames, key=lambda item: int(item.get("frame", 0)))


def interpolate_object_params(
    scene: ObjectScene,
    object_id: str,
    frame: int,
    *,
    default_azimuth: float,
    default_gain_db: float,
) -> tuple[float, float]:
    """Linear interpolation of azimuth and gain_db from scene dynamics keyframes."""
    keyframes = _sorted_dynamics_for_object(scene, object_id)
    if not keyframes:
        return default_azimuth, default_gain_db
    if frame <= int(keyframes[0].get("frame", 0)):
        first = keyframes[0]
        pos = first.get("position") or {}
        return float(pos.get("azimuth", default_azimuth)), float(first.get("gain_db", default_gain_db))
    for index in range(len(keyframes) - 1):
        left = keyframes[index]
        right = keyframes[index + 1]
        left_frame = int(left.get("frame", 0))
        right_frame = int(right.get("frame", left_frame))
        if frame < left_frame or frame > right_frame:
            continue
        if right_frame <= left_frame:
            pos = right.get("position") or {}
            return float(pos.get("azimuth", default_azimuth)), float(right.get("gain_db", default_gain_db))
        alpha = (frame - left_frame) / (right_frame - left_frame)
        left_pos = left.get("position") or {}
        right_pos = right.get("position") or {}
        azimuth = float(left_pos.get("azimuth", default_azimuth)) * (1 - alpha) + float(
            right_pos.get("azimuth", default_azimuth)
        ) * alpha
        gain_db = float(left.get("gain_db", default_gain_db)) * (1 - alpha) + float(
            right.get("gain_db", default_gain_db)
        ) * alpha
        return azimuth, gain_db
    last = keyframes[-1]
    pos = last.get("position") or {}
    return float(pos.get("azimuth", default_azimuth)), float(last.get("gain_db", default_gain_db))


def merge_object_scenes(
    scene_a: ObjectScene,
    scene_b: ObjectScene,
    *,
    source_node_type: str = "ObjectMerge",
) -> ObjectScene:
    """Merge beds and objects from two scenes into one."""
    if scene_a.sample_rate != scene_b.sample_rate:
        raise ValueError("ObjectMerge requires matching sample rates")
    frame_count = min(scene_a.frame_count, scene_b.frame_count)
    merged = ObjectScene.create(
        sample_rate=scene_a.sample_rate,
        frame_count=frame_count,
        source_node_type=source_node_type,
    )
    merged.beds = [*scene_a.beds, *scene_b.beds]
    merged.objects = [*scene_a.objects, *scene_b.objects]
    merged.dynamics = [
        dyn
        for dyn in [*scene_a.dynamics, *scene_b.dynamics]
        if int(dyn.get("frame", 0)) < frame_count
    ]
    merged.adm_path = scene_a.adm_path or scene_b.adm_path
    return merged


def apply_object_animation(
    scene: ObjectScene,
    *,
    azimuth_start: float,
    azimuth_end: float,
    gain_start_db: float = 0.0,
    gain_end_db: float = 0.0,
    object_id: str | None = None,
    source_node_type: str = "ObjectAnimate",
) -> ObjectScene:
    """Append start/end dynamics keyframes for one or all objects."""
    animated = ObjectScene(
        id=scene.id,
        sample_rate=scene.sample_rate,
        frame_count=scene.frame_count,
        beds=list(scene.beds),
        objects=list(scene.objects),
        dynamics=list(scene.dynamics),
        adm_path=scene.adm_path,
        source_node_type=source_node_type,
    )
    targets = [
        obj
        for obj in animated.objects
        if object_id is None or obj.get("id") == object_id or obj.get("name") == object_id
    ]
    if not targets:
        raise ValueError("ObjectAnimate found no matching objects")
    end_frame = max(0, scene.frame_count - 1)
    for obj in targets:
        obj_id = str(obj["id"])
        animated.dynamics = [
            dyn for dyn in animated.dynamics if dyn.get("object_id") != obj_id
        ]
        base_pos = obj.get("position") or {}
        elevation = float(base_pos.get("elevation", 0.0))
        animated.dynamics.extend(
            [
                {
                    "frame": 0,
                    "object_id": obj_id,
                    "position": {
                        "azimuth": azimuth_start,
                        "elevation": elevation,
                        "distance": float(base_pos.get("distance", 1.0)),
                    },
                    "gain_db": gain_start_db,
                },
                {
                    "frame": end_frame,
                    "object_id": obj_id,
                    "position": {
                        "azimuth": azimuth_end,
                        "elevation": elevation,
                        "distance": float(base_pos.get("distance", 1.0)),
                    },
                    "gain_db": gain_end_db,
                },
            ]
        )
    return animated


def render_object_scene(
    scene: ObjectScene,
    cache: Any,
    *,
    output_layout: str = "stereo",
) -> np.ndarray:
    """Sum beds + objects into a channel layout, honoring dynamics keyframes."""
    if output_layout not in {"stereo", "5.1"}:
        raise ValueError(f"Unsupported render layout: {output_layout}")
    channels = 2 if output_layout == "stereo" else 6
    mix = np.zeros((channels, scene.frame_count), dtype=np.float64)
    for bed in scene.beds:
        audio_id = bed.get("audio_id")
        if not audio_id:
            continue
        _, pcm = cache.load_audio(audio_id)
        if output_layout == "stereo":
            if pcm.shape[0] == 1:
                pcm = np.vstack([pcm[0], pcm[0]])
            elif pcm.shape[0] > 2:
                pcm = pcm[:2]
        else:
            if pcm.shape[0] == 6:
                pass
            elif pcm.shape[0] == 2:
                fl, fr = pcm
                pcm = np.vstack([fl, fr, (fl + fr) * 0.5, np.zeros_like(fl), fl * 0.3, fr * 0.3])
            elif pcm.shape[0] == 1:
                mono = pcm[0]
                pcm = np.vstack([mono, mono, mono, np.zeros_like(mono), mono, mono])
            else:
                pcm = pcm[:6]
        mix += pcm[:, : scene.frame_count]
    block = 2048
    for obj in scene.objects:
        audio_id = obj.get("audio_id")
        if not audio_id:
            continue
        _, pcm = cache.load_audio(audio_id)
        mono = pcm.mean(axis=0)[: scene.frame_count]
        obj_id = str(obj.get("id", ""))
        base_pos = obj.get("position") or {}
        default_azimuth = float(base_pos.get("azimuth", 0.0))
        default_gain_db = float(obj.get("gain_db", 0.0))
        for start in range(0, scene.frame_count, block):
            end = min(start + block, scene.frame_count)
            mid_frame = start + (end - start) // 2
            azimuth, gain_db = interpolate_object_params(
                scene,
                obj_id,
                mid_frame,
                default_azimuth=default_azimuth,
                default_gain_db=default_gain_db,
            )
            segment = mono[start:end]
            if output_layout == "stereo":
                mix[:, start:end] += pan_mono_to_stereo(segment, azimuth, gain_db)
            else:
                mix[:, start:end] += pan_mono_to_51(segment, azimuth, gain_db)
    return mix


def render_object_scene_stereo(
    scene: ObjectScene,
    cache: Any,
    *,
    output_layout: str = "stereo",
) -> np.ndarray:
    """Backward-compatible alias for object scene rendering."""
    return render_object_scene(scene, cache, output_layout=output_layout)


def object_scene_from_audio(
    audio: AudioBuffer,
    cache: Any,
    *,
    name: str = "Object",
    azimuth: float = 0.0,
    elevation: float = 0.0,
    source_node_type: str = "ObjectFromAudio",
) -> ObjectScene:
    _, pcm = cache.load_audio(audio.id)
    scene = ObjectScene.create(
        sample_rate=audio.sample_rate,
        frame_count=pcm.shape[1],
        source_node_type=source_node_type,
    )
    scene.objects.append(
        {
            "id": f"obj_{audio.id[:8]}",
            "name": name,
            "audio_id": audio.id,
            "channels": pcm.shape[0],
            "position": {"azimuth": azimuth, "elevation": elevation, "distance": 1.0},
            "size": {"width": 0.1, "height": 0.1},
            "gain_db": 0.0,
            "metadata": {"source_node_type": source_node_type},
        }
    )
    return scene
