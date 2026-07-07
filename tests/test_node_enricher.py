from __future__ import annotations

from groovy.node import get_node_class
from groovy.nodes.core import register_all as register_core
from groovy.registry.agent.node_enricher import enrich_node_schema

register_core()


def test_enrich_adds_descriptions() -> None:
    base = get_node_class("Normalize").describe()
    enriched = enrich_node_schema("Normalize", base)
    assert enriched["enriched"] is True
    assert "loudness" in enriched["description"].lower()
    assert any(widget.get("description") for widget in enriched["widgets"])


def test_enrich_unknown_node_has_fallback() -> None:
    base = get_node_class("Mix").describe()
    enriched = enrich_node_schema("Mix", base)
    assert enriched["description"]
    assert enriched["inputs"] or enriched["widgets"]
