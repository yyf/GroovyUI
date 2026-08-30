from __future__ import annotations

import json
import sys
from pathlib import Path

from groovy.executor.cache import CacheStore
from groovy.nodes.ai.inference import (
    require_model,
    run_audio_to_midi,
    run_deepfake_detect,
    run_detect_watermark,
    run_embed_watermark,
    run_denoise,
    run_diarize_transcribe,
    run_generate_audio,
    run_midi_to_audio,
    run_separate_stems,
    run_separate_to_objects,
    run_sing_from_midi,
    run_tts,
    run_timbre_transfer,
    run_voice_convert,
    run_speech_translate,
    run_whisper_stt,
)

HANDLERS = {
    "Denoise": run_denoise,
    "SeparateStems": run_separate_stems,
    "SeparateToObjects": run_separate_to_objects,
    "WhisperSTT": run_whisper_stt,
    "DiarizeTranscribe": run_diarize_transcribe,
    "TTS": run_tts,
    "VoiceConvert": run_voice_convert,
    "SpeechTranslate": run_speech_translate,
    "TimbreTransfer": run_timbre_transfer,
    "AudioToMIDI": run_audio_to_midi,
    "DeepfakeDetect": run_deepfake_detect,
    "EmbedWatermark": run_embed_watermark,
    "DetectWatermark": run_detect_watermark,
    "MIDIToAudio": run_midi_to_audio,
    "GenerateAudio": run_generate_audio,
    "SingFromMIDI": run_sing_from_midi,
}


def main() -> None:
    import os

    payload = json.loads(sys.stdin.read())
    node_type = payload["node_type"]
    project_dir = Path(payload["project_dir"])
    os.environ.setdefault("GROOVY_PROJECT_DIR", str(project_dir.resolve()))
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
