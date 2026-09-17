"""Tests for portable bundle path resolution and studio static mount."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_resolve_bundle_root_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from groovy.server.paths import resolve_bundle_root

    monkeypatch.setenv("GROOVY_BUNDLE_ROOT", str(tmp_path))
    assert resolve_bundle_root() == tmp_path.resolve()


def test_looks_like_bundle_and_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from groovy.server.paths import looks_like_bundle, resolve_bundle_root

    studio = tmp_path / "studio"
    studio.mkdir()
    (studio / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "templates").mkdir()
    assert looks_like_bundle(tmp_path)
    monkeypatch.delenv("GROOVY_BUNDLE_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    assert resolve_bundle_root() == tmp_path.resolve()


def test_resolve_studio_dir_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from groovy.server.paths import resolve_studio_dir

    studio = tmp_path / "ui"
    studio.mkdir()
    (studio / "index.html").write_text("<html>studio</html>", encoding="utf-8")
    monkeypatch.setenv("GROOVY_STUDIO_DIR", str(studio))
    assert resolve_studio_dir() == studio.resolve()


def test_resolve_studio_dir_requires_serve_or_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from groovy.server.paths import resolve_studio_dir

    monkeypatch.delenv("GROOVY_STUDIO_DIR", raising=False)
    monkeypatch.delenv("GROOVY_SERVE_STUDIO", raising=False)
    monkeypatch.delenv("GROOVY_BUNDLE_ROOT", raising=False)
    studio = tmp_path / "studio"
    studio.mkdir()
    (studio / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "templates").mkdir()
    # Bundle layout alone is enough
    assert resolve_studio_dir(tmp_path) == studio.resolve()


def test_resolve_default_project_dir_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from groovy.server.paths import resolve_default_project_dir

    monkeypatch.delenv("GROOVY_PROJECT_DIR", raising=False)
    assert resolve_default_project_dir(tmp_path) == (tmp_path / "workspace").resolve()


def test_studio_static_mount_serves_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    studio = tmp_path / "studio"
    studio.mkdir()
    (studio / "index.html").write_text("<html>portable-ok</html>", encoding="utf-8")
    monkeypatch.setenv("GROOVY_STUDIO_DIR", str(studio))
    monkeypatch.setenv("GROOVY_PROJECT_DIR", str(tmp_path / "workspace"))

    import groovy.server.main as main

    mounted = main._mount_studio_static()
    assert mounted is not None
    assert mounted == studio.resolve()

    client = TestClient(main.app)
    res = client.get("/")
    assert res.status_code == 200
    assert "portable-ok" in res.text
    # API still reachable
    health = client.get("/api/health")
    assert health.status_code == 200
