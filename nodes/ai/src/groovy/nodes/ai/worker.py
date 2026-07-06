from __future__ import annotations

import json
import sys
from pathlib import Path

from groovy.executor.cache import CacheStore
from groovy.nodes.ai.inference import (
    require_model,
    run_denoise,
    run_separate_stems,
    run_tts,
    run_voice_convert,
    run_whisper_stt,
)

HANDLERS = {
    "Denoise": run_denoise,
    "SeparateStems": run_separate_stems,
    "WhisperSTT": run_whisper_stt,
    "TTS": run_tts,
    "VoiceConvert": run_voice_convert,
}


def main() -> None:
    payload = json.loads(sys.stdin.read())
    node_type = payload["node_type"]
    project_dir = Path(payload["project_dir"])
    kwargs = payload["kwargs"]
    cache = CacheStore(project_dir)

    handler = HANDLERS.get(node_type)
    if handler is None:
        raise RuntimeError(f"Unknown AI node type: {node_type}")

    model_id = kwargs.get("model")
    if model_id:
        require_model(project_dir, str(model_id))

    outputs = handler(cache, kwargs)
    sys.stdout.write(json.dumps({"outputs": outputs}))


if __name__ == "__main__":
    main()
