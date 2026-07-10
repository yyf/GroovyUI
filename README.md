# GroovyUI

Node-graph studio for AI audio — patch models together, render sample-accurate previews, share workflows as JSON.

**v0.19.0** — Phase 2.6 complete. Phase 3 export is next.

## Quick start

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node 20+ for the UI.

```bash
uv sync --all-packages --group dev
cd apps/studio && npm install   # or: pnpm install from repo root

uv run pytest tests/ -q
cd apps/studio && npm test      # workflow graph unit tests

# Terminal 1 — API
uv run --package groovy-server groovy-server

# Terminal 2 — Studio
cd apps/studio && npm run dev
```

Open http://127.0.0.1:5173 — default template **Transcribe and Regenerate** (modular AI patch demo). Install models (**Cmd+K**), **Render chain**.

### Real AI inference (featured templates)

**Transcribe and Regenerate** (Basic Pitch + MusicGen Melody) and **Stem Split Vocals** (Demucs) use real offline inference:

```bash
./scripts/setup-inference.sh
```

Then in the studio, install models from **Model Browser** (Cmd+K): `basic-pitch`, `musicgen-melody-small`, `demucs-v4`. First run may download weights from Hugging Face / Meta (needs `torch`, `torchaudio`, `transformers`, `demucs`).

CI uses `GROOVY_INFERENCE_STUB=1` so tests stay fast without GPU weights.

Sample audio: bundled in `assets/samples/` (auto-copied into `workspace/assets/samples/` on server start).

With [just](https://github.com/casey/just): `just install`, `just test`, `just verify`, `just dev`.

## Repo layout

```
apps/studio/          React graph UI
server/               FastAPI host
packages/             schema, executor, node SDK, model registry
nodes/core|ai/        built-in nodes
templates/            starter workflows (*.groovy.json)
```

## License

Apache 2.0 (planned for core packages). Third-party models and weights keep their own licenses.
