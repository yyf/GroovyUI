from __future__ import annotations

import numpy as np
from groovy.executor.oba import (
    ObjectScene,
    apply_object_animation,
    interpolate_object_params,
    merge_object_scenes,
    object_scene_from_audio,
    pan_mono_to_51,
    render_object_scene,
)
from groovy.executor.audio import AudioBuffer


def test_pan_mono_to_51_has_six_channels() -> None:
    signal = np.ones(128)
    bed = pan_mono_to_51(signal, 45.0)
    assert bed.shape == (6, 128)
    assert np.max(np.abs(bed)) > 0


def test_merge_object_scenes_combines_objects() -> None:
    scene_a = ObjectScene.create(sample_rate=48000, frame_count=100, source_node_type="A")
    scene_b = ObjectScene.create(sample_rate=48000, frame_count=100, source_node_type="B")
    scene_a.objects.append({"id": "a1", "audio_id": "x"})
    scene_b.objects.append({"id": "b1", "audio_id": "y"})
    merged = merge_object_scenes(scene_a, scene_b)
    assert len(merged.objects) == 2
    assert merged.source_node_type == "ObjectMerge"


def test_object_animate_adds_dynamics() -> None:
    scene = ObjectScene.create(sample_rate=48000, frame_count=200, source_node_type="Test")
    scene.objects.append({"id": "obj1", "position": {"azimuth": 0.0, "elevation": 0.0}})
    animated = apply_object_animation(
        scene,
        azimuth_start=-30.0,
        azimuth_end=30.0,
        gain_start_db=0.0,
        gain_end_db=-6.0,
    )
    assert len(animated.dynamics) == 2
    azimuth, gain = interpolate_object_params(
        animated,
        "obj1",
        100,
        default_azimuth=0.0,
        default_gain_db=0.0,
    )
    assert -30.0 <= azimuth <= 30.0
    assert gain <= 0.0


def test_render_object_scene_51(tmp_path) -> None:
    from groovy.executor import Executor

    executor = Executor(tmp_path)
    sr = 48000
    pcm = np.full((1, 256), 0.2)
    source = AudioBuffer.from_planar(pcm, sr, source_node_type="Test", channel_layout="mono")
    executor.cache.write_audio(source, pcm)
    scene = object_scene_from_audio(source, executor.cache, azimuth=60.0)
    rendered = render_object_scene(scene, executor.cache, output_layout="5.1")
    assert rendered.shape == (6, 256)
