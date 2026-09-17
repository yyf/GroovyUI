"""HF token is attached as Bearer only for huggingface.co downloads / Discover."""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest
from groovy.registry.discover import discover_models
from groovy.registry.download import download_file


class _EmptyBodyResponse:
    def __enter__(self) -> _EmptyBodyResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return b""


class _JsonListResponse:
    def __enter__(self) -> _JsonListResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return b"[]"


def test_download_file_bearer_only_for_huggingface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = "hf_test_not_a_real_token"
    seen: dict[str, str | None] = {}

    def fake_urlopen(req: urllib.request.Request, timeout: float = 120):  # noqa: ARG001
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        return _EmptyBodyResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    dest_hf = tmp_path / "weights.bin"
    download_file(
        "https://huggingface.co/org/model/resolve/main/weights.bin",
        dest_hf,
        hf_token=fake,
    )
    assert seen["auth"] == f"Bearer {fake}"
    assert dest_hf.is_file()

    dest_gh = tmp_path / "other.bin"
    download_file(
        "https://github.com/org/repo/releases/download/v1/other.bin",
        dest_gh,
        hf_token=fake,
    )
    assert seen["url"].startswith("https://github.com/")
    assert seen["auth"] is None
    assert dest_gh.is_file()


def test_discover_models_bearer_when_token_set(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = "hf_test_not_a_real_token"
    seen: dict[str, str | None] = {}

    def fake_urlopen(req: urllib.request.Request, timeout: float = 30):  # noqa: ARG001
        seen["auth"] = req.get_header("Authorization")
        return _JsonListResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert discover_models("denoise", hf_token=fake) == []
    assert seen["auth"] == f"Bearer {fake}"

    seen.clear()
    assert discover_models("denoise", hf_token=None) == []
    assert seen["auth"] is None
