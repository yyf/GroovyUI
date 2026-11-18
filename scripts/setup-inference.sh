#!/usr/bin/env bash
# Optional AI inference extras (wrapper). Prefer: ./scripts/install.sh --inference
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/install.sh" --inference
