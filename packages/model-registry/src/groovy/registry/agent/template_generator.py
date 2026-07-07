from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from groovy.schema.models import Workflow
from groovy.schema.validate import validate_workflow


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "workflow-template"


def _infer_tags(workflow: Workflow) -> list[str]:
    tags: set[str] = set()
    for node in workflow.nodes:
        tags.add(node.type.lower())
        if node.type in {"LoadAudio", "Preview"}:
            continue
        category = node.type.replace("Node", "").lower()
        if category:
            tags.add(category)
    return sorted(tags)[:12]


def generate_template_from_workflow(
    workflow_data: dict[str, Any],
    *,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    known_node_types: set[str] | None = None,
) -> dict[str, Any]:
    workflow = Workflow.model_validate(workflow_data)
    template_title = title or workflow.metadata.title or "Generated Template"
    template_description = (
        description
        or workflow.metadata.description
        or f"Generated from workflow with {len(workflow.nodes)} nodes."
    )
    template_tags = tags or _infer_tags(workflow)
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    template = {
        "schema_version": workflow.schema_version,
        "groovy_version": workflow.groovy_version,
        "id": str(uuid.uuid4()),
        "metadata": {
            "title": template_title,
            "description": template_description,
            "tags": template_tags,
            "created_at": now,
            "modified_at": now,
            "generated": True,
        },
        "nodes": [node.model_dump() for node in workflow.nodes],
        "links": [link.model_dump() for link in workflow.links],
        "groups": workflow.groups,
        "view": workflow.view or {"zoom": 1.0, "pan": {"x": 0, "y": 0}},
    }
    validation = None
    if known_node_types is not None:
        validation = validate_workflow(
            Workflow.model_validate(template),
            known_node_types=known_node_types,
        ).model_dump()
    return {
        "template": template,
        "template_id": _slugify(template_title),
        "validation": validation,
        "agent": "template_generator",
        "suggested_readme": (
            f"# {template_title}\n\n{template_description}\n\n"
            f"**Tags:** {', '.join(template_tags)}\n"
        ),
    }
