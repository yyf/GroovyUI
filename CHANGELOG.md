# GroovyUI Phase 0–2

## Unreleased

### Added

- **Plan mode LLM (Claude, BYOK)** — Model Browser **Plan** picks which published models fit a task (Claude public-family suggestions remapped locally, or deterministic recommend without a key). It does **not** compose graphs — that is **Generate (⌘G)**. Private catalogs are not sent to Claude. Install / Drop stay explicit.
- **Studio template modes** — standard picker shows the ISMIR LBD demo set (`hello-groovy`, `podcast-denoise`, `prompt-modular-synth`, `isolate-vocals-to-transcribe`); **⌘D / Ctrl+D** toggles studio dev mode for the full featured list. Duplicate selection is **⌘⇧D / Ctrl+Shift+D**.
- **Bundled sample media in git** — allowlisted `assets/samples/` demo files (including `podcast_denoise_demo.wav`, `stem_separation_demo.wav`) so cold clones and release builds seed the workspace without local uploads.
- **`EmbedWatermark` / `DetectWatermark`** — Meta **AudioSeal** (MIT) nodes for localized audio watermark embed + detect with 16-bit payload decode; registry model `audioseal-16bit`.
- **`watermark-embed-detect` template** — Trust domain: LoadAudio → EmbedWatermark → DetectWatermark; preview JSON report and save watermarked WAV.
- **A/B sample check** — when two nodes are selected, Inspector Summary / Metrics show a horizontal sample table (Samples · Rate · Duration · Layout · Hash)
- **`sample-verify` template** — Compare-domain demo: LoadAudio → Preview with VerifySamples on each hop
- **`BeatTrack`** — AUDIO analyzer that rebuilds a Clock-style pulse train (plus half-time) from detected beats; optional fallback Clock when the groove is too weak. DSP (spectral flux), not a downloaded model.
- **⌘F find node** — dialog to search by node name or id; Enter frames and pulses the match.
- **Status LEDs** — click red/warn API / RND / CVS to open the fault log in a new window.
- **⌘C Compliance** — opens the Compliance drawer. Canvas copy is **⌘⇧C** so it does not collide.
- **`neural-modular-rack` featured** — Mix-bus copy of the self-playing rack (no Ambisonics / no RAVE): dual clock 88/44, intermittent pentatonic bass, probability-gated saw, articulating FM/bandpass drone, ACE-Step (MIT) into Granulate, very dry Mix/Reverb. Commercial-ok (ACE MIT + DSP).
- **`self-playing-neural-rack`** — Clock/S&H/Quantizer rack with Osc as the DSP voice, ACE-Step as a MIDI-conditioned oscillator (`AutomationToMIDI`), RAVE as the filter, object-bus freeze through FOA. Catalog only (hidden from the studio picker; RAVE is CC-BY-NC). Use **`neural-modular-rack`** for the commercial-ok Modular menu entry.
- **`AutomationToMIDI`** — convert stepwise Hz CV (Quantizer / S&H) to MIDI notes for AI oscillators. Offline sequencer read, not a live callback.
- **`authenticity-check` featured** — Trust-domain picker demo of all three Authenticity palette nodes (`VerifyProvenance`, `DeepfakeDetect`, `AuthenticitySummary`) plus source and detector pass-through Previews
- **License-clear 7-day sprint templates** (featured): `compare-whisper-sizes`, `script-to-vo-master`, `karaoke-guide-vocal`, `instrumental-tts-dub`, `melody-to-modular-synth`, `compare-stemmers`, `stem-lyrics-to-ace` — compound / A/B / modular graphs (MIT/Apache/ACE); Settings license matrix + integrity overrides updated
- **Settings → Model installs** — list local weight installs with size, per-model Remove (checkbox / button), **HF cache** (opens shared Hugging Face hub folder for manual delete), and **Remove all installed models**; APIs `GET /api/models/installed`, `POST /api/models/installed/clear`, `POST /api/system/reveal-hf-cache`
- **`SpeechTranslate` + `seamless-m4t-v2-large`** — speech-to-speech localization (Meta SeamlessM4T v2); `speaker_id` 0–199 (vocoder voice, not gender/source clone); stub when Inference=Stub; Real uses transformers when installed
- **`localize-dialogue-a-to-b` template** — denoise → Soft eng→spa translate → normalize → preview/export (featured; CC-BY-NC weights)

### Changed

- **Model Browser Search** — Find models tab removed; Search ranks the local published catalog (keywords or natural-language task + rationales / workflow handoff). Empty query browses; Discover stays HF browse-only. Legacy `mode: "recommend"` launches map to Search.
- **Plan vs Generate** — Plan lives under Model Browser only (no top-bar / ⌘L entry): recommends models for a task (Install / Drop). Generate (⌘G) drafts graphs (LLM or templates). Plan no longer returns workflow blueprints.
- **Generate (⌘G)** palette — selection / path / model chips / focus / blueprint chrome use signal red (`--accent`) instead of the interim blue highlight set.
- **Generate (⌘G)** — bottom-stage composer over the canvas with an explicit **With LLM** / **Without LLM** choice (defaults to LLM when a key is set, but never auto-swaps at submit). LLM: model chips + blueprint review + Save JSON/image; Apply unlocks when all nodes exist. Without LLM: deterministic bundled template match. Model Browser → Suggest workflow stays template-only.
- **ISMIR demo LoadAudio paths** — `podcast-denoise` uses `assets/samples/podcast_denoise_demo.wav`; `isolate-vocals-to-transcribe` uses `assets/samples/stem_separation_demo.wav` (CI still injects a tone WAV fixture for the isolate template). Shipped samples are only those two demos plus `automation_cc7.mid`; older clips live under local `assets/samples/archived/`.
- **Compliance fast path** — Install/render Preview no longer auto-auditions; Play remains the explicit cached-PCM audition (patch-bay, not a DAW).
- **Marquee A/B select** — box-select prefers nodes over wires (`edgesSelectable={false}`) so two-node A/B compare works without only shift-click
- **ACE-Step load errors** — do not treat every Hub message containing `401` as access-denied; skip a broken huggingface-cli login when Settings has no token; include the real Hub error on failure.
- **`neural-modular-rack` mix** — IDM diptych at 136 BPM: syncopated deep sine vs on-grid ticks; ice/metallic sparkles through a long reverb plus light stereo Granulate; ACE-Step (Telefon Tel Aviv *TTV* / Kodomo *Deep Winter*); bus 50/50.
- **Render canvas** — pulse-highlight the active node; after 5s of silence on an AI hop, show **Downloading model…** on the node and in the render bar.
- **Status LEDs** — click red/warn **API / RND / CVS** to open the error in a new window; failed render hops pulse on the canvas with the error text.
- **`melody-to-modular-synth`** — catalog only (hidden from the studio picker); Modular menu keeps **`neural-modular-rack`**.
- **Authenticity sidecar lookup** — VerifyProvenance uses `{stem}.provenance.json` beside the audio, or that filename if it appears exactly once in the project
- **Authenticity tab refresh** — always include AuthenticitySummary in the render job; prefer its merged report over a selected DeepfakeDetect; ignore stale fetches so sidecar status updates on the first completed render
- **Upload keeps provenance sidecars** — dropping a wav that already exists next to `*.provenance.json` reuses that project path (instead of copying audio-only into `assets/uploads/`)
- **Authenticity tab** — prefers `AuthenticitySummary` over the first AUTHENTICITY socket so Label is not blank
- **Mixed node outputs** — executor caches AUTHENTICITY+AUDIO (and other mixed `RETURN_TYPES`) as MULTI in slot order so DeepfakeDetect pass-through Preview can use outlet 1; stale 1-slot caches are ignored
- **MusicGen Melody conditioning** — prefer Demucs vocals as HF audio conditioner when wired; band-pass 120–3500 Hz + silence trim; cap tokens to melody duration; default `temperature=0.7` + top_k/top_p; soft output peak
- **`ChannelConvert` canvas labels** — e.g. MONO inlet / STEREO outlet when converting to stereo
- **`song-cover-remix`** — LoadAudio uses `Signe_Jakobsen_short.mp4`; vocals-conditioned MusicGen + RVC → stereo Mix
- **Sample bootstrap** — copy bundled `.mp4` / `.m4a` / `.mp3` into the project workspace alongside WAV/MIDI
- **`musicgen-small`** — real text-to-music inference via `facebook/musicgen-small` (no longer a tone stub when `GROOVY_INFERENCE_STUB` is off)
- **Featured template picker** — portfolio ship set only: podcast denoise → stems → dialogue → diarize → TTS → text-to-music → regenerate → hello
- **Kokoro TTS** — no silent sine fallback when stub is off (raises if package missing)

### Added

- **`song-cover-remix` template** — Demucs → Basic Pitch → MusicGen Melody → RVC compound cover/remix chain (featured)
- **`denoise-diarize-transcribe` template** — DeepFilterNet → pyannote → Whisper who-said-what chain (bundled; hidden from default picker)
- **`rave-v1` + `TimbreTransfer`** — Model Browser install downloads ACIDS RAVE TorchScript (`sol_ordinario_fast`); real encode/decode inference (stub only when Inference = Stub)
- **Sample-accuracy honesty** — canvas chip when AI/nondeterministic hops present; Note nodes on generative templates; `sample_accurate` / `deterministic` / `duration_locked` on node schemas (metadata only; no executor gates)
- **Template Notes** — compact `Note` on every bundled workflow template
- **Connection color** — click a wire → Inspector palette swatches (B/W/signal-red + greys); optional `links[].color` in workflow JSON
- **Active-edge glow** — subtle drop-shadow on animated path wires during audition (tracks stroke color; no heavy VFX)
- **`ChannelMerge`** — stack mono / LoadAudio per-channel outlets into stereo (or up to 7.1) for `SaveAudio`
- **Multi-select channel info** — Inspector selection / A/B compare shows per-node channel layout when known

### Removed

- **`StemPick`** node — unused after SeparateStems exposed per-stem AUDIO outs

## [0.19.0] - 2026-07-09

**Phase 2.6 signal integrity** — patch-bay trust layer before export (v1 + expansion).

### Added

- **`groovy.executor.signal_integrity`** — manifest audit helpers (`audit_manifest`, `audit_output_contract`, `attach_signal_metadata`)
- **`groovy.executor.template_integrity_registry`** — auto-built specs for all 22 bundled templates
- **Render manifest enrichment** — per-hop `sample_rate`, `channel_layout`, `frame_count`, `content_hash` on AUDIO/STEMS outputs (including cache hits)
- **`tests/test_signal_integrity.py`** — Mix SR/layout rejection, fan-in layout preservation, module I/O passthrough, SaveAudio round-trip, manifest fields
- **`tests/test_template_signal_integrity.py`** — L1–L3 for **all 22** templates; A/B spot check for `ab-compare-demo`
- **`GET /api/jobs/{job_id}/manifest`** — render manifest for studio debugging
- **`GET /api/cache/{cache_id}/metrics`** — peak, LUFS, SR, layout per cached AUDIO clip
- **Node Helper** — per-node signal metrics (peak, LUFS, SR, layout) on Outputs tab

### Phase 2.6 gate (complete)

- All **22 bundled templates** pass L1–L3 in CI (L0 unchanged via `groovy-verify`)
- SR/layout mismatch without Resample/ChannelConvert surfaces executor error
- SaveAudio round-trip + provenance sidecar fidelity
- Cross-machine golden (`hello-groovy`) unchanged

## [0.18.0] - 2026-07-08

**Phase 2 hardening complete** — studio graph UX, A/B compare, typed sockets, template CI gate.

### Added

- **A/B waveform compare** — shift-select two rendered nodes; overlay waveforms in NodeHelper
- **A/B signal analysis** — `POST /api/compare/analyze` with PCM metrics + optional model narrative (`groovy-signal-diff`, `whisper-ab-compare`)
- **Chain hop compare** — auto-redirect when selections share cache (e.g. Normalize → Preview passthrough)
- Template: `ab-compare-demo` (22 total)
- **Canvas copy/paste** — Cmd/Ctrl+C/V duplicates selected nodes + internal wires; Cmd/Ctrl+D quick duplicate
- **Box select** — drag on empty canvas to marquee-select (left-drag); middle/right-drag or Space+drag to pan
- **Node helper I/O** — Inputs/Outputs tabs list all schema sockets with color type badges; selected MODEL_REF shows registry card
- **Typed connection labels** — edge wires use color-coded socket type labels (AUDIO, MIDI, TEXT, etc.)
- Studio vitest suite for workflow graph helpers (`pnpm --filter @groovy/studio test` or `just test-studio`)
- `tests/test_all_templates.py` — validates all `templates/*.groovy.json` via `groovy-verify`

### Fixed

- **Edge connections** — derive `edges` from workflow instead of fighting React Flow internal state
- **Node deletion** — Delete/Backspace syncs removals to workflow (nodes, links, groups)
- **Multi-select** — Shift/Cmd/Ctrl additive selection without conflicting with marquee select
- **LoadAudio path input** — widget edits no longer clear selection or wipe text after one character
- **Node sync** — preserve React Flow measured dimensions during workflow updates
- Podcast template default sample: `podcast_denoise_demo.wav`

### Fixed (0.18.0 follow-up)

- **Node helper crash on select** — `useMemo` for input wiring ran after early return (Rules of Hooks violation); blank UI on node click
- **A/B analyze "Not Found"** — removed pre-install call that could fail; `groovy-signal-diff` runs without model weights; clearer errors when API route or cache is missing
- **Whisper A/B compare** — no longer requires separately installing `whisper-large-v3-turbo`

## [0.17.0] - 2026-07-06

### Added (Phase 2 closeout)

- **`MultichannelNormalize`** — EBU R128 / peak loudness on multichannel beds (no fold)
- **`MIDINoteGate`** — MIDI note on/off → `AUTOMATION` gate curve
- **`ChannelConvert`** — 7.1 → stereo ITU downmix
- **`Transcode`** — optional **ffmpeg** backend for `mp3` / `aac` / `opus` export
- **Subgraph collapse/expand** — grouped nodes collapse to proxy module node on canvas
- **Community packs** — `groovy-install pack <id>`, `GET /api/packs`, `POST /api/packs/{id}/install`
- **Template generator** agent — `POST /api/workflow/generate-template` + studio **Save as template**
- **Registry freshness** agent — `GET /api/registry/freshness`
- Studio toolbar: **Collapse group**, **Install pack**

## [0.16.0] - 2026-07-06

### Added (Phase 2.5 live control bridge)

- **`MIDIInDevice`**, **`MIDIOutDevice`**, **`OSCInLive`** nodes (opt-in Live I/O tier)
- **Settings → Live I/O** drawer — MIDI in/out + OSC toggles, device enumeration
- Host API: `GET /api/midi/devices`, `GET|POST /api/settings/live-io`, `POST /api/midi/in/event`, `POST /api/midi/out/send`, `POST /api/osc/in`, `GET /api/osc/events`
- WebSocket `/api/ws/midi/in`; OSC UDP listener on `127.0.0.1:9000` (allowlist `/groovy/*`)
- Studio **Web MIDI** capture + OSC widget routing via live hub
- Templates: `keyboard-to-music`, `transcribe-to-synth`, `ai-midi-to-hardware` (21 total)

## [0.15.0] - 2026-07-06

### Added (Phase 2.1 OBA completion)

- **`ObjectMerge`** — combine beds + objects from two OBA scenes
- **`ObjectAnimate`** — keyframed azimuth/gain dynamics; renderer honors interpolated motion
- **`RenderObjectScene`** — `5.1` output layout (simple azimuth pan law)
- **`MIDIToFloat`** — reads frame-indexed CC events from MIDI capture sidecar
- Template: `surround-mix` (20 total)

## [0.14.0] - 2026-07-06

### Added (Phase 2.1 OBA + subgraph I/O)

- **ModuleInlet / ModuleOutlet** — subgraph boundary nodes; `extractModule` records `inlets`/`outlets` (explicit or auto-detected)
- **SeparateToObjects** — stems → OBA scene (`demucs-v4-objects` registry entry, aliases `demucs-v4`)
- **ObjectPlacement** — heuristic azimuth spread (`object-placement-heuristic`)
- Template: `stems-to-spatial` (17 total)

## [0.13.0] - 2026-07-06

### Added (Phase 2 immersive foundation)

- **`AMBISONICS` socket** — `AmbisonicBuffer` cache type; `AmbisonicEncode`, `AmbisonicDecode`, `AmbisonicRotate` nodes (FOA AmbiX ACN/SN3D)
- **`OBA` socket** — `ObjectScene` cache type; `ObjectFromAudio`, `RenderObjectScene` (deterministic stereo pan)
- Templates: `ambisonic-vr-preview`, `object-spatial-demo` (16 total)
- Immersive tier palette includes ambisonic + OBA nodes

## [0.12.0] - 2026-07-06

### Added (Phase 2 agents + batch + subgraph import)

- **License scanner** agent + `POST /api/workflow/license-scan` — NC model flags + commercial-safe swap suggestions in Compliance drawer
- **Batch mode** — `POST /api/batch/render` folder-in workflow runs; studio **Batch folder** toolbar
- **Import module** — load `.module.json` subgraph exports into canvas
- Dev plan + pre-execution research backlog for surround/immersive/spatial templates

## [0.11.0] - 2026-07-06

### Added (Phase 2 multichannel + modular)

- **ComfyUI import** — `import_comfy_workflow` converter + `POST /api/workflow/import/comfy`; studio **Import ComfyUI** toolbar button
- **ChannelConvert 5.1 downmix** — ITU-R BS.775 stereo fold when `channel_layout` is `5.1`
- **Transcode** node — write FLAC/WAV export via soundfile while passing audio through
- **Subgraph modules** — multi-select (Shift+drag), **Group**, **Export module** (`.module.json`)
- Template: `surround-downmix` (14 total)
- **Node helper format panel** — channels, layout, encoding scheme (5.1, Atmos bed, FOA/HOA, ADM BWF), ACN/SN3D when detected; LoadAudio probes source file via `GET /api/project/audio-meta`

## [0.10.0] - 2026-07-06

### Added (Phase 2 modular + executor)

- **FloatRoute** control node — blend between two AUTOMATION curves
- **Progressive node palette** — Core / Modular / Immersive / All tier filters
- **Executor node cache skip** — unchanged nodes reuse prior outputs (`cache_hit` in manifest)
- **Playback path glow** — active edges highlight during chain/node audition

## [0.9.0] - 2026-07-06

### Added (Phase 2 MIDI-AI)

- **GenerateAudio** node — text-conditioned music generation (`musicgen-small`)
- **SingFromMIDI** node — MIDI + lyrics singing synthesis (`diffsinger-opencpop`)
- Templates: `text-to-music`, `sing-from-midi` (13 total)
- Transport bar waveform scrubber preview above chain audio player
- Model Browser filters: music-generation, singing-synthesis

## [0.8.0] - 2026-07-06

### Added (Phase 0/1 polish)

- **Undo/redo** — workflow history with Cmd+Z / Cmd+Shift+Z
- **Onboarding overlay** — first-run welcome; starts Hello Groovy template
- **Drag-drop audio** — drop WAV/FLAC/MP3 onto canvas; `POST /api/project/upload`
- **UX-6** — per-node headphone audition on canvas; double-click node to audition; Space to play chain
- **Real bundle install** — `groovy-verify-weights` model copies bundled weights (non-stub install path)

## [0.7.0] - 2026-07-06

### Added (Phase 2 control I/O)

- **Control I/O** — `AutomationBuffer` cache type; `ControlCurve`, `MIDIToFloat`, `AutomationApply`, `FloatMath`, `ChannelConvert` nodes
- `AUTOMATION` socket wiring in executor and node-sdk
- Template: `midi-automation-demo` (11 total)
- **Workflow suggester** agent + `POST /api/workflow/suggest`; Cmd+K **Suggest workflow** tab in studio
- **Registry curator** agent + `groovy-registry` CLI (`ingest`, `drafts`, `approve`) + registry API
- **Node helper enricher** — plain-language descriptions on `GET /api/nodes/{type}`
- UX-6: mini waveform thumbnail in node helper Outputs tab

## [0.6.0] - 2026-07-06

### Added (Phase 2 foundation)

- **MIDIToAudio** node + `musicgen-melody-small` registry entry (dev stub)
- **Prompt** and **LoadMIDI** core nodes; `TEXT` input socket wiring
- Templates: `transcribe-and-regenerate`, `stem-to-remix` (10 total)
- Cross-machine reproducibility golden test (`hello_groovy_pcm.sha256`)
- Model install download pipeline with HuggingFace allowlist + checksum verify

## [0.5.0] - 2026-07-06

### Added (Phase 1.1)

- **MIDI socket** — `MidiBuffer` cache type; `AudioToMIDI` node + `basic-pitch` registry entry
- **Authenticity** — `VerifyProvenance`, `DeepfakeDetect`, `AuthenticitySummary` nodes; `AUTHENTICITY` socket
- Templates: `authenticity-check`, `transcribe-to-midi` (8 total)
- Compliance drawer **Authenticity** tab + `GET /api/authenticity/{id}`
- `LoadAudio` imports sibling `.provenance.json` sidecars
- Model Browser filters: audio-to-midi, deepfake-detection
- CI runs `groovy-verify` after pytest

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
