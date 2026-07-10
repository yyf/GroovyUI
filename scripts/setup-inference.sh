#!/usr/bin/env bash
# Install optional real-inference packages for featured AI templates.
# basic-pitch is installed --no-deps to avoid tensorflow pins on Python 3.12+.
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --all-packages --group dev --group inference
uv pip install "basic-pitch==0.4.0" --no-deps
echo "Inference stack ready. Install models from Model Browser (Cmd+K): basic-pitch, musicgen-melody-small, demucs-v4"
