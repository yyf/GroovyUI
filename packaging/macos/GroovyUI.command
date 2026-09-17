#!/bin/bash
# Double-click launcher for the portable GroovyUI folder (macOS).
# Opens Terminal briefly, starts the local API + studio, and opens your browser.

cd "$(dirname "$0")" || exit 1

if [[ ! -x ".venv/bin/groovy-desktop" ]]; then
  echo "Missing .venv/bin/groovy-desktop — re-download or re-run the package script."
  read -r -p "Press Enter to close…"
  exit 1
fi

export GROOVY_BUNDLE_ROOT="$(pwd)"
exec .venv/bin/groovy-desktop
