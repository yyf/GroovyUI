from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from groovy.executor.batch import run_batch_render
from groovy.executor import Executor
from groovy.executor.engine import GROOVY_VERSION
from groovy.node import NODE_REGISTRY, get_node_class
from groovy.nodes.core import register_all as register_core
from groovy.nodes.ai import register_all as register_ai
from groovy.executor.provenance import summarize_workflow_outputs
from groovy.registry import ModelRegistry
from groovy.registry.catalog import ModelCatalog
from groovy.registry.agent.install_recovery import install_recovery
from groovy.registry.agent.node_enricher import enrich_node_schema
from groovy.registry.agent.recommender import recommend_models
from groovy.registry.agent.workflow_suggester import suggest_workflows
from groovy.registry.agent.license_scanner import scan_workflow_licenses
from groovy.registry.agent.curator import approve_draft, ingest_drafts, list_drafts, save_discover_draft
from groovy.registry.discover import DiscoverError, discover_models
from groovy.registry.agent.template_generator import generate_template_from_workflow
from groovy.registry.agent.registry_freshness import scan_registry_freshness
from groovy.registry.installer import model_install_complete
from groovy.registry.studio_settings import StudioSettingsStore
from groovy.registry.workflow_models import missing_models_for_workflow
from groovy.registry.pack_installer import PackInstaller
from groovy.registry.packs import list_packs
from groovy.registry.compliance import summarize_compliance
from groovy.registry.compliance_report import build_compliance_report, render_compliance_pdf
from groovy.schema.models import Workflow
from groovy.schema.validate import validate_workflow
from groovy.schema.comfy_import import import_comfy_workflow
from groovy.executor.live_midi import LiveIoState
from groovy.executor.osc_live import OscCaptureStore
from groovy.server.bootstrap import ensure_project_samples
from groovy.server.compare import analyze_ab_pair
from groovy.server.live_io_hub import MidiInHub, start_osc_listener
from pydantic import BaseModel, Field

register_core()
register_ai()

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_WORKSPACE = REPO_ROOT / "workspace"
TEMPLATES_DIR = REPO_ROOT / "templates"
PROJECT_DIR = Path(os.environ.get("GROOVY_PROJECT_DIR", str(DEFAULT_WORKSPACE))).resolve()
USER_TEMPLATES_DIR = PROJECT_DIR / "templates"
HOST = os.environ.get("GROOVY_HOST", "127.0.0.1")
PORT = int(os.environ.get("GROOVY_PORT", "8188"))

_live_io = LiveIoState(PROJECT_DIR)
_midi_hub = MidiInHub()
_osc_transport: asyncio.DatagramTransport | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _osc_transport
    ensure_project_samples(PROJECT_DIR, bundled_dir=REPO_ROOT / "assets" / "samples")
    _osc_transport = await start_osc_listener(PROJECT_DIR, _live_io, _midi_hub)
    yield
    if _osc_transport is not None:
        _osc_transport.close()


app = FastAPI(title="GroovyUI", version=GROOVY_VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("GROOVY_CORS_ORIGIN", "http://127.0.0.1:5173")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_jobs: dict[str, dict[str, Any]] = {}
_job_cancel_flags: dict[str, threading.Event] = {}
_install_threads: dict[str, threading.Thread] = {}
_ws_subscribers: dict[str, set[WebSocket]] = {}
_executor = Executor(PROJECT_DIR)
_registry = ModelRegistry(PROJECT_DIR)
_pack_installer = PackInstaller(PROJECT_DIR)
_studio_settings = StudioSettingsStore(PROJECT_DIR)


class ModelSearchRequest(BaseModel):
    query: str = ""
    task_type: str | None = None
    commercial_ok: bool | None = None
    node_type: str | None = None


class ModelRecommendRequest(BaseModel):
    prompt: str
    commercial_ok: bool | None = None
    max_results: int = 5


class ModelDraftRequest(BaseModel):
    external_id: str
    name: str
    description: str = ""
    author: str = ""
    task_types: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    license: dict[str, Any] = Field(default_factory=dict)
    source_url: str = ""
    suggested_compatible_nodes: list[str] = Field(default_factory=list)


class ProvenanceRequest(BaseModel):
    workflow: dict[str, Any]
    outputs: dict[str, Any] = {}
    target_node_id: str | None = None


class ComplianceReportRequest(BaseModel):
    workflow: dict[str, Any]
    outputs: dict[str, Any] = {}
    target_node_id: str | None = None


class ExecuteRequest(BaseModel):
    workflow: dict[str, Any]
    target_nodes: list[str] | None = None
    force_rebuild: bool = False


class ValidateRequest(BaseModel):
    workflow: dict[str, Any]


class WorkflowSuggestRequest(BaseModel):
    prompt: str


class ComfyImportRequest(BaseModel):
    workflow: dict[str, Any]
    title: str | None = None


class BatchRenderRequest(BaseModel):
    workflow: dict[str, Any]
    input_dir: str
    file_glob: str = "*.wav,*.flac"
    load_node_id: str | None = None
    target_nodes: list[str] | None = None


class LiveIoSettingsRequest(BaseModel):
    midi_input_enabled: bool | None = None
    midi_output_enabled: bool | None = None
    osc_live_enabled: bool | None = None
    default_input_id: str | None = None
    default_output_id: str | None = None
    audio_input_enabled: bool | None = None
    audio_output_enabled: bool | None = None
    default_audio_input_id: str | None = None
    default_audio_output_id: str | None = None


class StudioSettingsRequest(BaseModel):
    hf_token: str | None = None
    inference_mode: str | None = None


class MidiInEventRequest(BaseModel):
    device_id: str
    event: dict[str, Any]


class MidiOutSendRequest(BaseModel):
    device_id: str
    events: list[dict[str, Any]]


class OscInRequest(BaseModel):
    address: str
    args: list[Any] = []
    frame: int = 0


class GenerateTemplateRequest(BaseModel):
    workflow: dict[str, Any]
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None


class CompareAnalyzeRequest(BaseModel):
    cache_id_a: str
    cache_id_b: str
    model_id: str = "groovy-signal-diff"
    label_a: str = "A"
    label_b: str = "B"
    question: str | None = None


def _workflow_from_dict(data: dict[str, Any]) -> Workflow:
    return Workflow.model_validate(data)


def _authenticity_id_from_outputs(
    outputs: dict[str, Any],
    target_node_id: str | None = None,
) -> str | None:
    if target_node_id:
        focus = outputs.get(target_node_id) or {}
        if isinstance(focus, dict) and focus.get("authenticity_id"):
            return str(focus["authenticity_id"])
    for output in outputs.values():
        if isinstance(output, dict) and output.get("authenticity_id"):
            return str(output["authenticity_id"])
    return None


def _load_authenticity_record(report_id: str) -> dict[str, Any] | None:
    try:
        report = _executor.cache.load_authenticity(report_id)
    except FileNotFoundError:
        return None
    return report.record


def _compliance_report_filename(title: str) -> str:
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in title.lower()).strip("-")
    slug = slug[:60] or "workflow"
    return f"groovy-compliance-{slug}.pdf"


def _template_meta(path: Path, source: str) -> dict[str, str]:
    data = json.loads(path.read_text())
    meta = data.get("metadata", {})
    template_id = path.name.removesuffix(".groovy.json")
    return {
        "id": template_id,
        "title": str(meta.get("title", template_id)),
        "description": str(meta.get("description", "")),
        "source": source,
    }


def _list_all_templates() -> list[dict[str, str]]:
    templates: list[dict[str, str]] = []
    seen: set[str] = set()
    if TEMPLATES_DIR.is_dir():
        for path in sorted(TEMPLATES_DIR.glob("*.groovy.json")):
            entry = _template_meta(path, "bundled")
            templates.append(entry)
            seen.add(entry["id"])
    if USER_TEMPLATES_DIR.is_dir():
        for path in sorted(USER_TEMPLATES_DIR.glob("*.groovy.json")):
            entry = _template_meta(path, "user")
            if entry["id"] in seen:
                continue
            templates.append(entry)
            seen.add(entry["id"])
    return templates


def _resolve_template_path(template_id: str) -> Path | None:
    # Bundled wins over any user file with the same id (user saves must not shadow defaults).
    bundled_path = TEMPLATES_DIR / f"{template_id}.groovy.json"
    if bundled_path.exists():
        return bundled_path
    user_path = USER_TEMPLATES_DIR / f"{template_id}.groovy.json"
    if user_path.exists():
        return user_path
    return None


def _user_template_id_taken(template_id: str) -> bool:
    if (USER_TEMPLATES_DIR / f"{template_id}.groovy.json").exists():
        return True
    if (TEMPLATES_DIR / f"{template_id}.groovy.json").exists():
        return True
    return False


def _unique_user_template_path(template_id: str) -> Path:
    USER_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    if not _user_template_id_taken(template_id):
        return USER_TEMPLATES_DIR / f"{template_id}.groovy.json"
    index = 2
    while True:
        candidate_id = f"{template_id}-{index}"
        if not _user_template_id_taken(candidate_id):
            return USER_TEMPLATES_DIR / f"{candidate_id}.groovy.json"
        index += 1


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
def health() -> dict[str, Any]:
    studio = _studio_settings.public_view()
    return {
        "status": "ok",
        "groovy_version": GROOVY_VERSION,
        "compare_api": True,
        "inference_mode": studio["inference_mode"],
        "inference_effective": studio["inference_effective"],
        "inference_stub_active": studio["inference_stub_active"],
    }


@app.get("/api/midi/devices")
def midi_devices(direction: str | None = None) -> dict[str, list[dict[str, str]]]:
    devices = _live_io.list_devices(direction=direction)
    return {"devices": [device.to_dict() for device in devices]}


@app.get("/api/audio/devices")
def audio_devices(direction: str | None = None) -> dict[str, list[dict[str, Any]]]:
    devices = _live_io.list_audio_devices(direction=direction)
    return {"devices": [device.to_dict() for device in devices]}


@app.get("/api/settings/live-io")
def get_live_io_settings() -> dict[str, Any]:
    return _live_io.settings.to_dict()


@app.post("/api/settings/live-io")
def update_live_io_settings(body: LiveIoSettingsRequest) -> dict[str, Any]:
    data = body.model_dump(exclude_none=True)
    for key, value in data.items():
        setattr(_live_io.settings, key, value)
    _live_io.save_settings()
    return _live_io.settings.to_dict()


@app.get("/api/settings/studio")
def get_studio_settings() -> dict[str, Any]:
    return _studio_settings.public_view()


@app.post("/api/settings/studio")
def update_studio_settings(body: StudioSettingsRequest) -> dict[str, Any]:
    patch = body.model_dump(exclude_unset=True)
    mode = patch.get("inference_mode")
    if mode is not None:
        normalized = str(mode).strip().lower()
        if normalized not in ("real", "stub"):
            raise HTTPException(status_code=400, detail="inference_mode must be 'real' or 'stub'")
        patch["inference_mode"] = normalized
    return _studio_settings.save(patch)


@app.post("/api/cache/clear")
def clear_render_cache() -> dict[str, Any]:
    """Delete render cache files under ``.groovy/cache`` (not models or settings)."""
    cache_dir = PROJECT_DIR / ".groovy" / "cache"
    removed = 0
    if cache_dir.is_dir():
        for path in cache_dir.iterdir():
            if path.is_file():
                path.unlink()
                removed += 1
    return {"status": "ok", "removed": removed, "cache_dir": str(cache_dir)}


@app.post("/api/midi/in/event")
def midi_in_event(body: MidiInEventRequest) -> dict[str, str]:
    if not _live_io.settings.midi_input_enabled:
        raise HTTPException(status_code=403, detail="MIDI input is disabled")
    _live_io.append_midi_input(body.device_id, body.event)
    return {"status": "ok"}


@app.post("/api/midi/out/send")
def midi_out_send(body: MidiOutSendRequest) -> dict[str, Any]:
    if not _live_io.settings.midi_output_enabled:
        raise HTTPException(status_code=403, detail="MIDI output is disabled")
    sent = 0
    for event in body.events:
        if event.get("type") == "sysex":
            continue
        _live_io.append_midi_output({**event, "device_id": body.device_id})
        sent += 1
    return {"status": "ok", "sent": sent}


@app.get("/api/midi/out/log")
def midi_out_log() -> dict[str, Any]:
    return {"events": _live_io.midi_out_log()}


@app.post("/api/osc/in")
async def osc_in(body: OscInRequest) -> dict[str, str]:
    if not _live_io.settings.osc_live_enabled:
        raise HTTPException(status_code=403, detail="Live OSC is disabled")
    store = OscCaptureStore(PROJECT_DIR)
    if not store.append(body.address, body.args, frame=body.frame):
        raise HTTPException(status_code=400, detail="OSC message rejected")
    from groovy.executor.osc_live import parse_widget_target

    target = parse_widget_target(body.address)
    await _midi_hub.broadcast(
        {
            "type": "osc.message",
            "address": body.address,
            "args": body.args,
            "target": {"node_id": target[0], "param": target[1]} if target else None,
        }
    )
    return {"status": "ok"}


@app.get("/api/osc/events")
def osc_events() -> dict[str, Any]:
    store = OscCaptureStore(PROJECT_DIR)
    return {"events": store.events()}


@app.get("/api/packs")
def list_node_packs() -> dict[str, Any]:
    return {"packs": [pack.to_dict() for pack in list_packs()]}


@app.post("/api/packs/{pack_id}/install")
def install_node_pack(pack_id: str) -> dict[str, Any]:
    state = _pack_installer.install(pack_id, consent=True)
    if state.status == "failed":
        raise HTTPException(status_code=404, detail=state.error or "Install failed")
    return state.to_dict()


@app.get("/api/packs/installed")
def list_installed_packs() -> dict[str, Any]:
    return {"packs": _pack_installer.list_installed()}


@app.get("/api/registry/freshness")
def registry_freshness() -> dict[str, Any]:
    return scan_registry_freshness(_registry.catalog, _registry.store)


@app.post("/api/workflow/generate-template")
def generate_template_endpoint(body: GenerateTemplateRequest) -> dict[str, Any]:
    return generate_template_from_workflow(
        body.workflow,
        title=body.title,
        description=body.description,
        tags=body.tags,
        known_node_types=set(NODE_REGISTRY.keys()),
    )


@app.post("/api/project/upload")
async def upload_project_asset(file: UploadFile = File(...)) -> dict[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    safe_name = Path(file.filename).name
    dest_dir = PROJECT_DIR / "assets" / "uploads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_name
    dest.write_bytes(await file.read())
    return {"path": f"assets/uploads/{safe_name}"}


@app.get("/api/project/audio-meta")
def project_audio_meta(path: str) -> dict[str, Any]:
    from groovy.executor.audio_meta import probe_audio_file
    from groovy.executor.project_paths import resolve_project_media_path
    from groovy.server.bootstrap import ensure_project_samples

    ensure_project_samples(PROJECT_DIR, bundled_dir=REPO_ROOT / "assets" / "samples")
    try:
        resolved, canonical_path = resolve_project_media_path(_executor.cache, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        meta = probe_audio_file(resolved)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                f"UNSUPPORTED_FORMAT: {canonical_path} — {exc}. "
                "Try WAV/FLAC/AIFF; some MP3/OGG files may need conversion."
            ),
        ) from exc
    meta["canonical_path"] = canonical_path
    meta["project_dir"] = str(_executor.cache.project_dir)
    return meta


@app.get("/api/nodes")
def list_nodes() -> dict[str, list[dict[str, Any]]]:
    return {"nodes": [get_node_class(t).describe() for t in sorted(NODE_REGISTRY)]}


@app.get("/api/nodes/{node_type}")
def get_node(node_type: str, enriched: bool = True) -> dict[str, Any]:
    try:
        schema = get_node_class(node_type).describe()
        if enriched:
            return enrich_node_schema(node_type, schema)
        return schema
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/templates")
def save_user_template(body: GenerateTemplateRequest) -> dict[str, Any]:
    result = generate_template_from_workflow(
        body.workflow,
        title=body.title,
        description=body.description,
        tags=body.tags,
        known_node_types=set(NODE_REGISTRY.keys()),
    )
    template_id = str(result["template_id"])
    path = _unique_user_template_path(template_id)
    path.write_text(json.dumps(result["template"], indent=2) + "\n")
    actual_id = path.name.removesuffix(".groovy.json")
    return {
        **result,
        "template_id": actual_id,
        "source": "user",
        "path": str(path.relative_to(PROJECT_DIR)),
    }


@app.get("/api/templates")
def list_templates() -> dict[str, list[dict[str, str]]]:
    return {"templates": _list_all_templates()}


@app.delete("/api/templates/{template_id}")
def delete_user_template(template_id: str) -> dict[str, Any]:
    if "/" in template_id or "\\" in template_id or ".." in template_id or not template_id.strip():
        raise HTTPException(status_code=400, detail="Invalid template id")
    path = (USER_TEMPLATES_DIR / f"{template_id}.groovy.json").resolve()
    try:
        path.relative_to(USER_TEMPLATES_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid template id") from exc
    if not path.is_file():
        if (TEMPLATES_DIR / f"{template_id}.groovy.json").is_file():
            raise HTTPException(status_code=403, detail="Bundled templates cannot be deleted")
        raise HTTPException(status_code=404, detail="Template not found")
    path.unlink()
    return {"ok": True, "template_id": template_id}


@app.get("/api/templates/{template_id}")
def get_template(template_id: str) -> dict[str, Any]:
    path = _resolve_template_path(template_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return json.loads(path.read_text())


@app.get("/api/models")
def list_models() -> dict[str, list[dict[str, Any]]]:
    return {"models": [_model_card(m) for m in _registry.catalog.all()]}


@app.get("/api/models/discover")
def discover_models_endpoint(
    query: str = "",
    task_type: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    settings = StudioSettingsStore(PROJECT_DIR)
    try:
        results = discover_models(
            query,
            task_type=task_type,
            limit=limit,
            hf_token=settings.hf_token(),
        )
    except DiscoverError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"results": results}


@app.post("/api/models/drafts")
def create_model_draft(body: ModelDraftRequest) -> dict[str, Any]:
    manifest, created = save_discover_draft(_registry.draft_dir, body.model_dump())
    return {"model": _draft_model_card(manifest.model_dump()), "created": created}


@app.post("/api/models/search")
def search_models(body: ModelSearchRequest) -> dict[str, list[dict[str, Any]]]:
    matches = _registry.catalog.search(
        body.query,
        task_type=body.task_type,
        commercial_ok=body.commercial_ok,
        node_type=body.node_type,
    )
    cards = [_model_card(m) for m in matches]
    cards.extend(_filtered_draft_cards(body.query, body.task_type, body.commercial_ok, body.node_type))
    return {"models": cards}


@app.get("/api/models/{model_id}")
def get_model(model_id: str) -> dict[str, Any]:
    manifest = _registry.catalog.get(model_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Model not found")
    return _model_card(manifest)


@app.post("/api/models/{model_id}/install", status_code=202)
def install_model(model_id: str) -> dict[str, Any]:
    if _is_draft_model(model_id):
        raise HTTPException(
            status_code=400,
            detail="Draft models cannot be installed until published and verified.",
        )
    manifest = _registry.catalog.get(model_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="Model not found")
    if manifest.status != "published":
        raise HTTPException(
            status_code=400,
            detail="Only published catalog models can be installed from Model Browser.",
        )
    return _start_model_install(model_id).model_dump()


@app.get("/api/models/{model_id}/install/status")
def install_model_status(model_id: str) -> dict[str, Any]:
    if not _registry.catalog.get(model_id):
        raise HTTPException(status_code=404, detail="Model not found")
    return _registry.store.get(model_id).model_dump()


@app.post("/api/models/recommend")
def recommend_models_endpoint(body: ModelRecommendRequest) -> dict[str, Any]:
    return recommend_models(
        _registry.catalog,
        _registry.store,
        prompt=body.prompt,
        commercial_ok=body.commercial_ok,
        max_results=body.max_results,
    )


@app.get("/api/models/{model_id}/recovery")
def model_recovery(model_id: str) -> dict[str, Any]:
    return install_recovery(_registry.catalog, _registry.store, _registry.installer, model_id)


def _model_card(manifest) -> dict[str, Any]:
    state = _registry.store.get(manifest.id)
    from groovy.nodes.ai.inference_env import model_inference_ready

    return {
        **manifest.model_dump(),
        "install_status": state.status,
        "install_progress": state.progress,
        "install_error": state.error,
        "dev_stub": manifest.install.dev_stub,
        "inference_ready": model_inference_ready(manifest.id, dev_stub=manifest.install.dev_stub),
        "install_complete": model_install_complete(manifest, state),
    }


def _draft_model_card(data: dict[str, Any]) -> dict[str, Any]:
    return {
        **data,
        "install_status": "draft",
        "install_progress": 0.0,
        "install_error": None,
        "dev_stub": True,
        "inference_ready": False,
        "install_complete": False,
    }


def _is_draft_model(model_id: str) -> bool:
    if (_registry.draft_dir / f"{model_id}.json").exists():
        return True
    manifest = _registry.catalog.get(model_id)
    return manifest is not None and manifest.status != "published"


def _filtered_draft_cards(
    query: str,
    task_type: str | None,
    commercial_ok: bool | None,
    node_type: str | None,
) -> list[dict[str, Any]]:
    q = query.strip().lower()
    cards: list[dict[str, Any]] = []
    for draft in list_drafts(_registry.draft_dir):
        card = _draft_model_card(draft)
        if task_type and task_type not in card.get("task_types", []):
            continue
        if commercial_ok is True and not card.get("license", {}).get("commercial_ok"):
            continue
        if node_type and node_type not in card.get("compatible_nodes", []):
            continue
        if q:
            haystack = " ".join(
                [
                    str(card.get("id", "")),
                    str(card.get("name", "")),
                    str(card.get("description", "")),
                    " ".join(card.get("tags") or []),
                    " ".join(card.get("task_types") or []),
                ]
            ).lower()
            if q not in haystack and not any(token in haystack for token in q.split()):
                continue
        cards.append(card)
    return cards


def _start_model_install(model_id: str):
    manifest = _registry.catalog.get(model_id)
    state = _registry.store.get(model_id)
    if manifest and model_install_complete(manifest, state):
        return state
    active = _install_threads.get(model_id)
    if active is not None and active.is_alive():
        return _registry.store.get(model_id)

    def run() -> None:
        try:
            _registry.installer.install(model_id)
        finally:
            _install_threads.pop(model_id, None)

    _registry.store.mark_progress(model_id, "downloading", 0.05)
    thread = threading.Thread(target=run, daemon=True, name=f"install-{model_id}")
    _install_threads[model_id] = thread
    thread.start()
    return _registry.store.get(model_id)


@app.post("/api/workflow/import/comfy")
def import_comfy_workflow_endpoint(body: ComfyImportRequest) -> dict[str, Any]:
    converted = import_comfy_workflow(body.workflow, title=body.title or "Imported from ComfyUI")
    import_meta = converted.pop("import_meta", {})
    workflow = _workflow_from_dict(converted)
    validation = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    missing_models = missing_models_for_workflow(workflow, _registry.catalog, _registry.store)
    return {
        "workflow": converted,
        "validation": validation.model_dump(),
        "import_meta": import_meta,
        "missing_models": missing_models,
    }


@app.post("/api/workflow/missing-models")
def workflow_missing_models(body: ValidateRequest) -> dict[str, Any]:
    workflow = _workflow_from_dict(body.workflow)
    return {
        "missing_models": missing_models_for_workflow(workflow, _registry.catalog, _registry.store),
    }


@app.post("/api/workflow/suggest")
def workflow_suggest(body: WorkflowSuggestRequest) -> dict[str, Any]:
    return suggest_workflows(body.prompt, TEMPLATES_DIR)


@app.post("/api/registry/ingest")
def registry_ingest(force: bool = False) -> dict[str, Any]:
    return ingest_drafts(_registry.draft_dir, skip_existing=not force)


@app.get("/api/registry/drafts")
def registry_drafts() -> dict[str, Any]:
    return {"drafts": list_drafts(_registry.draft_dir)}


@app.post("/api/registry/drafts/{model_id}/approve")
def registry_approve_draft(model_id: str) -> dict[str, Any]:
    try:
        manifest = approve_draft(_registry.draft_dir, _registry.overlay_path, model_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _registry.catalog = ModelCatalog(overlay_path=_registry.overlay_path)
    return manifest.model_dump()


@app.post("/api/workflow/validate")
def validate_workflow_endpoint(body: ValidateRequest) -> dict[str, Any]:
    workflow = _workflow_from_dict(body.workflow)
    result = validate_workflow(workflow, known_node_types=set(NODE_REGISTRY.keys()))
    return result.model_dump()


@app.post("/api/workflow/compliance")
def workflow_compliance(body: ValidateRequest) -> dict[str, Any]:
    workflow = _workflow_from_dict(body.workflow)
    return summarize_compliance(workflow, _registry)


@app.post("/api/workflow/license-scan")
def workflow_license_scan(body: ValidateRequest) -> dict[str, Any]:
    workflow = _workflow_from_dict(body.workflow)
    return scan_workflow_licenses(workflow, _registry)


@app.post("/api/workflow/compliance-report")
def workflow_compliance_report(body: ComplianceReportRequest) -> Response:
    workflow = _workflow_from_dict(body.workflow)
    provenance = None
    if body.outputs:
        provenance = summarize_workflow_outputs(
            _executor.cache,
            body.outputs,
            target_node_id=body.target_node_id,
        )
    authenticity_id = _authenticity_id_from_outputs(body.outputs, body.target_node_id)
    authenticity = _load_authenticity_record(authenticity_id) if authenticity_id else None
    report = build_compliance_report(
        workflow,
        _registry,
        provenance=provenance,
        authenticity=authenticity,
    )
    pdf_bytes = render_compliance_pdf(report)
    filename = _compliance_report_filename(str(report.get("workflow_title") or workflow.id))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/batch/render")
def batch_render_endpoint(body: BatchRenderRequest) -> dict[str, Any]:
    workflow = _workflow_from_dict(body.workflow)
    try:
        return run_batch_render(
            _executor,
            workflow,
            input_dir=body.input_dir,
            file_glob=body.file_glob,
            load_node_id=body.load_node_id,
            target_nodes=body.target_nodes,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/workflow/provenance")
def workflow_provenance(body: ProvenanceRequest) -> dict[str, Any]:
    workflow = _workflow_from_dict(body.workflow)
    return summarize_workflow_outputs(
        _executor.cache,
        body.outputs,
        target_node_id=body.target_node_id,
    )


@app.get("/api/cache/{cache_id}/provenance")
def cache_provenance(cache_id: str) -> dict[str, Any]:
    record = _executor.cache.read_provenance(cache_id)
    if not record:
        raise HTTPException(status_code=404, detail="Provenance not found")
    return record


@app.get("/api/authenticity/{report_id}")
def get_authenticity(report_id: str) -> dict[str, Any]:
    try:
        report = _executor.cache.load_authenticity(report_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Authenticity report not found") from exc
    return report.record


@app.post("/api/execute", status_code=202)
async def execute(body: ExecuteRequest) -> dict[str, str]:
    ensure_project_samples(PROJECT_DIR, bundled_dir=REPO_ROOT / "assets" / "samples")
    workflow = _workflow_from_dict(body.workflow)
    job_id = str(uuid.uuid4())
    cancel_flag = threading.Event()
    _job_cancel_flags[job_id] = cancel_flag
    _jobs[job_id] = {
        "status": "running",
        "progress": 0.0,
        "outputs": {},
        "error": None,
        "message": "Queued",
        "started_at": asyncio.get_event_loop().time(),
    }

    async def run_job() -> None:
        loop = asyncio.get_event_loop()

        def on_progress(_executor_job_id: str, node_id: str, fraction: float, message: str) -> None:
            _jobs[job_id]["current_node"] = node_id
            _jobs[job_id]["progress"] = fraction
            _jobs[job_id]["message"] = message
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
                cancel_check=cancel_flag.is_set,
            ),
        )
        _job_cancel_flags.pop(job_id, None)
        if result.status == "completed":
            _jobs[job_id].update(
                {
                    "status": "completed",
                    "progress": 1.0,
                    "outputs": result.outputs,
                    "manifest_path": result.manifest_path,
                    "message": "Complete",
                }
            )
            await _broadcast(
                job_id,
                {"type": "job.complete", "job_id": job_id, "outputs": result.outputs},
            )
        elif result.status == "cancelled":
            _jobs[job_id].update(
                {
                    "status": "cancelled",
                    "outputs": result.outputs,
                    "error": result.error,
                    "message": result.error or "Cancelled",
                }
            )
            await _broadcast(
                job_id,
                {
                    "type": "job.cancelled",
                    "job_id": job_id,
                    "outputs": result.outputs,
                    "error": {"code": "CANCELLED", "message": result.error or "Cancelled"},
                },
            )
        else:
            _jobs[job_id].update(
                {
                    "status": "failed",
                    "error": result.error,
                    "outputs": result.outputs,
                    "message": result.error,
                }
            )
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


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict[str, Any]:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "running":
        return {"ok": True, "status": job["status"]}
    flag = _job_cancel_flags.get(job_id)
    if flag:
        flag.set()
    job["message"] = "Cancelling…"
    return {"ok": True, "status": "running"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


@app.get("/api/jobs/{job_id}/manifest")
def get_job_manifest(job_id: str) -> dict[str, Any]:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    manifest_path = job.get("manifest_path")
    if not manifest_path:
        raise HTTPException(status_code=404, detail="Manifest not available for this job")
    path = Path(manifest_path)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Manifest file not found")
    return json.loads(path.read_text())


@app.get("/api/cache/{cache_id}/metrics")
def cache_metrics(cache_id: str) -> dict[str, Any]:
    from groovy.executor.ab_compare import measure_clip

    try:
        metrics = measure_clip(_executor.cache, cache_id, label=cache_id)
        return metrics.to_dict()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Cache not found") from exc


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
            if _executor.cache.is_midi_cache(cache_id):
                data = _executor.cache.midi_preview_wav_bytes(cache_id)
            else:
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


@app.get("/api/cache/{cache_id}/spectrogram")
def cache_spectrogram(cache_id: str, width: int = 512, height: int = 48) -> dict[str, Any]:
    try:
        return _executor.cache.spectrogram_tiles(cache_id, width=width, height=height)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Cache not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/cache/{cache_id}/midi-roll")
def cache_midi_roll(cache_id: str) -> dict[str, Any]:
    try:
        return _executor.cache.midi_roll(cache_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="MIDI cache not found") from exc


@app.post("/api/compare/analyze")
def compare_analyze(body: CompareAnalyzeRequest) -> dict[str, Any]:
    manifest = _registry.catalog.get(body.model_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Model not found: {body.model_id}")
    try:
        return analyze_ab_pair(
            _executor.cache,
            _registry,
            cache_id_a=body.cache_id_a,
            cache_id_b=body.cache_id_b,
            label_a=body.label_a,
            label_b=body.label_b,
            model_id=body.model_id,
            question=body.question,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"{exc}. Re-render the workflow (Shift+R) if clips were cleared.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.websocket("/api/ws/midi/in")
async def midi_in_websocket(ws: WebSocket) -> None:
    await _midi_hub.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "midi.event":
                if not _live_io.settings.midi_input_enabled:
                    continue
                device_id = str(msg.get("device_id", _live_io.settings.default_input_id or "virtual:in-demo"))
                event = msg.get("event") or {}
                _live_io.append_midi_input(device_id, event)
            elif msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        _midi_hub.disconnect(ws)


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
    ensure_project_samples(PROJECT_DIR, bundled_dir=REPO_ROOT / "assets" / "samples")
    uvicorn.run("groovy.server.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
