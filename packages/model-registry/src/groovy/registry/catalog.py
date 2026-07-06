from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from groovy.registry.models import ModelManifest


class ModelCatalog:
    def __init__(self, catalog_path: Path | None = None) -> None:
        if catalog_path is None:
            catalog_path = Path(resources.files("groovy.registry")) / "seed.json"
        data = json.loads(catalog_path.read_text())
        self._models: dict[str, ModelManifest] = {
            item["id"]: ModelManifest.model_validate(item) for item in data["models"]
        }

    def all(self) -> list[ModelManifest]:
        return sorted(self._models.values(), key=lambda m: m.name.lower())

    def get(self, model_id: str) -> ModelManifest | None:
        return self._models.get(model_id)

    def search(
        self,
        query: str = "",
        *,
        task_type: str | None = None,
        commercial_ok: bool | None = None,
        node_type: str | None = None,
    ) -> list[ModelManifest]:
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

    def similar(self, model_id: str, *, commercial_ok: bool | None = None) -> list[ModelManifest]:
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
        return ranked

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
