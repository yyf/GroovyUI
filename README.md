# GroovyUI

Patch-bay for AI audio — patch models in a graph, render sample-accurate previews, share workflows as JSON.

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

Open http://127.0.0.1:5173 — pick a template, install models (**Cmd+K**), **Render chain**, audition from cache.

## Verify

```bash
uv run pytest tests/ -q
cd apps/studio && npm test
uv run groovy-verify
```

With [just](https://github.com/casey/just): `just install`, `just test`, `just verify`, `just dev`.

## License

Apache 2.0 (planned for core packages). Third-party models and weights keep their own licenses.

Release notes: [CHANGELOG.md](CHANGELOG.md)
