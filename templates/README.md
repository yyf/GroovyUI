# GroovyUI Template Workflows (OSS)

Public picker set for standard studio mode (ISMIR 2026 LBD). Validated in CI via `groovy-verify`.

Dev-only / featured templates live locally under `docs/internal/templates/` (gitignored) and appear when studio **dev mode** (⌘⇧D) is on. See `apps/studio/src/templateUi.ts` (`STANDARD_BUNDLED_TEMPLATE_IDS` vs `FEATURED_BUNDLED_TEMPLATE_IDS`).

| Template | File | Models |
|----------|------|--------|
| Empty Canvas | [empty-canvas.groovy.json](empty-canvas.groovy.json) | — |
| Hello GroovyUI | [hello-groovy.groovy.json](hello-groovy.groovy.json) | `kokoro-82m` |
| Podcast Denoise | [podcast-denoise.groovy.json](podcast-denoise.groovy.json) | `deepfilternet-v3` |
| Isolate to Transcribe | [isolate-vocals-to-transcribe.groovy.json](isolate-vocals-to-transcribe.groovy.json) | `demucs-v4`, Whisper |
| Isolate → STT → Translate → TTS | [isolate-vocals-to-transcribe-translate.groovy.json](isolate-vocals-to-transcribe-translate.groovy.json) | `demucs-v4`, Whisper, `m2m100-418m`, `kokoro-82m` (zh) |
| Prompt Modular Synth | [prompt-modular-synth.groovy.json](prompt-modular-synth.groovy.json) | `kokoro-82m` |
| TTS with Emotion Editing | [tts-emotion-edit.groovy.json](tts-emotion-edit.groovy.json) | `kokoro-82m`, `step-audio-editx` (Step = MLX on Apple Silicon or CUDA+vLLM on Linux) |
| ACE-Step 1.5 SFT | [ace-step-1.5-sft.groovy.json](ace-step-1.5-sft.groovy.json) | `ace-step-1.5-sft` (MIT; prefer NVIDIA CUDA) |
| ASR Benchmark — WER / CER | [asr-benchmark-wer-cer.groovy.json](asr-benchmark-wer-cer.groovy.json) | `kokoro-82m` → `whisper-small-en` ∥ `whisper-large-v3-turbo`; drag-select transcript Previews for WER A/B |
| Demucs vs Open-Unmix — Stem A/B | [demucs-vs-openunmix.groovy.json](demucs-vs-openunmix.groovy.json) | `demucs-v4` ∥ `openunmix-umx` vocals; A/B pairwise (no GT): loudness / waveform / SDR / SI-SDR / mel cosine / LSD |
| Video to Audio | [video-to-audio.groovy.json](video-to-audio.groovy.json) | `diff-foley` (default; experimental — CUDA testing) |

Featured-only (⌘⇧D): Trailer Bumper — Music + SFX Layers ([layered-music-sfx.groovy.json](layered-music-sfx.groovy.json)) — Community / NC `stable-audio-open-small` ×2 → Mix.

Sample assets: `assets/samples/` (`podcast_denoise_demo.wav`, `stem_separation_demo.wav`, `video480p.mov`).
