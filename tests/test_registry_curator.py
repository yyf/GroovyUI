from __future__ import annotations

from pathlib import Path

import pytest

from groovy.registry.agent.curator import approve_draft, ingest_drafts, list_drafts
from groovy.registry.catalog import ModelCatalog


def test_ingest_creates_drafts(tmp_path: Path) -> None:
    draft_dir = tmp_path / "drafts"
    result = ingest_drafts(draft_dir, skip_existing=False)
    assert len(result["created"]) >= 3
    drafts = list_drafts(draft_dir)
    assert all(item["status"] == "draft" for item in drafts)


def test_approve_publishes_to_overlay(tmp_path: Path) -> None:
    draft_dir = tmp_path / "drafts"
    overlay_path = tmp_path / "catalog_overlay.json"
    ingest_drafts(draft_dir, skip_existing=False)
    draft_id = list_drafts(draft_dir)[0]["id"]
    manifest = approve_draft(draft_dir, overlay_path, draft_id)
    assert manifest.status == "published"
    assert not (draft_dir / f"{draft_id}.json").exists()
    catalog = ModelCatalog(overlay_path=overlay_path)
    assert catalog.get(draft_id) is not None


def test_approve_missing_draft_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        approve_draft(tmp_path / "drafts", tmp_path / "overlay.json", "missing-id")
