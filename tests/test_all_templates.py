from __future__ import annotations

from groovy.verify import main as verify_templates


def test_all_templates_validate() -> None:
    assert verify_templates() == 0
