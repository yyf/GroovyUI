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


def test_module_inlet_passthrough(project_dir) -> None:
    sr = 48000
    frames = 64
    pcm = np.full((1, frames), 0.2)
    source = AudioBuffer.from_planar(pcm, sr, source_node_type="Test", channel_layout="mono")
    executor = Executor(project_dir)
    executor.cache.write_audio(source, pcm)
    ctx = JobContext(project_dir=project_dir, cache=executor.cache, job_id="mod-io")
    node = NODE_REGISTRY["ModuleInlet"]()
    node.bind_context(ctx)
    out, = node.run(signal=source, name="audio_in")
    assert out.id == source.id
