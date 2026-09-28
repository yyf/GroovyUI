#!/usr/bin/env bash
# One-shot local launch: API (:8188) + Vite studio (:5173) + open browser.
# Usage (from repo root, after install): ./scripts/dev.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API_HOST="${GROOVY_HOST:-127.0.0.1}"
API_PORT="${GROOVY_PORT:-8188}"
STUDIO_URL="${GROOVY_STUDIO_URL:-http://127.0.0.1:5173}"
API_PID=""
STUDIO_PID=""

cleanup() {
  trap - EXIT INT TERM
  if [[ -n "${STUDIO_PID}" ]] && kill -0 "${STUDIO_PID}" 2>/dev/null; then
    kill "${STUDIO_PID}" 2>/dev/null || true
  fi
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install: https://docs.astral.sh/uv/" >&2
  exit 1
fi
if [[ ! -d .venv ]]; then
  echo "Missing .venv. First run:" >&2
  echo "  uv venv --python 3.11 && uv sync --all-packages --group dev" >&2
  echo "  cd apps/studio && npm install" >&2
  exit 1
fi

PY_VER="$("$ROOT/.venv/bin/python" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || true)"
if [[ -n "${PY_VER}" ]]; then
  MAJOR="${PY_VER%%.*}"
  MINOR="${PY_VER#*.}"
  if [[ "${MAJOR}" -gt 3 ]] || { [[ "${MAJOR}" -eq 3 ]] && [[ "${MINOR}" -ge 12 ]]; }; then
    echo "Warning: .venv is Python ${PY_VER}. Podcast denoise (DeepFilterNet) needs 3.11" >&2
    echo "  (deepfilterlib has no 3.12+ wheel). Recreate with:" >&2
    echo "  rm -rf .venv && uv venv --python 3.11 && uv sync --all-packages --group dev" >&2
  fi
fi
if [[ ! -d apps/studio/node_modules ]] && ! command -v pnpm >/dev/null 2>&1; then
  echo "Studio deps missing. First run: cd apps/studio && npm install" >&2
  exit 1
fi

if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"${API_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port ${API_PORT} is already in use." >&2
    echo "Quit the other GroovyUI/API process (lsof -nP -iTCP:${API_PORT} -sTCP:LISTEN), then retry." >&2
    exit 1
  fi
fi

echo "Starting API  http://${API_HOST}:${API_PORT}"
uv run --package groovy-server groovy-server &
API_PID=$!

echo "Starting studio ${STUDIO_URL}"
if [[ -d apps/studio/node_modules ]]; then
  (cd apps/studio && npm run dev -- --host 127.0.0.1 --port 5173) &
  STUDIO_PID=$!
else
  pnpm dev:studio &
  STUDIO_PID=$!
fi

echo -n "Waiting for API"
for _ in $(seq 1 80); do
  if curl -sf "http://${API_HOST}:${API_PORT}/api/health" >/dev/null 2>&1; then
    echo " — ready"
    break
  fi
  if ! kill -0 "${API_PID}" 2>/dev/null; then
    echo
    echo "API exited early. Check the log above (port in use is common)." >&2
    exit 1
  fi
  echo -n "."
  sleep 0.25
done
if ! curl -sf "http://${API_HOST}:${API_PORT}/api/health" >/dev/null 2>&1; then
  echo
  echo "API did not become healthy on http://${API_HOST}:${API_PORT}/api/health" >&2
  exit 1
fi

echo -n "Waiting for studio"
for _ in $(seq 1 80); do
  if curl -sf "${STUDIO_URL}" >/dev/null 2>&1; then
    echo " — ready"
    break
  fi
  echo -n "."
  sleep 0.25
done

echo "Opening ${STUDIO_URL}"
if [[ "${GROOVY_NO_BROWSER:-}" != "1" ]]; then
  if command -v open >/dev/null 2>&1; then
    open "${STUDIO_URL}"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${STUDIO_URL}" >/dev/null 2>&1 || true
  fi
fi

echo "GroovyUI running. Ctrl+C stops API + studio."
wait
