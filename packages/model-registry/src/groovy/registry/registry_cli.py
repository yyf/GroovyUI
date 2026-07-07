from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from groovy.registry.agent.curator import approve_draft, ingest_drafts, list_drafts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="groovy-registry", description="GroovyUI registry curator CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Ingest curated hints as draft model entries")
    ingest.add_argument(
        "--project",
        default=os.environ.get("GROOVY_PROJECT_DIR", "workspace"),
        help="Project directory",
    )
    ingest.add_argument("--force", action="store_true", help="Overwrite existing drafts")

    drafts = sub.add_parser("drafts", help="List draft model entries")
    drafts.add_argument(
        "--project",
        default=os.environ.get("GROOVY_PROJECT_DIR", "workspace"),
        help="Project directory",
    )

    approve = sub.add_parser("approve", help="Approve a draft into the project catalog overlay")
    approve.add_argument("model_id", help="Draft model id")
    approve.add_argument(
        "--project",
        default=os.environ.get("GROOVY_PROJECT_DIR", "workspace"),
        help="Project directory",
    )

    args = parser.parse_args(argv)
    project_dir = Path(args.project).resolve()
    draft_dir = project_dir / ".groovy" / "registry" / "drafts"
    overlay_path = project_dir / ".groovy" / "registry" / "catalog_overlay.json"

    if args.command == "ingest":
        result = ingest_drafts(draft_dir, skip_existing=not args.force)
        print(f"ingest ok: created={len(result['created'])} skipped={len(result['skipped'])}")
        for model_id in result["created"]:
            print(f"  + {model_id}")
        return 0

    if args.command == "drafts":
        items = list_drafts(draft_dir)
        if not items:
            print("No drafts.")
            return 0
        for item in items:
            print(f"{item['id']}\tdraft\t{item.get('name', item['id'])}")
        return 0

    if args.command == "approve":
        try:
            manifest = approve_draft(draft_dir, overlay_path, args.model_id)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"approved: {manifest.id} → {overlay_path}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
