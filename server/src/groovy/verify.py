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


def main() -> int:
    errors: list[str] = []
    for path in sorted(TEMPLATES.glob("*.groovy.json")):
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

    print(f"verify ok: {len(list(TEMPLATES.glob('*.groovy.json')))} templates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
