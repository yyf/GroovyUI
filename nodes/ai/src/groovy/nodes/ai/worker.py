from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from groovy.executor.audio import AudioBuffer
from groovy.executor.cache import CacheStore
from groovy.nodes.ai.inference import denoise_audio


def main() -> None:
    payload = json.loads(sys.stdin.read())
    project_dir = Path(payload["project_dir"])
    kwargs = payload["kwargs"]
    cache = CacheStore(project_dir)

    audio_id = kwargs["audio_id"]
    model_id = str(kwargs.get("model", "deepfilternet-v3"))
    strength = float(kwargs.get("strength", 1.0))

    marker = project_dir / ".groovy" / "models" / model_id / "installed.json"
    if not marker.exists():
        raise RuntimeError(
            f"Model not installed: {model_id}. Install it from Model Browser (Cmd+K) first."
        )

    buffer, pcm = cache.load_audio(audio_id)
    out = denoise_audio(pcm, model_id=model_id, strength=strength, sample_rate=buffer.sample_rate)

    out_buffer = AudioBuffer.from_planar(
        out,
        buffer.sample_rate,
        source_node_type="Denoise",
        channel_layout=buffer.channel_layout,
    )
    cache.write_audio(out_buffer, out)
    result = {"outputs": [{"type": "AUDIO", "cache_id": out_buffer.id}]}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
