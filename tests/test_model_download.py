from __future__ import annotations

import pytest
from groovy.registry.download import DownloadError, assert_allowed_url


def test_allowlisted_host() -> None:
    assert_allowed_url("https://huggingface.co/org/model/resolve/main/weights.bin")


def test_blocked_host() -> None:
    with pytest.raises(DownloadError):
        assert_allowed_url("https://evil.example.com/model.bin")
