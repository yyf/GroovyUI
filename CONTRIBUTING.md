# Contributing to GroovyUI

Thanks for helping improve the patch-bay for AI audio. This project is **Apache 2.0** for in-repo code; model weights keep their own licenses.

## Before you open a PR

1. **Python 3.11** — `uv venv --python 3.11 && uv sync --all-packages --group dev`
2. **Studio** — `cd apps/studio && npm install`
3. **Tests** (from repo root):

```bash
uv run pytest tests/ -q
uv run groovy-verify
cd apps/studio && npm test && npm run lint
```

CI runs with `GROOVY_INFERENCE_STUB=1`. For audio-facing changes, smoke **Real** inference locally when you can.

## Dev session

```bash
./scripts/dev.sh
```

API on `:8188`, Vite studio on `:5173`.

## Crowdsourced catalog requests (no PR required)

Users can file GitHub issues from Studio (browser deep link — no token in the app):

| Template | Studio entry |
|----------|----------------|
| [Model request](.github/ISSUE_TEMPLATE/model_request.yml) | Model Browser → Discover / unknown model → **File GitHub request** |
| [Blueprint request](.github/ISSUE_TEMPLATE/blueprint_request.yml) | Patch Generation → **Blueprint request** |
| [Node request](.github/ISSUE_TEMPLATE/node_request.yml) | Patch Generation (missing types) → **Node request** |

Maintainer playbooks: [MODEL_REQUEST_PLAYBOOK.md](.github/MODEL_REQUEST_PLAYBOOK.md), [BLUEPRINT_REQUEST_PLAYBOOK.md](.github/BLUEPRINT_REQUEST_PLAYBOOK.md).

Forks can set `VITE_GROOVY_GITHUB_REPO=owner/repo` when building studio so issue links target your fork.

## What not to commit

- `docs/internal/` (local planning only — gitignored)
- `.groovy/`, `.env`, `.secrets/`, `studio_settings.json`, tokens, or absolute paths with credentials
- Broad `git add .` without checking the above

See [SECURITY.md](SECURITY.md).

## Code style

- Match surrounding modules; smallest PR that solves one problem.
- New registry entries: follow `tests/test_seed_catalog_quality.py` and the model request playbook.
- **Patch-bay, not a DAW** — offline render + cached audition; avoid live-engine scope creep in studio PRs.

## Questions

Use GitHub Issues for bugs and feature discussion. Prefer the request templates when asking for new verified models, nodes, or templates.
