from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from groovy.registry.pack_installer import PackInstaller
from groovy.registry.packs import list_packs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="groovy-install", description="GroovyUI community pack installer")
    sub = parser.add_subparsers(dest="command", required=True)

    pack_cmd = sub.add_parser("pack", help="Install a community node pack by id")
    pack_cmd.add_argument("pack_id", help="Pack registry id")
    pack_cmd.add_argument(
        "--project",
        default=os.environ.get("GROOVY_PROJECT_DIR", "workspace"),
        help="Project directory",
    )
    pack_cmd.add_argument("--yes", action="store_true", help="Skip interactive consent")

    list_cmd = sub.add_parser("list", help="List available community packs")
    list_cmd.add_argument(
        "--project",
        default=os.environ.get("GROOVY_PROJECT_DIR", "workspace"),
        help="Project directory",
    )

    args = parser.parse_args(argv)
    project_dir = Path(args.project).resolve()
    installer = PackInstaller(project_dir)

    if args.command == "list":
        for pack in list_packs():
            state = installer.get_state(pack.id)
            status = state.status if state else "not_installed"
            print(f"{pack.id}\t{status}\t{pack.name} ({pack.trust_tier})")
        return 0

    if args.command == "pack":
        if not args.yes:
            print(
                f"Community pack '{args.pack_id}' installs metadata to your project (.groovy/packs). "
                "Third-party packs may execute code when nodes ship — review manifest first.",
                file=sys.stderr,
            )
        state = installer.install(args.pack_id, consent=True)
        print(f"{args.pack_id}: {state.status}")
        if state.error:
            print(state.error, file=sys.stderr)
            return 1
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
