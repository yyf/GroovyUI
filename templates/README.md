# GroovyUI Template Workflows (OSS)

Public picker set for **standard** studio mode (ISMIR 2026 LBD). Validated in CI via `groovy-verify`.

This README lists **only** `STANDARD_BUNDLED_TEMPLATE_IDS` from `apps/studio/src/templateUi.ts`. Do **not** document featured / studio-dev-only / `docs/internal/templates/` workflows here — those stay internal.

| Template | File | Models |
|----------|------|--------|
| Empty Canvas | [empty-canvas.groovy.json](empty-canvas.groovy.json) | — |
| Hello GroovyUI | [hello-groovy.groovy.json](hello-groovy.groovy.json) | `kokoro-82m` |
| Podcast Denoise | [podcast-denoise.groovy.json](podcast-denoise.groovy.json) | `deepfilternet-v3` |
| Isolate to Transcribe | [isolate-vocals-to-transcribe.groovy.json](isolate-vocals-to-transcribe.groovy.json) | `demucs-v4`, Whisper |
| Isolate → STT → Translate → TTS | [isolate-vocals-to-transcribe-translate.groovy.json](isolate-vocals-to-transcribe-translate.groovy.json) | `demucs-v4`, Whisper, `m2m100-418m`, `kokoro-82m` (zh) |
| Prompt Modular Synth | [prompt-modular-synth.groovy.json](prompt-modular-synth.groovy.json) | `kokoro-82m` |
| Moving Clouds | [moving-clouds.groovy.json](moving-clouds.groovy.json) | — (modular grain cloud + opposite-phase stereo pans) |
| Shepard Tone | [shepard-tone.groovy.json](shepard-tone.groovy.json) | — (periodic Shepard–Risset / Dunkirk-style endless rise; modular DSP) |
| Rutt/Etra Scan Processor | [rutt-etra-scan.groovy.json](rutt-etra-scan.groovy.json) | — (LoadVideo luma → Z Push grayscale scan terrain → PreviewVideo; modular DSP) |
| TTS with Emotion Editing | [tts-emotion-edit.groovy.json](tts-emotion-edit.groovy.json) | `kokoro-82m`, `step-audio-editx` (Step = MLX on Apple Silicon or CUDA+vLLM on Linux) |
| Text to MIDI | [text-to-midi.groovy.json](text-to-midi.groovy.json) | `midi-llm` → PreviewMidi / SaveMidi; SynthMidi (pretty_midi DSP) → SaveAudio; path demo: `midi-gen` |
| Text to Music | [ace-step-1.5-sft.groovy.json](ace-step-1.5-sft.groovy.json) | `ace-step-1.5-sft` (MIT; prefer NVIDIA CUDA) — style + optional lyrics Prompts |
| ASR Benchmark — WER / CER | [asr-benchmark-wer-cer.groovy.json](asr-benchmark-wer-cer.groovy.json) | `kokoro-82m` → `whisper-small-en` ∥ `whisper-large-v3-turbo`; drag-select transcript Previews for WER A/B |
| Demucs vs Open-Unmix — Stem A/B | [demucs-vs-openunmix.groovy.json](demucs-vs-openunmix.groovy.json) | `demucs-v4` ∥ `openunmix-umx` vocals; A/B pairwise (no GT): loudness / waveform / SDR / SI-SDR / mel cosine / LSD |
| ACE-Step Dual LoRA A/B | [ace-step-dual-lora-ab.groovy.json](ace-step-dual-lora-ab.groovy.json) | Experimental: turbo + `ace-step-cny-lora` ∥ `ace-step-ambient-lora` (NC / community); Inspector A/B |
| Watermark Embed and Detect | [watermark-embed-detect.groovy.json](watermark-embed-detect.groovy.json) | `audioseal-16bit` (MIT) — EmbedWatermark → DetectWatermark |
| Text to Video | [text-to-video.groovy.json](text-to-video.groovy.json) | `ltx-2.3-q4` (MLX Mac · ~27 GB; `SwitchImage` defaults GenerateImage/`flux-klein-4b` + PreviewImage; select=0 LoadImage A/B; path demo: `flux-image`) |

Sample assets: `assets/samples/` (`podcast_denoise_demo.wav`, `stem_separation_demo.wav`, `video480p.mov`).
