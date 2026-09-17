"""Published seed catalog quality gates for Core / model-request PRs."""

from __future__ import annotations

from groovy.registry.catalog import ModelCatalog

# Hero / cold-machine gate models — must stay real installs (not stubs).
HERO_MODEL_IDS = (
    "deepfilternet-v3",
    "demucs-v4",
    "whisper-large-v3-turbo",
    "basic-pitch",
    "musicgen-melody-small",
    "kokoro-82m",
)


def _is_ci_fixture(manifest) -> bool:
    tags = {t.lower() for t in (manifest.tags or [])}
    tasks = {t.lower() for t in (manifest.task_types or [])}
    return "ci" in tags or "verification" in tasks or manifest.id.startswith("groovy-verify-")


def test_published_installable_entries_have_required_fields() -> None:
    catalog = ModelCatalog()
    for manifest in catalog.all():
        if manifest.status != "published":
            continue
        if manifest.install.dev_stub:
            continue
        assert manifest.id.strip(), "empty model id"
        assert len((manifest.description or "").strip()) >= 20, manifest.id
        assert manifest.task_types, manifest.id
        assert manifest.license.spdx.strip(), manifest.id
        if not _is_ci_fixture(manifest):
            assert manifest.compatible_nodes, f"{manifest.id} missing compatible_nodes"
        payload = manifest.install.model_dump()
        assert payload.get("weights") or payload.get("python_deps") or payload.get(
            "install_script"
        ), f"{manifest.id} missing install payload"


def test_hero_models_are_published_non_stub() -> None:
    catalog = ModelCatalog()
    for model_id in HERO_MODEL_IDS:
        manifest = catalog.get(model_id)
        assert manifest is not None, model_id
        assert manifest.status == "published", model_id
        assert manifest.install.dev_stub is False, model_id
        assert manifest.compatible_nodes, model_id
        assert manifest.license.spdx, model_id


def test_stubs_do_not_block_catalog_load() -> None:
    catalog = ModelCatalog()
    stubs = [m.id for m in catalog.all() if m.install.dev_stub]
    assert stubs, "expected some stub placeholders until curated"
    for model_id in stubs:
        assert catalog.get(model_id) is not None
