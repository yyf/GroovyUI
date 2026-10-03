from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from groovy.registry.models import ModelManifest


class ModelCatalog:
    def __init__(self, catalog_path: Path | None = None, overlay_path: Path | None = None) -> None:
        if catalog_path is None:
            catalog_path = Path(resources.files("groovy.registry")) / "seed.json"
        self._catalog_path = Path(catalog_path)
        self._overlay_path = Path(overlay_path) if overlay_path else None
        self._seed_mtime: float | None = None
        self._overlay_mtime: float | None = None
        self._models: dict[str, ModelManifest] = {}
        self._load()

    def _path_mtime(self, path: Path | None) -> float | None:
        if path is None or not path.exists():
            return None
        return path.stat().st_mtime

    def _load(self) -> None:
        data = json.loads(self._catalog_path.read_text())
        self._models = {
            item["id"]: ModelManifest.model_validate(item) for item in data["models"]
        }
        if self._overlay_path and self._overlay_path.exists():
            overlay = json.loads(self._overlay_path.read_text())
            for item in overlay.get("models", []):
                self._models[item["id"]] = ModelManifest.model_validate(item)
        self._seed_mtime = self._path_mtime(self._catalog_path)
        self._overlay_mtime = self._path_mtime(self._overlay_path)

    def _reload_if_stale(self) -> None:
        """Pick up seed.json / overlay edits without restarting the API (dev ergonomics)."""
        if self._path_mtime(self._catalog_path) != self._seed_mtime:
            self._load()
            return
        if self._path_mtime(self._overlay_path) != self._overlay_mtime:
            self._load()

    def all(self, *, include_drafts: bool = False) -> list[ModelManifest]:
        self._reload_if_stale()
        return sorted(
            [m for m in self._models.values() if include_drafts or m.status == "published"],
            key=lambda m: m.name.lower(),
        )

    def get(self, model_id: str) -> ModelManifest | None:
        self._reload_if_stale()
        return self._models.get(model_id)

    def search(
        self,
        query: str = "",
        *,
        task_type: str | None = None,
        commercial_ok: bool | None = None,
        node_type: str | None = None,
    ) -> list[ModelManifest]:
        self._reload_if_stale()
        q = query.strip().lower()
        results: list[tuple[int, ModelManifest]] = []
        for model in self._models.values():
            if model.status != "published":
                continue
            if task_type and task_type not in model.task_types:
                continue
            if commercial_ok is not None and model.license.commercial_ok != commercial_ok:
                continue
            if node_type and node_type not in model.compatible_nodes:
                continue
            score = self._score(model, q)
            if q and score == 0:
                continue
            results.append((score, model))
        results.sort(key=lambda item: (-item[0], item[1].name.lower()))
        return [m for _, m in results]

    def similar(self, model_id: str, *, commercial_ok: bool | None = None, limit: int = 4) -> list[ModelManifest]:
        """Return seed ``similar_models`` first, then rank peers by task/tag/node/VRAM overlap."""
        model = self.get(model_id)
        if not model:
            return []
        seen = {model_id}
        ranked: list[ModelManifest] = []
        for similar_id in model.similar_models:
            if similar_id in seen:
                continue
            candidate = self.get(similar_id)
            if not candidate or candidate.status != "published":
                continue
            if commercial_ok is not None and candidate.license.commercial_ok != commercial_ok:
                continue
            ranked.append(candidate)
            seen.add(similar_id)
            if len(ranked) >= limit:
                return ranked

        scored: list[tuple[int, ModelManifest]] = []
        for candidate in self.all():
            if candidate.id in seen:
                continue
            score = self._similar_score(model, candidate)
            # Require shared task or compatible node — avoid weak VRAM/author-only matches.
            if score < 6:
                continue
            if commercial_ok is not None and candidate.license.commercial_ok != commercial_ok:
                continue
            scored.append((score, candidate))
        scored.sort(key=lambda item: (-item[0], item[1].name.lower()))
        for _, candidate in scored:
            ranked.append(candidate)
            if len(ranked) >= limit:
                break
        return ranked

    def _similar_score(self, source: ModelManifest, candidate: ModelManifest) -> int:
        score = 0
        shared_tasks = set(source.task_types) & set(candidate.task_types)
        if shared_tasks:
            score += 8 * len(shared_tasks)
        shared_nodes = set(source.compatible_nodes) & set(candidate.compatible_nodes)
        if shared_nodes:
            score += 6 * len(shared_nodes)
        shared_tags = set(source.tags) & set(candidate.tags)
        if shared_tags:
            score += 2 * min(len(shared_tags), 4)
        if source.author and source.author == candidate.author:
            score += 2
        if candidate.vram_gb_estimate <= source.vram_gb_estimate:
            score += 1
        if abs(candidate.vram_gb_estimate - source.vram_gb_estimate) <= 2:
            score += 1
        return score

    def _score(self, model: ModelManifest, query: str) -> int:
        if not query:
            return 1
        haystack = " ".join(
            [
                model.id,
                model.name,
                model.description,
                " ".join(model.tags),
                " ".join(model.task_types),
                model.author,
            ]
        ).lower()
        if query in haystack:
            return 10
        tokens = query.split()
        return sum(2 for token in tokens if token in haystack)
