from __future__ import annotations

from pathlib import Path

import groovy.server.main as main
import pytest
from fastapi.testclient import TestClient
from groovy.registry import ModelRegistry
from groovy.registry.download import DownloadCancelled, download_file
from groovy.registry.machine import build_machine_checks, probe_machine
from groovy.registry.preflight import estimate_workflow_preflight
from groovy.schema.models import NodeInstance, Workflow, WorkflowMetadata


def test_download_file_honors_cancel_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "weights.bin"
    chunks = [b"chunk-one", b"chunk-two", b"chunk-three"]

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size: int = -1) -> bytes:
            if not chunks:
                return b""
            return chunks.pop(0)

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(),
    )

    calls = {"n": 0}

    def cancel_after_first() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    with pytest.raises(DownloadCancelled):
        download_file(
            "https://huggingface.co/org/model/resolve/main/weights.bin",
            dest,
            cancel_check=cancel_after_first,
        )
    assert not dest.exists()
    assert not (tmp_path / "weights.bin.partial").exists()


def test_build_machine_checks_flags_disk_short() -> None:
    checks = build_machine_checks(
        known_download_mb=2000,
        peak_vram_gb=4,
        machine={
            "disk_free_mb": 100,
            "vram_available_gb": 8,
            "vram_source": "cuda:test",
            "uv_available": True,
        },
        missing_verify_imports=[],
    )
    by_code = {check["code"]: check for check in checks}
    assert by_code["DISK_SHORT"]["severity"] == "error"
    assert by_code["VRAM_OK"]["severity"] == "ok"


def test_build_machine_checks_warns_on_tight_vram() -> None:
    checks = build_machine_checks(
        known_download_mb=10,
        peak_vram_gb=12,
        machine={
            "disk_free_mb": 50_000,
            "vram_available_gb": 4,
            "vram_source": "cuda:test",
            "uv_available": True,
        },
        missing_verify_imports=["torchaudio"],
    )
    by_code = {check["code"]: check for check in checks}
    assert by_code["VRAM_TIGHT"]["severity"] == "warning"
    assert by_code["RUNTIME_NEEDS_INSTALL"]["severity"] == "warning"


def test_preflight_includes_machine_and_checks(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    workflow = Workflow(
        schema_version="1.0.0",
        groovy_version="0.1.0",
        id="machine-preflight",
        metadata=WorkflowMetadata(title="Machine preflight"),
        nodes=[
            NodeInstance(id="n1", type="Denoise", widgets={"model": "deepfilternet-v3"}),
        ],
        links=[],
    )
    preflight = estimate_workflow_preflight(workflow, registry)
    assert "disk_free_mb" in preflight["machine"]
    assert any(check["code"].startswith("DISK_") for check in preflight["checks"])
    assert any(check["code"].startswith("VRAM_") for check in preflight["checks"])
    assert any(check["code"].startswith("RUNTIME_") for check in preflight["checks"])


def test_probe_machine_never_raises(tmp_path: Path) -> None:
    snapshot = probe_machine(tmp_path)
    assert snapshot["disk_free_mb"] >= 0
    assert Path(snapshot["disk_path"]).exists()


def test_install_cancel_api_sets_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROOVY_PROJECT_DIR", str(tmp_path))
    main.PROJECT_DIR = tmp_path
    main._registry = ModelRegistry(tmp_path)
    main._install_threads.clear()
    main._install_cancel_flags.clear()

    started = False

    def fake_install(model_id: str, *, cancel_check=None):
        nonlocal started
        started = True
        assert cancel_check is not None
        # Wait until cancel is requested, then cooperate.
        import time

        for _ in range(50):
            if cancel_check():
                return main._registry.store.mark_cancelled(model_id)
            time.sleep(0.05)
        return main._registry.store.mark_ready(model_id)

    monkeypatch.setattr(main._registry.installer, "install", fake_install)
    client = TestClient(main.app)

    start = client.post("/api/models/deepfilternet-v3/install")
    assert start.status_code == 202
    cancel = client.post("/api/models/deepfilternet-v3/install/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["install"]["status"] in {"cancelling", "cancelled", "downloading"}

    deadline = __import__("time").time() + 5
    while __import__("time").time() < deadline:
        status = client.get("/api/models/deepfilternet-v3/install/status").json()
        if status["status"] == "cancelled":
            break
        __import__("time").sleep(0.05)
    else:
        pytest.fail("Install did not reach cancelled status")

    assert started
    caps = client.get("/api/system/capabilities")
    assert caps.status_code == 200
    assert "disk_free_mb" in caps.json()["machine"]
    assert "models_used_mb" in caps.json()["machine"]


def test_cancelled_install_resets_progress(tmp_path: Path) -> None:
    store = ModelRegistry(tmp_path).store
    store.mark_progress("demo", "downloading", 0.4)
    cancelled = store.mark_cancelled("demo")
    assert cancelled.status == "cancelled"
    assert cancelled.progress == 0.0

def test_uninstall_removes_weights_and_resets_state(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    model_id = "cosyvoice-300m"
    state = registry.installer.install(model_id)
    assert state.status == "ready"
    model_dir = registry.store.model_dir(model_id)
    assert model_dir.exists()
    (model_dir / "extra.bin").write_bytes(b"x" * (2 * 1024 * 1024))

    result = registry.installer.uninstall(model_id)
    assert result["install"]["status"] == "not_installed"
    assert result["freed_mb"] > 0
    assert result["python_packages_removed"] is False
    assert not model_dir.exists()
    assert registry.store.get(model_id).status == "not_installed"


def test_list_and_clear_installed_models_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_PROJECT_DIR", str(tmp_path))
    main.PROJECT_DIR = tmp_path
    main._registry = ModelRegistry(tmp_path)
    main._install_threads.clear()
    main._install_cancel_flags.clear()

    registry = main._registry
    for model_id in ("deepfilternet-v3", "cosyvoice-300m"):
        registry.store.mark_ready(model_id)
        weight = registry.store.model_dir(model_id) / "w.bin"
        weight.write_bytes(b"x" * (2 * 1024 * 1024))

    client = TestClient(main.app)
    listed = client.get("/api/models/installed")
    assert listed.status_code == 200
    body = listed.json()
    ids = {row["id"] for row in body["models"]}
    assert "deepfilternet-v3" in ids
    assert "cosyvoice-300m" in ids
    assert sum(row["size_mb"] for row in body["models"]) >= 3.0
    assert all(row.get("size_label") for row in body["models"])
    assert all(row["can_remove"] for row in body["models"])

    cleared = client.post("/api/models/installed/clear")
    assert cleared.status_code == 200
    result = cleared.json()
    assert len(result["removed"]) >= 2
    assert result["freed_mb"] > 0

    empty = client.get("/api/models/installed").json()
    assert empty["models"] == []


def test_uninstall_api_blocks_active_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROOVY_PROJECT_DIR", str(tmp_path))
    main.PROJECT_DIR = tmp_path
    main._registry = ModelRegistry(tmp_path)
    main._install_threads.clear()
    main._install_cancel_flags.clear()

    import threading
    import time

    hold = threading.Event()

    def fake_install(model_id: str, *, cancel_check=None):
        hold.wait(timeout=5)
        return main._registry.store.mark_ready(model_id)

    monkeypatch.setattr(main._registry.installer, "install", fake_install)
    client = TestClient(main.app)
    start = client.post("/api/models/deepfilternet-v3/install")
    assert start.status_code == 202

    blocked = client.delete("/api/models/deepfilternet-v3/install")
    assert blocked.status_code == 409

    hold.set()
    deadline = time.time() + 5
    while time.time() < deadline:
        thread = main._install_threads.get("deepfilternet-v3")
        if thread is None or not thread.is_alive():
            break
        time.sleep(0.05)

    removed = client.delete("/api/models/deepfilternet-v3/install")
    assert removed.status_code == 200
    assert removed.json()["install"]["status"] == "not_installed"
