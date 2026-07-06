from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from groovy.nodes.core import register_all
from groovy.schema.models import Workflow
from groovy.schema.validate import validate_workflow
from groovy.server.main import app
from groovy.node import NODE_REGISTRY

register_all()

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = ROOT / "templates"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_list_templates(client: TestClient) -> None:
    res = client.get("/api/templates")
    assert res.status_code == 200
    templates = res.json()["templates"]
    ids = {t["id"] for t in templates}
    assert "hello-groovy" in ids


def test_get_template(client: TestClient) -> None:
    res = client.get("/api/templates/hello-groovy")
    assert res.status_code == 200
    data = res.json()
    assert data["metadata"]["title"] == "Hello Groovy"


def test_all_templates_validate() -> None:
    from groovy.nodes.ai import register_all as register_ai
    from groovy.nodes.core import register_all as register_core

    register_core()
    register_ai()
    for path in sorted(TEMPLATES_DIR.glob("*.groovy.json")):
        workflow = Workflow.model_validate(json.loads(path.read_text()))
        result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
        assert result.valid, f"{path.name}: {[e.message for e in result.errors]}"
