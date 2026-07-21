from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from groovy.executor.content_credentials import (
    COMPOSITED_WITH_TRAINED_ALGORITHMIC_MEDIA,
    TRAINED_ALGORITHMIC_MEDIA,
    NoOpContentCredentialSigner,
    SignResult,
    VerificationResult,
    build_content_credentials_manifest,
    process_content_credentials,
)


class FakeSigner:
    def __init__(self, *, valid: bool = True) -> None:
        self.valid = valid
        self.manifest: dict[str, Any] | None = None

    def available(self) -> bool:
        return True

    def public_status(self) -> dict[str, Any]:
        return {
            "provider": "test",
            "configured": True,
            "sdk_available": True,
            "supported_formats": ["wav", "flac"],
        }

    def sign(
        self, source: Path, destination: Path, manifest: dict[str, Any]
    ) -> SignResult:
        self.manifest = manifest
        shutil.copy2(source, destination)
        return SignResult(
            manifest_id="urn:c2pa:test",
            issuer="GroovyUI test signer",
            timestamp="2026-07-20T00:00:00Z",
        )

    def verify(self, asset: Path) -> VerificationResult:
        return VerificationResult(
            valid=self.valid,
            trusted=self.valid,
            manifest_id="urn:c2pa:test",
            issuer="GroovyUI test signer",
            error=None if self.valid else "invalid claim",
        )


def test_manifest_maps_ai_generated_and_mixed_contributions() -> None:
    provenance = {
        "schema_version": "1.1.0",
        "integrity": {"record_hash": "sha256:record"},
        "origin": {"workflow_hash": "sha256:workflow"},
        "conditioning": {"prompts_redacted": True},
        "lineage": {
            "root_cache_id": "root",
            "nodes": [
                {
                    "contribution": {"class": "ai_generated"},
                    "models": [
                        {
                            "registry_id": "model-a",
                            "version": "1",
                            "weights_hash_status": "verified",
                        }
                    ],
                }
            ],
        },
    }

    manifest = build_content_credentials_manifest(
        provenance,
        title="render.wav",
        claim_generator="GroovyUI/0.1.0",
    )

    action = manifest["assertions"][0]["data"]["actions"][0]
    custom = manifest["assertions"][1]["data"]
    assert action["action"] == "c2pa.created"
    assert action["digitalSourceType"] == TRAINED_ALGORITHMIC_MEDIA
    assert custom["prompts_redacted"] is True
    assert custom["models"][0]["registry_id"] == "model-a"

    provenance["lineage"]["nodes"].append(
        {"contribution": {"class": "human_recorded"}, "models": []}
    )
    mixed = build_content_credentials_manifest(
        provenance,
        title="render.wav",
        claim_generator="GroovyUI/0.1.0",
    )
    mixed_action = mixed["assertions"][0]["data"]["actions"][0]
    assert mixed_action["action"] == "c2pa.opened"
    assert (
        mixed_action["digitalSourceType"]
        == COMPOSITED_WITH_TRAINED_ALGORITHMIC_MEDIA
    )


def test_sign_if_configured_falls_back_with_explicit_unsigned_status(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.wav"
    destination = tmp_path / "destination.wav"
    source.write_bytes(b"audio")

    result = process_content_credentials(
        signer=NoOpContentCredentialSigner(),
        mode="sign_if_configured",
        source=source,
        destination=destination,
        manifest={},
    )

    assert destination.read_bytes() == b"audio"
    assert result.status == "unconfigured"
    assert result.verified is False


def test_required_mode_fails_without_signer_and_does_not_publish(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.wav"
    destination = tmp_path / "destination.wav"
    source.write_bytes(b"audio")

    with pytest.raises(RuntimeError, match="no signer is configured"):
        process_content_credentials(
            signer=NoOpContentCredentialSigner(),
            mode="required",
            source=source,
            destination=destination,
            manifest={},
        )

    assert source.exists()
    assert not destination.exists()


def test_configured_signer_must_pass_post_sign_verification(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    destination = tmp_path / "destination.wav"
    source.write_bytes(b"audio")
    signer = FakeSigner(valid=True)

    result = process_content_credentials(
        signer=signer,
        mode="sign_if_configured",
        source=source,
        destination=destination,
        manifest={"title": "test"},
    )

    assert result.status == "signed"
    assert result.verified is True
    assert result.trusted is True
    assert not source.exists()
    assert destination.exists()

    invalid_source = tmp_path / "invalid-source.wav"
    invalid_destination = tmp_path / "invalid-destination.wav"
    invalid_source.write_bytes(b"audio")
    with pytest.raises(RuntimeError, match="verification failed"):
        process_content_credentials(
            signer=FakeSigner(valid=False),
            mode="sign_if_configured",
            source=invalid_source,
            destination=invalid_destination,
            manifest={},
        )
    assert not invalid_destination.exists()
