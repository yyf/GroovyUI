from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from groovy.registry.catalog import ModelCatalog
from groovy.registry.store import InstallStore


def scan_registry_freshness(catalog: ModelCatalog, store: InstallStore) -> dict[str, Any]:
    flags: list[dict[str, Any]] = []
    for manifest in catalog.all():
        state = store.get(manifest.id)
        if manifest.status == "planned":
            flags.append(
                {
                    "model_id": manifest.id,
                    "severity": "info",
                    "code": "PLANNED_MODEL",
                    "message": f"{manifest.name} is planned — weights not published yet.",
                }
            )
            continue
        if state.status == "failed":
            flags.append(
                {
                    "model_id": manifest.id,
                    "severity": "warning",
                    "code": "INSTALL_FAILED",
                    "message": state.error or "Install failed",
                }
            )
        elif state.status == "not_installed" and manifest.status == "published":
            flags.append(
                {
                    "model_id": manifest.id,
                    "severity": "info",
                    "code": "NOT_INSTALLED",
                    "message": f"{manifest.name} is published but not installed locally.",
                }
            )
    stale = [flag for flag in flags if flag["severity"] in {"warning", "error"}]
    return {
        "scanned_at": datetime.now(UTC).isoformat(),
        "model_count": len(catalog.all()),
        "flag_count": len(flags),
        "stale_count": len(stale),
        "flags": flags,
        "agent": "registry_freshness",
        "ok": len(stale) == 0,
    }
