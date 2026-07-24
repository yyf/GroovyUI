from __future__ import annotations

from pathlib import Path

from groovy.executor.engine import Executor
from groovy.node import get_node_class
from groovy.nodes.core import register_all
from groovy.schema.models import NodeInstance, Workflow, WorkflowMetadata

register_all()


def test_note_node_schema_has_text_widget_and_no_sockets() -> None:
    cls = get_node_class("Note")
    schema = cls.describe()
    assert schema["type"] == "Note"
    assert schema["inputs"] == []
    assert schema["outputs"] == []
    widgets = {w["name"]: w for w in schema["widgets"]}
    assert "text" in widgets
    assert widgets["text"]["type"] == "STRING"
    assert widgets["text"].get("multiline") is True


def test_note_node_run_is_noop() -> None:
    node = get_node_class("Note")()
    assert node.run(text="hello") == ()


def test_executor_skips_note_output_safely(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="note-test",
        metadata=WorkflowMetadata(title="Note"),
        nodes=[
            NodeInstance(id="n1", type="Note", widgets={"text": "document the denoise gain"}),
        ],
        links=[],
        groups=[],
    )
    result = Executor(project).execute(workflow)
    assert result.status == "completed", result.error
    assert "n1" not in result.outputs
