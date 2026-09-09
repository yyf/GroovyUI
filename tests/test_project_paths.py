from pathlib import Path

import pytest

from groovy.executor.cache import CacheStore
from groovy.executor.project_paths import (
    build_media_not_found_error,
    find_media_path_suggestions,
    resolve_project_media_path,
)


@pytest.fixture
def cache(tmp_path: Path) -> CacheStore:
    samples = tmp_path / "assets" / "samples"
    uploads = tmp_path / "assets" / "uploads"
    samples.mkdir(parents=True)
    uploads.mkdir(parents=True)
    (samples / "podcast_denoise_demo.wav").write_bytes(b"RIFF")
    (samples / "Knockout_41k.wav").write_bytes(b"RIFF")
    (samples / "nested" / "dialogue.wav").parent.mkdir(parents=True)
    (samples / "nested" / "dialogue.wav").write_bytes(b"RIFF")
    return CacheStore(tmp_path)


def test_resolve_direct_project_relative_path(cache: CacheStore) -> None:
    resolved, canonical = resolve_project_media_path(cache, "assets/samples/podcast_denoise_demo.wav")
    assert resolved.name == "podcast_denoise_demo.wav"
    assert canonical == "assets/samples/podcast_denoise_demo.wav"


def test_resolve_bare_filename_in_samples(cache: CacheStore) -> None:
    resolved, canonical = resolve_project_media_path(cache, "podcast_denoise_demo.wav")
    assert resolved.name == "podcast_denoise_demo.wav"
    assert canonical == "assets/samples/podcast_denoise_demo.wav"


def test_fuzzy_hyphen_underscore_match(cache: CacheStore) -> None:
    resolved, canonical = resolve_project_media_path(cache, "assets/samples/Knockout-41k.wav")
    assert resolved.name == "Knockout_41k.wav"
    assert canonical == "assets/samples/Knockout_41k.wav"


def test_missing_file_error_is_descriptive(cache: CacheStore) -> None:
    message = build_media_not_found_error(cache, "missing.wav")
    assert "FILE_NOT_FOUND: missing.wav" in message
    assert str(cache.project_dir) in message
    assert "assets/samples" in message


def test_suggestions_find_nested_basename(cache: CacheStore) -> None:
    suggestions = find_media_path_suggestions(cache, "dialogue.wav")
    assert "assets/samples/nested/dialogue.wav" in suggestions


def test_missing_nested_path_auto_resolves_unique_basename(cache: CacheStore) -> None:
    resolved, canonical = resolve_project_media_path(cache, "dialogue.wav")
    assert canonical == "assets/samples/nested/dialogue.wav"
