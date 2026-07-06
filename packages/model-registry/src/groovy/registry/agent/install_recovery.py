"""Install recovery agent — deterministic suggestions for failed model installs."""

from __future__ import annotations

from typing import Any

from groovy.registry.catalog import ModelCatalog
from groovy.registry.installer import ModelInstaller
from groovy.registry.models import ModelManifest
from groovy.registry.store import InstallStore


def install_recovery(
    catalog: ModelCatalog,
    store: InstallStore,
    installer: ModelInstaller,
    model_id: str,
) -> dict[str, Any]:
    base = installer.recovery_suggestions(model_id)
    manifest = catalog.get(model_id)
    fixes = _suggested_fixes(base.get("error") or "", manifest)
    return {
        **base,
        "suggested_fixes": fixes,
        "agent": "install_recovery_v1",
    }


def _suggested_fixes(error: str, manifest: ModelManifest | None) -> list[str]:
    lowered = error.lower()
    fixes: list[str] = []
    if "checksum" in lowered:
        fixes.append("Delete partial weights and retry install.")
    if "disk" in lowered or "space" in lowered:
        fixes.append("Free disk space under ~/.groovy/models and retry.")
    if "network" in lowered or "connection" in lowered:
        fixes.append("Check network connectivity and retry install.")
    if "cuda" in lowered or "gpu" in lowered:
        fixes.append("Try a CPU-compatible model from the similar list below.")
    if manifest and manifest.install.dev_stub:
        fixes.append("Dev stub install should succeed — restart the API server and retry.")
    if not fixes:
        fixes.append("Retry install from Model Browser or run: groovy-model install <model-id>")
    return fixes


def _card(manifest: ModelManifest, state) -> dict[str, Any]:
    return {
        "id": manifest.id,
        "name": manifest.name,
        "task_types": manifest.task_types,
        "license": manifest.license.model_dump(),
        "vram_gb_estimate": manifest.vram_gb_estimate,
        "install_status": state.status,
    }
