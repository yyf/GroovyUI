# GroovyUI

Node-graph studio for AI audio — patch models together, render sample-accurate previews, share workflows as JSON.

**Early preview.** Core graph + offline render works today; model registry and AI nodes are expanding.

## Quick start

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node 20+ for the UI.

```bash
uv sync --all-packages --group dev
cd apps/studio && npm install

uv run pytest tests/ -q

# Terminal 1 — API
uv run --package groovy-server groovy-server

# Terminal 2 — Studio
cd apps/studio && npm run dev
```

Open http://127.0.0.1:5173 — load a template, install a model (**Cmd+K**), **Render chain**.

Sample audio: `workspace/assets/samples/dialogue_48k.wav` (used by bundled templates).

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
