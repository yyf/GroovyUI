from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from typing import Any


def probe_machine(project_dir: Path) -> dict[str, Any]:
    """Best-effort host capacity snapshot for preflight (never raises)."""
    groovy_root = project_dir.resolve() / ".groovy"
    groovy_root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(groovy_root)
    disk_free_mb = round(usage.free / (1024 * 1024), 1)
    models_dir = groovy_root / "models"
    models_used_mb = round(_directory_size_bytes(models_dir) / (1024 * 1024), 1)

    ram_available_gb: float | None = None
    try:
        import psutil

        ram_available_gb = round(psutil.virtual_memory().available / (1024**3), 1)
    except Exception:
        ram_available_gb = None

    vram_available_gb: float | None = None
    vram_source = "unknown"
    torch_cuda_available = False
    try:
        import torch

        torch_cuda_available = bool(torch.cuda.is_available())
        if torch_cuda_available:
            props = torch.cuda.get_device_properties(0)
            free_bytes, _total = torch.cuda.mem_get_info(0)
            vram_available_gb = round(free_bytes / (1024**3), 1)
            vram_source = f"cuda:{props.name}"
    except Exception:
        pass

    return {
        "disk_free_mb": disk_free_mb,
        "disk_path": str(groovy_root),
        "models_dir": str(models_dir),
        "models_used_mb": models_used_mb,
        "ram_available_gb": ram_available_gb,
        "vram_available_gb": vram_available_gb,
        "vram_source": vram_source,
        "torch_cuda_available": torch_cuda_available,
        "python_executable": sys.executable,
        "uv_available": shutil.which("uv") is not None,
    }


def _directory_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                continue
    return total


def build_machine_checks(
    *,
    known_download_mb: float,
    peak_vram_gb: float,
    machine: dict[str, Any],
    missing_verify_imports: list[str],
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    disk_free = float(machine.get("disk_free_mb") or 0)
    # Pip wheels + unpack room; keep a floor so tiny installs still leave headroom.
    needed_mb = max(known_download_mb * 1.25 + 512.0, known_download_mb + 256.0)
    if known_download_mb <= 0:
        checks.append(
            {
                "code": "DISK_OK",
                "severity": "ok",
                "message": f"{disk_free:.0f} MB free on project cache volume.",
            }
        )
    elif disk_free < needed_mb:
        checks.append(
            {
                "code": "DISK_SHORT",
                "severity": "error",
                "message": (
                    f"Only {disk_free:.0f} MB free; need about {needed_mb:.0f} MB "
                    f"for ~{known_download_mb:.0f} MB of model downloads."
                ),
            }
        )
    else:
        checks.append(
            {
                "code": "DISK_OK",
                "severity": "ok",
                "message": (
                    f"{disk_free:.0f} MB free for ~{known_download_mb:.0f} MB download "
                    f"(~{needed_mb:.0f} MB recommended)."
                ),
            }
        )

    vram_available = machine.get("vram_available_gb")
    if peak_vram_gb <= 0:
        checks.append(
            {
                "code": "VRAM_OK",
                "severity": "ok",
                "message": "No meaningful GPU VRAM estimate for this chain.",
            }
        )
    elif vram_available is None:
        checks.append(
            {
                "code": "VRAM_UNKNOWN",
                "severity": "warning",
                "message": (
                    f"Peak model VRAM ~{peak_vram_gb} GB — host GPU memory "
                    "could not be measured; CPU fallback may be slow."
                ),
            }
        )
    elif float(vram_available) + 0.25 < peak_vram_gb:
        checks.append(
            {
                "code": "VRAM_TIGHT",
                "severity": "warning",
                "message": (
                    f"Peak model VRAM ~{peak_vram_gb} GB exceeds measured "
                    f"{float(vram_available):.1f} GB free; expect CPU or OOM risk."
                ),
            }
        )
    else:
        checks.append(
            {
                "code": "VRAM_OK",
                "severity": "ok",
                "message": (
                    f"Peak ~{peak_vram_gb} GB within measured "
                    f"{float(vram_available):.1f} GB free ({machine.get('vram_source')})."
                ),
            }
        )

    if not machine.get("uv_available") and missing_verify_imports:
        checks.append(
            {
                "code": "RUNTIME_NO_UV",
                "severity": "warning",
                "message": "uv not found on PATH — dependency installs may fall back to pip.",
            }
        )
    elif missing_verify_imports:
        joined = ", ".join(missing_verify_imports[:6])
        more = "" if len(missing_verify_imports) <= 6 else "…"
        checks.append(
            {
                "code": "RUNTIME_NEEDS_INSTALL",
                "severity": "warning",
                "message": (
                    f"Missing inference imports will install with the model: {joined}{more}."
                ),
            }
        )
    else:
        checks.append(
            {
                "code": "RUNTIME_READY",
                "severity": "ok",
                "message": "Required inference imports already available or no verify list.",
            }
        )

    return checks


def missing_verify_imports_for_models(manifests: list[Any]) -> list[str]:
    missing: list[str] = []
    seen: set[str] = set()
    for manifest in manifests:
        for module in getattr(getattr(manifest, "install", None), "verify_imports", []) or []:
            name = str(module)
            if name in seen:
                continue
            seen.add(name)
            try:
                available = importlib.util.find_spec(name) is not None
            except Exception:
                # Broken or partially installed packages can raise while resolving.
                available = False
            if not available:
                missing.append(name)
    return missing
