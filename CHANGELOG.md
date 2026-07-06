# GroovyUI Phase 0–1

## [0.4.0] - 2026-07-06

### Added (Phase 1 complete)

- Provenance pipeline: parent lineage on cache writes, `GET /api/cache/{id}/provenance`, `POST /api/workflow/provenance`
- SaveAudio exports `.provenance.json` sidecar alongside WAV
- Model recommender agent (`POST /api/models/recommend`) + install recovery agent enhancements
- `groovy-model` CLI (`install`, `list`)
- Studio: Compliance Provenance + Disclosure tabs, Model Browser filters + Find models mode + install failure recovery UI
- Focus mode (`F` / `\`), auto-render on Play when stale, Shift+R render all
- Node helper Provenance tab

## [0.3.0] - 2026-07-06

### Added (Phase 1 MVP)

- AI nodes: `SeparateStems`, `WhisperSTT`, `TTS`, `VoiceConvert` (dev inference stubs + worker dispatch)
- `STEMS` cache bundle + core `StemPick` node
- Templates: `stem-split-vocals`, `transcribe-dialogue`, `tts-greeting`, `voice-convert-demo` (5 total with Phase 0)
- Compliance API (`POST /api/workflow/compliance`) + studio Compliance drawer (License tab)
- Node palette — add Core/AI nodes from sidebar
- Per-node audition in node helper Outputs tab
- `groovy-verify` CLI — validates all workflow templates

## [0.2.0] - 2026-07-05

### Added (Phase 1 foundation)

- `packages/model-registry` — seed catalog, search, install state, recovery suggestions
- `nodes/ai` — `Denoise` node with subprocess worker isolation (ADR-003)
- Model API: `GET /api/models`, `POST /api/models/search`, `POST /api/models/{id}/install`
- Studio Model Browser overlay (Cmd+K) with one-click install
- `podcast-denoise` template (LoadAudio → Denoise → Normalize → Preview)
- MODEL_REF widget support in node helper

## [0.1.0] - 2026-07-05

### Added

- Monorepo scaffold: Python packages (schema, node-sdk, executor), core nodes, FastAPI server
- Phase 0 core nodes: LoadAudio, SaveAudio, Resample, Trim, Mix, Normalize, Preview
- Hello Groovy template and golden test path
- React studio shell with graph canvas, node helper (Config/Inputs/Outputs), WebSocket render progress, transport bar, and cached preview playback
- Template list/get API (`GET /api/templates`, `GET /api/templates/{id}`)
