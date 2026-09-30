from __future__ import annotations

import json
import sys
from pathlib import Path

from groovy.nodes.ai import register_all as register_ai
from groovy.nodes.core import register_all as register_core
from groovy.node import NODE_REGISTRY
from groovy.schema.models import Workflow
from groovy.schema.validate import validate_workflow

register_core()
register_ai()

ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = ROOT / "templates"
DEV_TEMPLATES = ROOT / "docs" / "internal" / "templates"


def _template_dirs() -> list[Path]:
    dirs: list[Path] = []
    if TEMPLATES.is_dir():
        dirs.append(TEMPLATES)
    if DEV_TEMPLATES.is_dir():
        dirs.append(DEV_TEMPLATES)
    return dirs


def main() -> int:
    errors: list[str] = []
    paths: list[Path] = []
    for directory in _template_dirs():
        paths.extend(sorted(directory.glob("*.groovy.json")))
    for path in paths:
        try:
            workflow = Workflow.model_validate(json.loads(path.read_text()))
            result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
            if not result.valid:
                errors.append(f"{path.name}: {[e.message for e in result.errors]}")
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    print(f"verify ok: {len(paths)} templates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
