from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from groovy.executor import Executor
from groovy.executor.engine import GROOVY_VERSION
from groovy.node import NODE_REGISTRY, get_node_class
from groovy.nodes.core import register_all as register_core
from groovy.nodes.ai import register_all as register_ai
from groovy.registry import ModelRegistry
from groovy.schema.models import Workflow
from groovy.schema.validate import validate_workflow
from pydantic import BaseModel

register_core()
register_ai()

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_WORKSPACE = REPO_ROOT / "workspace"
TEMPLATES_DIR = REPO_ROOT / "templates"
PROJECT_DIR = Path(os.environ.get("GROOVY_PROJECT_DIR", str(DEFAULT_WORKSPACE))).resolve()
HOST = os.environ.get("GROOVY_HOST", "127.0.0.1")
PORT = int(os.environ.get("GROOVY_PORT", "8188"))

app = FastAPI(title="GroovyUI", version=GROOVY_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("GROOVY_CORS_ORIGIN", "http://127.0.0.1:5173")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_jobs: dict[str, dict[str, Any]] = {}
_ws_subscribers: dict[str, set[WebSocket]] = {}
_executor = Executor(PROJECT_DIR)
_registry = ModelRegistry(PROJECT_DIR)


class ModelSearchRequest(BaseModel):
    query: str = ""
    task_type: str | None = None
    commercial_ok: bool | None = None
    node_type: str | None = None


class ExecuteRequest(BaseModel):
    workflow: dict[str, Any]
    target_nodes: list[str] | None = None
    force_rebuild: bool = False


class ValidateRequest(BaseModel):
    workflow: dict[str, Any]


def _workflow_from_dict(data: dict[str, Any]) -> Workflow:
    return Workflow.model_validate(data)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "GroovyUI API",
        "groovy_version": GROOVY_VERSION,
        "health": "/api/health",
        "nodes": "/api/nodes",
        "studio": "http://127.0.0.1:5173",
        "docs": "/docs",
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "groovy_version": GROOVY_VERSION}


@app.get("/api/nodes")
def list_nodes() -> dict[str, list[dict[str, Any]]]:
    return {"nodes": [get_node_class(t).describe() for t in sorted(NODE_REGISTRY)]}


@app.get("/api/nodes/{node_type}")
def get_node(node_type: str) -> dict[str, Any]:
    try:
        return get_node_class(node_type).describe()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/templates")
def list_templates() -> dict[str, list[dict[str, str]]]:
    templates: list[dict[str, str]] = []
    for path in sorted(TEMPLATES_DIR.glob("*.groovy.json")):
        data = json.loads(path.read_text())
        meta = data.get("metadata", {})
        template_id = path.name.removesuffix(".groovy.json")
        templates.append(
            {
                "id": template_id,
                "title": str(meta.get("title", template_id)),
                "description": str(meta.get("description", "")),
            }
        )
    return {"templates": templates}


@app.get("/api/templates/{template_id}")
def get_template(template_id: str) -> dict[str, Any]:
    path = TEMPLATES_DIR / f"{template_id}.groovy.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    return json.loads(path.read_text())


@app.get("/api/models")
def list_models() -> dict[str, list[dict[str, Any]]]:
    return {"models": [_model_card(m) for m in _registry.catalog.all()]}


@app.post("/api/models/search")
def search_models(body: ModelSearchRequest) -> dict[str, list[dict[str, Any]]]:
    matches = _registry.catalog.search(
        body.query,
        task_type=body.task_type,
        commercial_ok=body.commercial_ok,
        node_type=body.node_type,
    )
    return {"models": [_model_card(m) for m in matches]}


@app.get("/api/models/{model_id}")
def get_model(model_id: str) -> dict[str, Any]:
    manifest = _registry.catalog.get(model_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Model not found")
    return _model_card(manifest)


@app.post("/api/models/{model_id}/install", status_code=202)
def install_model(model_id: str) -> dict[str, Any]:
    manifest = _registry.catalog.get(model_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Model not found")
    state = _registry.installer.install(model_id)
    return state.model_dump()


@app.get("/api/models/{model_id}/recovery")
def model_recovery(model_id: str) -> dict[str, Any]:
    return _registry.installer.recovery_suggestions(model_id)


def _model_card(manifest) -> dict[str, Any]:
    state = _registry.store.get(manifest.id)
    return {
        **manifest.model_dump(),
        "install_status": state.status,
        "install_progress": state.progress,
        "install_error": state.error,
    }


@app.post("/api/workflow/validate")
def validate_workflow_endpoint(body: ValidateRequest) -> dict[str, Any]:
    workflow = _workflow_from_dict(body.workflow)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    return result.model_dump()


@app.post("/api/execute", status_code=202)
async def execute(body: ExecuteRequest) -> dict[str, str]:
    workflow = _workflow_from_dict(body.workflow)
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "running", "progress": 0.0, "outputs": {}, "error": None}

    async def run_job() -> None:
        loop = asyncio.get_event_loop()

        def on_progress(_executor_job_id: str, node_id: str, fraction: float, message: str) -> None:
            _jobs[job_id]["current_node"] = node_id
            _jobs[job_id]["progress"] = fraction
            asyncio.run_coroutine_threadsafe(
                _broadcast(
                    job_id,
                    {
                        "type": "job.progress",
                        "job_id": job_id,
                        "node_id": node_id,
                        "progress": fraction,
                        "message": message,
                    },
                ),
                loop,
            )

        result = await loop.run_in_executor(
            None,
            lambda: _executor.execute(
                workflow,
                target_nodes=body.target_nodes,
                force_rebuild=body.force_rebuild,
                on_progress=on_progress,
            ),
        )
        if result.status == "completed":
            _jobs[job_id].update(
                {
                    "status": "completed",
                    "progress": 1.0,
                    "outputs": result.outputs,
                    "manifest_path": result.manifest_path,
                }
            )
            await _broadcast(
                job_id,
                {"type": "job.complete", "job_id": job_id, "outputs": result.outputs},
            )
        else:
            _jobs[job_id].update({"status": "failed", "error": result.error})
            await _broadcast(
                job_id,
                {
                    "type": "job.failed",
                    "job_id": job_id,
                    "error": {"code": "EXECUTION_FAILED", "message": result.error},
                },
            )

    asyncio.create_task(run_job())
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


@app.get("/api/cache/{cache_id}/meta")
def cache_meta(cache_id: str) -> dict[str, Any]:
    try:
        return _executor.cache.read_meta(cache_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Cache not found") from exc


@app.get("/api/cache/{cache_id}/preview")
def cache_preview(cache_id: str, format: str = "wav") -> Response:
    try:
        if format == "wav":
            data = _executor.cache.preview_wav_bytes(cache_id)
            return Response(content=data, media_type="audio/wav")
        raise HTTPException(status_code=400, detail="Unsupported format")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Cache not found") from exc


@app.get("/api/cache/{cache_id}/waveform")
def cache_waveform(cache_id: str, width: int = 512) -> dict[str, Any]:
    try:
        return _executor.cache.waveform_peaks(cache_id, width=width)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Cache not found") from exc


@app.websocket("/api/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    subscribed_job: str | None = None
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "subscribe":
                subscribed_job = msg.get("job_id")
                if subscribed_job:
                    _ws_subscribers.setdefault(subscribed_job, set()).add(ws)
            elif msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        if subscribed_job and subscribed_job in _ws_subscribers:
            _ws_subscribers[subscribed_job].discard(ws)


async def _broadcast(job_id: str, payload: dict[str, Any]) -> None:
    dead: list[WebSocket] = []
    for ws in _ws_subscribers.get(job_id, set()):
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_subscribers[job_id].discard(ws)


def main() -> None:
    import uvicorn

    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    uvicorn.run("groovy.server.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
