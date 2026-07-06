# GroovyUI Phase 0–1

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
