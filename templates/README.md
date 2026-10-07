# GroovyUI Template Workflows (OSS)

Public picker set for standard studio mode (ISMIR 2026 LBD). Validated in CI via `groovy-verify`.

Dev-only / featured templates live locally under `docs/internal/templates/` (gitignored) and appear when studio **dev mode** (⌘⇧D) is on. See `apps/studio/src/templateUi.ts` (`STANDARD_BUNDLED_TEMPLATE_IDS` vs `FEATURED_BUNDLED_TEMPLATE_IDS`).

| Template | File | Models |
|----------|------|--------|
| Empty Canvas | [empty-canvas.groovy.json](empty-canvas.groovy.json) | — |
| Hello GroovyUI | [hello-groovy.groovy.json](hello-groovy.groovy.json) | `kokoro-82m` |
| Podcast Denoise | [podcast-denoise.groovy.json](podcast-denoise.groovy.json) | `deepfilternet-v3` |
| Isolate to Transcribe | [isolate-vocals-to-transcribe.groovy.json](isolate-vocals-to-transcribe.groovy.json) | `demucs-v4`, Whisper |
| Isolate to Transcribe + Translate | [isolate-vocals-to-transcribe-translate.groovy.json](isolate-vocals-to-transcribe-translate.groovy.json) | `demucs-v4`, Whisper, `m2m100-418m` |
| Prompt Modular Synth | [prompt-modular-synth.groovy.json](prompt-modular-synth.groovy.json) | `kokoro-82m` |
| Video to Audio | [video-to-audio.groovy.json](video-to-audio.groovy.json) | `diff-foley` (default; experimental — CUDA testing) |

Sample assets: `assets/samples/` (`podcast_denoise_demo.wav`, `stem_separation_demo.wav`, `video480p.mov`).
