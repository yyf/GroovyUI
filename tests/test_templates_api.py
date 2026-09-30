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

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "templates"
DEV_TEMPLATES_DIR = ROOT / "docs" / "internal" / "templates"


def _bundled_template_paths() -> list[Path]:
    paths: list[Path] = []
    for directory in (TEMPLATES_DIR, DEV_TEMPLATES_DIR):
        if directory.is_dir():
            paths.extend(sorted(directory.glob("*.groovy.json")))
    return paths


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_list_templates(client: TestClient) -> None:
    res = client.get("/api/templates")
    assert res.status_code == 200
    templates = res.json()["templates"]
    ids = {t["id"] for t in templates}
    assert "hello-groovy" in ids
    bundled = [t for t in templates if t.get("source") == "bundled"]
    assert len(bundled) >= 1


def test_save_user_template_listed(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_PROJECT_DIR", str(tmp_path))
    import groovy.server.main as main

    monkeypatch.setattr(main, "PROJECT_DIR", tmp_path.resolve())
    monkeypatch.setattr(main, "USER_TEMPLATES_DIR", tmp_path.resolve() / "templates")

    hello = client.get("/api/templates/hello-groovy").json()
    res = client.post(
        "/api/templates",
        json={"workflow": hello, "title": "My Custom Export"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "user"

    listed = client.get("/api/templates").json()["templates"]
    user_templates = [t for t in listed if t.get("source") == "user"]
    assert any(t["title"] == "My Custom Export" for t in user_templates)

    loaded = client.get(f"/api/templates/{body['template_id']}")
    assert loaded.status_code == 200
    assert loaded.json()["metadata"]["title"] == "My Custom Export"

    deleted = client.delete(f"/api/templates/{body['template_id']}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    listed_after = client.get("/api/templates").json()["templates"]
    assert not any(t["id"] == body["template_id"] for t in listed_after)
    assert client.get(f"/api/templates/{body['template_id']}").status_code == 404


def test_delete_bundled_template_rejected(client: TestClient) -> None:
    res = client.delete("/api/templates/hello-groovy")
    assert res.status_code == 403


def test_save_user_template_does_not_shadow_bundled(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROOVY_PROJECT_DIR", str(tmp_path))
    import groovy.server.main as main

    monkeypatch.setattr(main, "PROJECT_DIR", tmp_path.resolve())
    monkeypatch.setattr(main, "USER_TEMPLATES_DIR", tmp_path.resolve() / "templates")

    bundled = client.get("/api/templates/podcast-denoise").json()
    assert len(bundled["nodes"]) > 0

    empty = {**bundled, "nodes": [], "links": [], "groups": []}
    res = client.post(
        "/api/templates",
        json={"workflow": empty, "title": "Podcast Denoise"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["template_id"] != "podcast-denoise"
    assert body["template_id"].startswith("podcast-denoise-")
    assert body["source"] == "user"

    loaded = client.get("/api/templates/podcast-denoise").json()
    assert loaded["metadata"]["title"] == "Podcast Denoise"
    assert len(loaded["nodes"]) > 0
    assert loaded["nodes"] == bundled["nodes"]

    user_loaded = client.get(f"/api/templates/{body['template_id']}").json()
    assert user_loaded["nodes"] == []


def test_get_template(client: TestClient) -> None:
    res = client.get("/api/templates/hello-groovy")
    assert res.status_code == 200
    data = res.json()
    assert data["metadata"]["title"] == "Hello GroovyUI"


def test_all_templates_validate() -> None:
    from groovy.nodes.ai import register_all as register_ai
    from groovy.nodes.core import register_all as register_core

    register_core()
    register_ai()
    for path in _bundled_template_paths():
        workflow = Workflow.model_validate(json.loads(path.read_text()))
        result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
        assert result.valid, f"{path.name}: {[e.message for e in result.errors]}"
