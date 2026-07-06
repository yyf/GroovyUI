from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkflowMetadata(BaseModel):
    title: str = "Untitled"
    author: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    modified_at: datetime | None = None


class NodeInstance(BaseModel):
    id: str
    type: str
    pos: dict[str, float] | None = None
    widgets: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)


class Link(BaseModel):
    id: str
    from_: list[str | int] = Field(alias="from")
    to: list[str | int]
    type: str

    model_config = {"populate_by_name": True}


class ViewState(BaseModel):
    zoom: float = 1.0
    pan: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})


class Workflow(BaseModel):
    schema_version: str
    groovy_version: str
    id: str
    metadata: WorkflowMetadata
    nodes: list[NodeInstance]
    links: list[Link]
    groups: list[dict[str, Any]] = Field(default_factory=list)
    view: ViewState | None = None

    model_config = {"populate_by_name": True}


class ValidationError(BaseModel):
    code: str
    message: str
    node_id: str | None = None
    link_id: str | None = None


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationError] = Field(default_factory=list)
    warnings: list[ValidationError] = Field(default_factory=list)
