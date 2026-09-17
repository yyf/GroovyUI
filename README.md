# GroovyUI

Patch-bay for AI audio — patch models in a graph, render sample-accurate offline previews (cached PCM), share workflows as JSON.

## Quick start

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node 20+. Needs **two terminals** (API + Studio).

```bash
uv sync --all-packages --group dev
cd apps/studio && npm install

# Terminal 1 — API
uv run --package groovy-server groovy-server

# Terminal 2 — Studio
cd apps/studio && npm run dev
```

Open http://127.0.0.1:5173. Keep Settings → Inference on **Real** (Stub is for UI/CI only). Pick a featured template → **Cmd+K** → install required models → **Render** → audition the cached preview.

First model install can take minutes and gigabytes of disk; later renders reuse the local cache. Play is audition of the last render — not live inference.

## Portable (macOS arm64, experimental)

Download/build a self-contained folder (Python `.venv` + built studio + templates). No separate Vite process; the API serves the UI at the same origin.

```bash
# From a clone on Apple Silicon:
just package-portable
# → dist/portable/GroovyUI-portable-<version>-macos-arm64.zip
```

Unzip → double-click `GroovyUI.command` (or run `./bin/groovy-desktop`) → browser opens http://127.0.0.1:8188/. Models are not in the zip; Install on demand. Not codesigned/notarized yet.

## Verify

```bash
uv run pytest tests/ -q
cd apps/studio && npm test
uv run groovy-verify
```

With [just](https://github.com/casey/just): `just install`, `just test`, `just verify`, `just dev`.

## License

Apache 2.0 (planned for core packages). Third-party models and weights keep their own licenses.

## Request a model

In the studio Model Browser → **Discover**, use **File GitHub request** to open a prefilled public issue (no GroovyUI account; no secrets stored in the app). Maintainers triage first; Install stays off until a verified registry entry is merged. See [`.github/MODEL_REQUEST_PLAYBOOK.md`](.github/MODEL_REQUEST_PLAYBOOK.md).

Release notes: [CHANGELOG.md](CHANGELOG.md)
