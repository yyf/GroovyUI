# GroovyUI

Node-graph studio for AI audio — patch models together, render sample-accurate previews, share workflows as JSON.

**v0.18.0** — Phases 0–2 + 2.5 complete (modular synth, multichannel/OBA, live MIDI bridge). **Phase 2.6 signal integrity** is next, then Phase 3 export.

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

Open http://127.0.0.1:5173 — load a template (22 bundled), install a model (**Cmd+K**), **Render chain**.

Sample audio: `workspace/assets/samples/male-1.wav` and `dialogue_48k.wav` (used by bundled templates).

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
