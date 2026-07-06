from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="groovy-model", description="GroovyUI model registry CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install", help="Install a model by registry id")
    install.add_argument("model_id", help="Model registry id")
    install.add_argument(
        "--project",
        default=os.environ.get("GROOVY_PROJECT_DIR", "workspace"),
        help="Project directory (default: workspace or GROOVY_PROJECT_DIR)",
    )

    list_cmd = sub.add_parser("list", help="List published models")
    list_cmd.add_argument("--query", default="", help="Optional search query")

    args = parser.parse_args(argv)
    project_dir = Path(args.project).resolve()

    from groovy.registry import ModelRegistry

    registry = ModelRegistry(project_dir)

    if args.command == "install":
        manifest = registry.catalog.get(args.model_id)
        if not manifest:
            print(f"Unknown model: {args.model_id}", file=sys.stderr)
            return 1
        state = registry.installer.install(args.model_id)
        print(f"{args.model_id}: {state.status}")
        if state.error:
            print(state.error, file=sys.stderr)
            return 1
        return 0

    if args.command == "list":
        matches = registry.catalog.search(args.query) if args.query else registry.catalog.all()
        for model in matches:
            status = registry.store.get(model.id).status
            print(f"{model.id}\t{status}\t{model.name}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
