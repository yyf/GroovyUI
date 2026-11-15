#!/usr/bin/env bash
# Setup LTX-2.3 Q4 MLX for GroovyUI GenerateVideo on Apple Silicon (M1 Max 32 GB class).
# Usage:
#   bash scripts/setup-ltx-mac.sh --free-disk   # reclaim HF caches (~20+ GB)
#   bash scripts/setup-ltx-mac.sh              # install CLI deps + download distilled pack + smoke test
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HF_HUB="${HOME}/.cache/huggingface/hub"
MODEL_DIR="${GROOVY_LTX_MLX_ROOT:-$ROOT/workspace/.groovy/models/ltx-2.3-q4}"

free_disk() {
  echo "==> Freeing large unused Hugging Face caches (keeps Runware ACE 2B / Kokoro / etc.)"
  local targets=(
    "models--ACE-Step--acestep-v15-xl-sft-diffusers"
    "models--ACE-Step--acestep-v15-xl-turbo-diffusers"
    "models--stabilityai--stable-audio-open-1.0"
    "models--facebook--seamless-m4t-v2-large"
  )
  for name in "${targets[@]}"; do
    path="${HF_HUB}/${name}"
    if [[ -d "$path" ]]; then
      du -sh "$path" || true
      rm -rf "$path"
      echo "    removed $path"
    else
      echo "    skip (missing): $path"
    fi
  done
  df -h "$HOME" | tail -1
  echo "==> Need ≥30 GB free before downloading LTX-2.3 Q4 distilled (+ Gemma TE)."
}

install_cli() {
  echo "==> Installing ltx-2-mlx packages into project venv"
  if [[ ! -x .venv/bin/python ]]; then
    echo "Missing .venv — run: uv venv --python 3.11 && uv sync --all-packages --group dev" >&2
    exit 1
  fi
  uv pip install --python .venv/bin/python \
    "mlx>=0.22" \
    "huggingface_hub>=0.20" \
    "safetensors>=0.4" \
    "numpy" \
    "pillow" \
    "imageio[ffmpeg]" \
    "ltx-core-mlx @ git+https://github.com/dgrauet/ltx-2-mlx.git#subdirectory=packages/ltx-core-mlx" \
    "ltx-pipelines-mlx @ git+https://github.com/dgrauet/ltx-2-mlx.git#subdirectory=packages/ltx-pipelines-mlx"
}

download_pack() {
  echo "==> Downloading distilled-only LTX-2.3 Q4 → ${MODEL_DIR}"
  mkdir -p "$(dirname "$MODEL_DIR")"
  export GROOVY_LTX_MLX_ROOT="$MODEL_DIR"
  export GROOVY_PROJECT_DIR="${GROOVY_PROJECT_DIR:-$ROOT/workspace}"
  uv run python -c "from groovy.nodes.ai.backends.ltx_mlx_runner import ensure_weights; print(ensure_weights())"
}

smoke_test() {
  echo "==> Smoke test: 512×512, ~1.4 s (33 frames), --low-ram"
  export GROOVY_LTX_MLX_ROOT="$MODEL_DIR"
  OUT="${TMPDIR:-/tmp}/groovy-ltx-smoke.mp4"
  uv run python -c "
from pathlib import Path
from groovy.nodes.ai.backends.ltx_mlx_runner import generate_mp4
out = generate_mp4(
    'a calm ocean at sunset, gentle waves',
    dest=Path('${OUT}'),
    duration=1.4,
    width=512,
    height=512,
    seed=7,
    low_ram=True,
)
print('wrote', out, 'bytes', out.stat().st_size)
"
}

case "${1:-}" in
  --free-disk)
    free_disk
    ;;
  --download-only)
    download_pack
    ;;
  --smoke)
    smoke_test
    ;;
  *)
    free_disk
    install_cli
    download_pack
    smoke_test
    echo "==> Done. In studio: install/select model ltx-2.3-q4 on GenerateVideo, Inference=Real, Render."
    ;;
esac
