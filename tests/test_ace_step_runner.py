"""ACE-Step Hub auth helpers — do not treat '401' substrings as access errors."""

from __future__ import annotations

import pytest

from groovy.nodes.ai.backends.ace_step_runner import (
    LORA_HF_BY_ID,
    _hf_token_arg,
    _is_hf_access_denied,
    _raise_hf_load_error,
    _refuse_cpu_if_low_ram,
    _resolve_lora_repo,
    _sanitize_hf_error,
    _unload_lora,
)


class _HttpError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_hf_token_arg_is_anonymous_when_unset() -> None:
    assert _hf_token_arg(None) is False
    assert _hf_token_arg("") is False
    assert _hf_token_arg("hf_test_not_a_real_token") == "hf_test_not_a_real_token"


def test_access_denied_does_not_match_401_substring() -> None:
    assert not _is_hf_access_denied(RuntimeError("cache blob ff401931-037c"))
    assert not _is_hf_access_denied(OSError("No space left on device"))
    assert not _is_hf_access_denied(RuntimeError("404 Client Error: Not Found"))


def test_access_denied_matches_real_hub_auth() -> None:
    assert _is_hf_access_denied(_HttpError("401 Client Error: Unauthorized", 401))
    assert _is_hf_access_denied(RuntimeError("403 Client Error: Forbidden"))
    assert _is_hf_access_denied(RuntimeError("Cannot access gated repo for url …"))


def test_sanitize_redacts_hf_tokens() -> None:
    cleaned = _sanitize_hf_error("Bearer hf_test_not_a_real_token failed")
    assert "hf_test_not_a_real_token" not in cleaned
    assert "hf_[redacted]" in cleaned


def test_non_auth_load_error_keeps_hub_detail() -> None:
    try:
        _raise_hf_load_error(
            "ACE-Step/acestep-v15-xl-turbo-diffusers",
            OSError("We couldn't connect to 'https://huggingface.co' to load this model"),
        )
    except RuntimeError as exc:
        assert "Failed to load ACE-Step" in str(exc)
        assert "couldn't connect" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_refuse_cpu_low_ram_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROOVY_ACE_STEP_ALLOW_LOW_RAM", raising=False)
    monkeypatch.setenv("GROOVY_ACE_STEP_MIN_RAM_GB", "12")
    monkeypatch.setattr(
        "groovy.nodes.ai.backends.ace_step_runner._available_ram_gb",
        lambda: 6.0,
    )
    with pytest.raises(RuntimeError, match="available RAM"):
        _refuse_cpu_if_low_ram("Runware/acestep-v15-sft-diffusers")


def test_refuse_cpu_allows_typical_macbook_headroom(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROOVY_ACE_STEP_ALLOW_LOW_RAM", raising=False)
    monkeypatch.delenv("GROOVY_ACE_STEP_MIN_RAM_GB", raising=False)
    monkeypatch.setattr(
        "groovy.nodes.ai.backends.ace_step_runner._available_ram_gb",
        lambda: 13.2,
    )
    _refuse_cpu_if_low_ram("Runware/acestep-v15-sft-diffusers")


def test_refuse_cpu_low_ram_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOVY_ACE_STEP_ALLOW_LOW_RAM", "1")
    monkeypatch.setattr(
        "groovy.nodes.ai.backends.ace_step_runner._available_ram_gb",
        lambda: 2.0,
    )
    _refuse_cpu_if_low_ram("Runware/acestep-v15-sft-diffusers")


def test_resolve_lora_repo_known_id_and_hub_path() -> None:
    assert _resolve_lora_repo("ace-step-cny-lora") == LORA_HF_BY_ID["ace-step-cny-lora"]
    assert _resolve_lora_repo("ace-step-ambient-lora") == LORA_HF_BY_ID["ace-step-ambient-lora"]
    assert (
        _resolve_lora_repo("ACE-Step/ACE-Step-v1.5-chinese-new-year-LoRA")
        == "ACE-Step/ACE-Step-v1.5-chinese-new-year-LoRA"
    )


def test_resolve_lora_repo_unknown_raises() -> None:
    with pytest.raises(RuntimeError, match="Unknown ACE-Step LoRA"):
        _resolve_lora_repo("not-a-real-lora-id")


def test_unload_lora_tolerates_missing_hooks() -> None:
    class _Bare:
        pass

    _unload_lora(_Bare())  # no-op; must not raise
