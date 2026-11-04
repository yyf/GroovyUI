"""Lightweight eval fixture manifest (JSONL-shaped) for future batch runners.

v1 only defines the schema helpers — Studio batch UI / ``groovy-eval`` CLI can
consume the same records later. Demo templates still use in-graph Prompt refs.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvalItem:
    """One fixture row: optional audio path + reference text (ASR / MT / etc.)."""

    id: str
    reference_text: str = ""
    audio: str | None = None
    language: str = "en"
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def load_eval_manifest(path: Path | str) -> list[EvalItem]:
    """Load JSONL (one EvalItem per line) or a JSON list."""
    file_path = Path(path)
    raw = file_path.read_text(encoding="utf-8")
    rows: list[Any]
    stripped = raw.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        rows = json.loads(stripped)
    else:
        rows = [json.loads(line) for line in stripped.splitlines() if line.strip()]
    items: list[EvalItem] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"Eval manifest rows must be objects, got {type(row).__name__}")
        item_id = str(row.get("id") or "").strip()
        if not item_id:
            raise ValueError("Eval manifest row missing id")
        tags = row.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
        items.append(
            EvalItem(
                id=item_id,
                reference_text=str(row.get("reference_text") or row.get("text") or ""),
                audio=(str(row["audio"]) if row.get("audio") else None),
                language=str(row.get("language") or "en"),
                tags=[str(tag) for tag in tags],
                meta=dict(meta),
            )
        )
    return items


def dump_eval_manifest(items: list[EvalItem], path: Path | str) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item.to_dict(), ensure_ascii=False) for item in items]
    file_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
