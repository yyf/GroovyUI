#!/usr/bin/env bash
# Build a portable macOS arm64 folder + zip under dist/portable/.
# Usage: ./scripts/package_portable_macos.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script only packages on macOS (Darwin)." >&2
  exit 1
fi
if [[ "$(uname -m)" != "arm64" ]]; then
  echo "Warning: host is $(uname -m); artifact targets Apple Silicon (macos-arm64)." >&2
fi

VERSION="$(
  python3 - <<'PY'
from pathlib import Path
import re
text = Path("server/pyproject.toml").read_text()
m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
print(m.group(1) if m else "0.0.0")
PY
)"

OUT_NAME="GroovyUI-portable-${VERSION}-macos-arm64"
OUT_DIR="${ROOT}/dist/portable/${OUT_NAME}"
ZIP_PATH="${ROOT}/dist/portable/${OUT_NAME}.zip"

echo "==> Cleaning ${OUT_DIR}"
rm -rf "${OUT_DIR}"
mkdir -p "${OUT_DIR}/studio" "${OUT_DIR}/templates" "${OUT_DIR}/assets/samples" "${OUT_DIR}/workspace" "${OUT_DIR}/bin"

echo "==> Building studio (same-origin API)"
(
  cd apps/studio
  VITE_GROOVY_API= npm run build
)
cp -R apps/studio/dist/. "${OUT_DIR}/studio/"

echo "==> Copying templates + allowlisted samples"
cp -R templates/. "${OUT_DIR}/templates/"
shopt -s nullglob
for f in assets/samples/*.{wav,flac,mid,midi,mp3,m4a,mp4}; do
  cp "$f" "${OUT_DIR}/assets/samples/"
done
shopt -u nullglob
if [[ -f assets/samples/README.md ]]; then
  cp assets/samples/README.md "${OUT_DIR}/assets/samples/"
fi

echo "==> Creating portable .venv (non-editable workspace install)"
uv venv "${OUT_DIR}/.venv"
# Copy packages into site-packages so the zip does not depend on the monorepo tree.
UV_PROJECT_ENVIRONMENT="${OUT_DIR}/.venv" uv sync \
  --package groovy-server \
  --no-dev \
  --no-editable

cp packaging/macos/GroovyUI.command "${OUT_DIR}/GroovyUI.command"
chmod +x "${OUT_DIR}/GroovyUI.command"

cat > "${OUT_DIR}/bin/groovy-desktop" <<'EOF'
#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export GROOVY_BUNDLE_ROOT="$ROOT"
exec "$ROOT/.venv/bin/groovy-desktop" "$@"
EOF
chmod +x "${OUT_DIR}/bin/groovy-desktop"

cat > "${OUT_DIR}/README.txt" <<EOF
GroovyUI portable (${VERSION}, macOS arm64) — experimental

1. Unzip this folder anywhere (keep the whole directory together).
2. Double-click GroovyUI.command (or run: ./bin/groovy-desktop).
3. Your browser opens http://127.0.0.1:8188/ — local API + studio (same origin).
4. Pick Hello Groovy → Render → Play the cached preview.

Notes:
- Models are not bundled; Install downloads into your local project/cache.
- Workspace defaults to this folder's workspace/ directory.
- Quit with Ctrl+C in the Terminal window that the launcher opens.
- Requires Apple Silicon (arm64). Not codesigned/notarized yet.
- Artifact size is large because the Python runtime + dependencies ship inside .venv/.

See the project README for source and development setup.
EOF

if [[ ! -x "${OUT_DIR}/.venv/bin/groovy-desktop" ]]; then
  echo "ERROR: .venv/bin/groovy-desktop missing after uv sync" >&2
  ls -la "${OUT_DIR}/.venv/bin" >&2 || true
  exit 1
fi

echo "==> Zipping ${ZIP_PATH}"
mkdir -p "$(dirname "${ZIP_PATH}")"
rm -f "${ZIP_PATH}"
(
  cd "${ROOT}/dist/portable"
  zip -qy -r "${OUT_NAME}.zip" "${OUT_NAME}"
)

echo "Done: ${ZIP_PATH}"
du -sh "${OUT_DIR}" "${ZIP_PATH}" || true
