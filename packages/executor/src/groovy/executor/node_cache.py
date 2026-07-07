from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_node_signature(node_type: str, widgets: dict[str, Any], kwargs: dict[str, Any]) -> str:
    refs: dict[str, Any] = {}
    for key, value in sorted(kwargs.items()):
        if hasattr(value, "id"):
            refs[key] = str(value.id)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            refs[key] = value
    payload = {
        "type": node_type,
        "widgets": widgets,
        "refs": refs,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
