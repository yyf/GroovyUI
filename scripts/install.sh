#!/usr/bin/env bash
# One-time install: Python 3.11 venv + workspace sync + Studio UI deps.
# Usage (from repo root): ./scripts/install.sh
# Optional: ./scripts/install.sh --inference   # also pull AI inference extras
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

WITH_INFERENCE=0
for arg in "$@"; do
  case "$arg" in
    --inference) WITH_INFERENCE=1 ;;
    -h|--help)
      echo "Usage: ./scripts/install.sh [--inference]"
      echo "  One-time GroovyUI install (venv + sync + Studio npm/pnpm)."
      echo "  --inference  also sync the optional AI inference dependency group"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (try --help)" >&2
      exit 1
      ;;
  esac
done

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required tool: $1" >&2
    echo "$2" >&2
    exit 1
  fi
}

need uv "Install uv: https://docs.astral.sh/uv/ (curl -LsSf https://astral.sh/uv/install.sh | sh)"

if ! command -v node >/dev/null 2>&1 && ! command -v pnpm >/dev/null 2>&1; then
  echo "Missing Node.js 20+ (needed for the Studio UI)." >&2
  echo "Install Node: https://nodejs.org/  (or enable pnpm after Node is installed)" >&2
  exit 1
fi

if [[ -d .venv ]]; then
  PY_VER="$("$ROOT/.venv/bin/python" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || true)"
  if [[ -n "${PY_VER}" ]]; then
    MAJOR="${PY_VER%%.*}"
    MINOR="${PY_VER#*.}"
    if [[ "${MAJOR}" -gt 3 ]] || { [[ "${MAJOR}" -eq 3 ]] && [[ "${MINOR}" -ge 12 ]]; }; then
      echo "Existing .venv is Python ${PY_VER}; recreating with 3.11 (DeepFilterNet wheels)."
      rm -rf .venv
    fi
  fi
fi

echo "==> Python 3.11 venv"
if [[ ! -d .venv ]]; then
  uv venv --python 3.11
fi

echo "==> Sync workspace packages"
SYNC_ARGS=(sync --all-packages --group dev)
if [[ "${WITH_INFERENCE}" -eq 1 ]]; then
  SYNC_ARGS+=(--group inference)
fi
uv "${SYNC_ARGS[@]}"

if [[ "${WITH_INFERENCE}" -eq 1 ]]; then
  # basic-pitch: --no-deps avoids tensorflow pins on Python 3.12+ (we stay on 3.11).
  uv pip install "basic-pitch==0.4.0" --no-deps
fi

echo "==> Studio UI deps"
if command -v pnpm >/dev/null 2>&1 && [[ -f pnpm-lock.yaml ]]; then
  pnpm install
elif [[ -f apps/studio/package.json ]]; then
  (cd apps/studio && npm install)
else
  echo "No Studio package.json found under apps/studio/" >&2
  exit 1
fi

echo
echo "Install complete."
if [[ "${WITH_INFERENCE}" -eq 1 ]]; then
  echo "Inference extras ready. Install models from Model Browser (Cmd+K) as needed."
fi
echo "Start a session:  ./scripts/dev.sh"
echo "Studio: http://127.0.0.1:5173   API: http://127.0.0.1:8188"
