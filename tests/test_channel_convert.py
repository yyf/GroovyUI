from __future__ import annotations

import numpy as np
import pytest
from groovy.executor import Executor
from groovy.executor.audio import AudioBuffer
from groovy.executor.engine import JobContext
from groovy.nodes.core import register_all
from groovy.node import NODE_REGISTRY

register_all()


@pytest.fixture
def project_dir(tmp_path):
    return tmp_path


def test_channel_convert_51_to_stereo_downmix(project_dir) -> None:
    sr = 48000
    frames = 256
    fl = np.full(frames, 1.0)
    fr = np.full(frames, 0.0)
    fc = np.full(frames, 1.0)
    lfe = np.full(frames, 0.5)
    bl = np.full(frames, 1.0)
    br = np.full(frames, 0.0)
    pcm = np.vstack([fl, fr, fc, lfe, bl, br])
    source = AudioBuffer.from_planar(pcm, sr, source_node_type="Test", channel_layout="5.1")

    executor = Executor(project_dir)
    executor.cache.write_audio(source, pcm)
    ctx = JobContext(project_dir=project_dir, cache=executor.cache, job_id="test")
    node = NODE_REGISTRY["ChannelConvert"]()
    node.bind_context(ctx)
    out, = node.run(audio=source, layout="stereo")

    _, result_pcm = executor.cache.load_audio(out.id)
    assert result_pcm.shape[0] == 2
    scale = 0.70710678
    expected_l = fl + scale * fc + scale * bl
    expected_r = fr + scale * fc + scale * br
    np.testing.assert_allclose(result_pcm[0], expected_l, rtol=1e-5)
    np.testing.assert_allclose(result_pcm[1], expected_r, rtol=1e-5)
    meta = executor.cache.read_meta(out.id)
    assert meta["channel_layout"] == "stereo"


def test_transcode_writes_flac(project_dir) -> None:
    sr = 48000
    frames = 128
    pcm = np.full((1, frames), 0.25)
    source = AudioBuffer.from_planar(pcm, sr, source_node_type="Test", channel_layout="mono")

    executor = Executor(project_dir)
    executor.cache.write_audio(source, pcm)
    ctx = JobContext(project_dir=project_dir, cache=executor.cache, job_id="transcode-test")
    node = NODE_REGISTRY["Transcode"]()
    node.bind_context(ctx)
    out, = node.run(audio=source, format="flac", path="assets/exports/downmix.flac")

    dest = project_dir / "assets" / "exports" / "downmix.flac"
    assert dest.exists()
    assert out.channel_layout == "mono"
