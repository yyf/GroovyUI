# GroovyUI

Patch-bay for AI audio — patch models in a graph, render sample-accurate offline previews (cached PCM), share workflows as JSON.

## Quick start

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node 20+.

```bash
uv sync --all-packages --group dev
cd apps/studio && npm install

# Terminal 1 — API
uv run --package groovy-server groovy-server

# Terminal 2 — Studio
cd apps/studio && npm run dev
```

Open http://127.0.0.1:5173. Settings → Inference on **Real** (Stub is for UI/CI). Featured template → **Cmd+K** → install models → **Render** → play the cached preview.

Play auditions the last render — not live inference. First model install can take minutes and gigabytes of disk.

```bash
uv run pytest tests/ -q && cd apps/studio && npm test && uv run groovy-verify
```

Or with [just](https://github.com/casey/just): `just install`, `just test`, `just verify`, `just dev`.

## License

Apache 2.0 (planned for core packages). Third-party models and weights keep their own licenses.

Model requests: Model Browser → Discover → **File GitHub request**. See [`.github/MODEL_REQUEST_PLAYBOOK.md`](.github/MODEL_REQUEST_PLAYBOOK.md). Release notes: [CHANGELOG.md](CHANGELOG.md).
