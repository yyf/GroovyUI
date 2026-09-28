# GroovyUI

**Open-source alpha.** Patch-bay for AI audio — wire models in a graph, render sample-accurate offline previews (cached PCM), share workflows as JSON.

Not a DAW: no timeline, no live low-latency engine. **Play** auditions the last render from cache; **Render** is explicit.

## Status

Experimental. APIs and UI will change. Expect rough edges on clean machines and first model installs. Hub, managed export, and notarized installers are out of scope for this alpha.

## Quick start

Requires **Python 3.11 or 3.12** (3.13+ often breaks model wheels like DeepFilterNet), [uv](https://docs.astral.sh/uv/), and Node 20+.

```bash
# One-time install
uv sync --all-packages --group dev
cd apps/studio && npm install && cd ../..

# Every session — API + studio + browser
./scripts/dev.sh
# or: just dev
```

Opens http://127.0.0.1:5173 (API on `:8188`). Ctrl+C stops both.

1. Settings → Inference → **Real** (Stub is for UI/CI only).
2. Pick a featured template (e.g. Hello Groovy or podcast denoise).
3. **Cmd+K** / **Ctrl+K** → install required models if prompted.
4. **Render** → play the cached preview.

First model install can take minutes and gigabytes of disk. Models keep their own licenses (see Compliance).

If `./scripts/dev.sh` says port 8188 is in use, quit the leftover API (`lsof -nP -iTCP:8188 -sTCP:LISTEN`) and retry.

```bash
uv run pytest tests/ -q && cd apps/studio && npm test && uv run groovy-verify
```

Or with [just](https://github.com/casey/just): `just install`, `just test`, `just verify`, `just dev`.

## License

[Apache License 2.0](LICENSE). Third-party models and weights keep their own SPDX licenses — the app license is not a grant to those weights.

Model requests: Model Browser → Discover → **File GitHub request**. See [`.github/MODEL_REQUEST_PLAYBOOK.md`](.github/MODEL_REQUEST_PLAYBOOK.md). Release notes: [CHANGELOG.md](CHANGELOG.md).
