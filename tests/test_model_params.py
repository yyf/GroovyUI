from __future__ import annotations

from groovy.nodes.ai.model_params import bool_param, float_param, int_param, optional_frequency
from groovy.registry.catalog import ModelCatalog


def test_optional_frequency_treats_zero_as_auto() -> None:
    assert optional_frequency({"minimum_frequency": 0}, "minimum_frequency") is None
    assert optional_frequency({"minimum_frequency": 220.0}, "minimum_frequency") == 220.0


def test_bool_param_parses_strings() -> None:
    assert bool_param({"melodia_trick": "true"}, "melodia_trick", False) is True
    assert bool_param({"melodia_trick": "off"}, "melodia_trick", True) is False


def test_catalog_basic_pitch_inference_params() -> None:
    manifest = ModelCatalog().get("basic-pitch")
    assert manifest is not None
    names = {param.name for param in manifest.inference_params}
    assert "onset_threshold" in names
    assert "melodia_trick" in names


def test_catalog_musicgen_melody_inference_params() -> None:
    manifest = ModelCatalog().get("musicgen-melody-small")
    assert manifest is not None
    names = {param.name for param in manifest.inference_params}
    assert "max_new_tokens" in names
    assert "guidance_scale" in names


def test_catalog_demucs_inference_params() -> None:
    manifest = ModelCatalog().get("demucs-v4")
    assert manifest is not None
    names = {param.name for param in manifest.inference_params}
    assert "shifts" in names
    assert "overlap" in names
    assert manifest.install.dev_stub is False


def test_param_helpers_defaults() -> None:
    assert float_param({}, "onset_threshold", 0.5) == 0.5
    assert int_param({}, "max_new_tokens", 512) == 512
