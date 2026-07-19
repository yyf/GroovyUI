from __future__ import annotations

from pydantic import BaseModel, Field


class LicenseInfo(BaseModel):
    spdx: str
    commercial_ok: bool = False
    attribution_required: bool = False
    confidence: float = 1.0


class InstallSpec(BaseModel):
    weights: list[dict] = Field(default_factory=list)
    python_deps: list[dict] = Field(default_factory=list)
    verify_imports: list[str] = Field(default_factory=list)
    install_script: str | None = None
    dev_stub: bool = False


class InferenceParam(BaseModel):
    name: str
    type: str = "FLOAT"
    default: str | int | float | bool | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    description: str = ""


class ModelManifest(BaseModel):
    id: str
    status: str = "published"
    trust: str = "verified"
    name: str
    description: str
    task_types: list[str]
    tags: list[str] = Field(default_factory=list)
    author: str = ""
    license: LicenseInfo
    vram_gb_estimate: float = 0
    # Curated, approximate transfer size for model-specific assets/dependencies.
    # None means the catalog cannot estimate without network access.
    download_size_mb_estimate: float | None = None
    compatible_nodes: list[str] = Field(default_factory=list)
    install: InstallSpec = Field(default_factory=InstallSpec)
    similar_models: list[str] = Field(default_factory=list)
    inference_params: list[InferenceParam] = Field(default_factory=list)


class InstallState(BaseModel):
    model_id: str
    status: str = "not_installed"
    version: str | None = None
    error: str | None = None
    progress: float = 0.0
    installed_at: str | None = None
