# GroovyUI

**ComfyUI for audio, with the soul of a modular synth.**

Patch AI audio models together in a node graph — explore, compare, audition, and share workflows without leaving the canvas. Every studio render is sample-accurate and reproducible. When you need realtime, export a frozen chain to a JUCE project or web app.

> *Patch AI audio like modular synthesis. Render with sample accuracy. Ship to realtime when you're ready.*

**Status:** Phase 1 in progress — model registry, AI Denoise node, Model Browser (Cmd+K).

---

## Highlights

- **Model discovery** — search by task (TTS, stem split, denoise, voice clone); one-click install with failure recovery
- **Flow-first UX** — per-node and per-chain audition from cached renders; node helper menu; Cmd+K model browser
- **Shareable workflows** — `.groovy.json` graphs with resolved model refs and cross-machine reproducibility
- **Compliance built in** — per-chain license summary; AI audio provenance and disclosure on every output
- **Inbound authenticity** *(Phase 1.1)* — verify provenance sidecars and run deepfake/spoof classifiers on received audio
- **Export path** *(Phase 3)* — compile frozen chains to JUCE projects or web apps with AudioWorklet runtime
- **Virtual audio routing** *(Phase 4, low priority)* — route preview to DAW/streaming apps via virtual cables

---

## Quick start

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20+ (studio UI only). [pnpm](https://pnpm.io/) optional — **npm works too**.

Optional: [just](https://github.com/casey/just) or use **make** / the raw commands below.

```bash
# Install Python deps
uv sync --all-packages --group dev

# Install studio UI (pick one)
cd apps/studio && npm install          # npm — no pnpm required
# pnpm install                         # from repo root, if you use pnpm

# Test
uv run pytest tests/ -q

# Run API + studio (two terminals)
uv run --package groovy-server groovy-server   # http://127.0.0.1:8188
cd apps/studio && npm run dev                  # http://127.0.0.1:5173
```

Install pnpm (optional): `corepack enable && corepack prepare pnpm@latest --activate`

Place audio under `workspace/assets/samples/` for LoadAudio nodes (see `templates/hello-groovy.groovy.json`).

---

## Documentation

Contributors and design docs: [docs/internal/README.md](docs/internal/README.md)

---

## License

Apache 2.0 for core, executor, and node SDK (planned). Individual node packs and model weights carry their own licenses, tracked per workflow chain.

---

## Contributing

The project is in pre-build planning. See [docs/internal/ENGINEERING.md](docs/internal/ENGINEERING.md) for monorepo layout and Phase 0 gates.
