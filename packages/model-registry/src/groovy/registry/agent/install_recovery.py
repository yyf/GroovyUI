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
    explain = _explain_failure(base.get("summary") or "", base.get("error") or "", manifest)
    return {
        **base,
        "explain": explain,
        "suggested_fixes": fixes,
        "agent": "install_recovery_v1",
    }


def _explain_failure(summary: str, error: str, manifest: ModelManifest | None) -> str:
    bits = [summary.strip()] if summary.strip() else []
    if manifest:
        bits.append(
            f"{manifest.name} targets {', '.join(manifest.task_types[:2]) or 'audio'} "
            f"(~{manifest.vram_gb_estimate:g} GB VRAM)."
        )
        if manifest.install.dev_stub:
            bits.append("This entry is a stub install — retry after restarting the API if it still fails.")
    if error and error.strip() and error.strip() != summary.strip():
        bits.append("Open logs for the raw installer message.")
    return " ".join(bits)


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
    if "failed to install" in lowered or "pip install" in lowered:
        fixes.append("Retry install from Model Browser (Cmd+K).")
    if "inference runtime not ready" in lowered or "runtime not ready" in lowered or "not importable" in lowered:
        fixes.append("Reinstall from Model Browser (Cmd+K) to pull Python inference deps.")
    if not fixes:
        fixes.append("Retry install from Model Browser or run: groovy-model install <model-id>")
    if manifest and (manifest.similar_models or manifest.task_types):
        fixes.append("Or install a similar model from the list below (your choice — nothing auto-installs).")
    return fixes
