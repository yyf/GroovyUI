# GroovyUI Template Workflows

29 curated `.groovy.json` starter graphs. Validated in CI via `groovy-verify` and `tests/test_all_templates.py`.

Featured picker order (studio): see `apps/studio/src/templateUi.ts` and [TEMPLATE_PORTFOLIO_PRIORITY.md](../docs/internal/TEMPLATE_PORTFOLIO_PRIORITY.md).

| Template | File | Phase | Models |
|----------|------|-------|--------|
| Hello Groovy | [hello-groovy.groovy.json](hello-groovy.groovy.json) | 0 | — |
| Podcast Denoise | [podcast-denoise.groovy.json](podcast-denoise.groovy.json) | 1 | `deepfilternet-v3` |
| Stem Split Vocals | [stem-split-vocals.groovy.json](stem-split-vocals.groovy.json) | 1 / **featured** | `demucs-v4` |
| Transcribe Dialogue | [transcribe-dialogue.groovy.json](transcribe-dialogue.groovy.json) | 1 / **featured** | `whisper-large-v3-turbo` |
| Cleanup and Transcribe | [cleanup-and-transcribe.groovy.json](cleanup-and-transcribe.groovy.json) | 1 / **featured** | deepfilternet + whisper |
| Diarize and Transcribe | [diarize-and-transcribe.groovy.json](diarize-and-transcribe.groovy.json) | 1 / **featured** | whisper + pyannote (energy fallback) |
| TTS Greeting | [tts-greeting.groovy.json](tts-greeting.groovy.json) | 1 / **featured** | `kokoro-82m` |
| Voice Cloning | [voice-cloning.groovy.json](voice-cloning.groovy.json) | 1 / **featured** | `f5-tts-base` (+ reference LoadAudio) |
| Prompt TTS Modular | [prompt-tts-modular.groovy.json](prompt-tts-modular.groovy.json) | 2 / **featured** | `kokoro-82m` |
| Simple FM Synth | [simple-fm-synth.groovy.json](simple-fm-synth.groovy.json) | 2 / **featured** | — (Osc + FloatMath + ControlCurves) |
| Karaoke Stems | [karaoke-stems.groovy.json](karaoke-stems.groovy.json) | 1 / **featured** | `demucs-v4` |
| Stable Audio | [stable-audio.groovy.json](stable-audio.groovy.json) | 2 / **featured** | `stable-audio-open-1.0` |
| Text to Music | [text-to-music.groovy.json](text-to-music.groovy.json) | 2 / **featured** | `musicgen-small` |
| Voice Convert Demo | [voice-convert-demo.groovy.json](voice-convert-demo.groovy.json) | 1 | `rvc-v2-base` |
| Transcribe to MIDI | [transcribe-to-midi.groovy.json](transcribe-to-midi.groovy.json) | 1.1 | `basic-pitch` |
| Transcribe and Regenerate | [transcribe-and-regenerate.groovy.json](transcribe-and-regenerate.groovy.json) | 1.1 / **featured** | `basic-pitch`, `musicgen-melody-small` |
| Authenticity Check | [authenticity-check.groovy.json](authenticity-check.groovy.json) | 1.1 | `rawnet2-asvspoof` |
| Stem to Remix | [stem-to-remix.groovy.json](stem-to-remix.groovy.json) | 2 | demucs, basic-pitch, musicgen |
| Sing from MIDI | [sing-from-midi.groovy.json](sing-from-midi.groovy.json) | 2 | `diffsinger-opencpop` |
| MIDI Automation Demo | [midi-automation-demo.groovy.json](midi-automation-demo.groovy.json) | 2 | `deepfilternet-v3` |
| Surround Downmix | [surround-downmix.groovy.json](surround-downmix.groovy.json) | 2 | — |
| Surround Mix | [surround-mix.groovy.json](surround-mix.groovy.json) | 2.1 | — |
| Ambisonic VR Preview | [ambisonic-vr-preview.groovy.json](ambisonic-vr-preview.groovy.json) | 2 | — |
| Object Spatial Demo | [object-spatial-demo.groovy.json](object-spatial-demo.groovy.json) | 2 | — |
| Stems to Spatial | [stems-to-spatial.groovy.json](stems-to-spatial.groovy.json) | 2.1 | `demucs-v4-objects` |
| Keyboard to Music | [keyboard-to-music.groovy.json](keyboard-to-music.groovy.json) | 2.5 | `musicgen-melody-small` |
| Transcribe to Synth | [transcribe-to-synth.groovy.json](transcribe-to-synth.groovy.json) | 2.5 | basic-pitch, musicgen |
| AI MIDI to Hardware | [ai-midi-to-hardware.groovy.json](ai-midi-to-hardware.groovy.json) | 2.5 | musicgen |
| A/B Compare Demo | [ab-compare-demo.groovy.json](ab-compare-demo.groovy.json) | 2 hardening | `deepfilternet-v3` |

Sample assets: `workspace/assets/samples/` (default LoadAudio: `male-1.wav`; also `dialogue_48k.wav`, `surround_51.wav`, etc.).
