from __future__ import annotations

import importlib.util
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

ContentCredentialsMode = Literal["off", "sign_if_configured", "required"]

TRAINED_ALGORITHMIC_MEDIA = (
    "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
)
COMPOSITED_WITH_TRAINED_ALGORITHMIC_MEDIA = (
    "http://cv.iptc.org/newscodes/digitalsourcetype/"
    "compositedWithTrainedAlgorithmicMedia"
)


@dataclass(frozen=True)
class SignResult:
    manifest_id: str
    issuer: str | None = None
    timestamp: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    trusted: bool | None = None
    manifest_id: str | None = None
    issuer: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ContentCredentialResult:
    status: Literal["off", "unconfigured", "signed"]
    mode: ContentCredentialsMode
    verified: bool
    trusted: bool | None = None
    manifest_id: str | None = None
    issuer: str | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContentCredentialSigner(Protocol):
    def available(self) -> bool: ...

    def public_status(self) -> dict[str, Any]: ...

    def sign(
        self,
        source: Path,
        destination: Path,
        manifest: dict[str, Any],
    ) -> SignResult: ...

    def verify(self, asset: Path) -> VerificationResult: ...


class NoOpContentCredentialSigner:
    def available(self) -> bool:
        return False

    def public_status(self) -> dict[str, Any]:
        return {
            "provider": "none",
            "configured": False,
            "sdk_available": c2pa_sdk_available(),
            "supported_formats": ["wav", "flac"],
        }

    def sign(
        self,
        source: Path,
        destination: Path,
        manifest: dict[str, Any],
    ) -> SignResult:
        raise RuntimeError("No Content Credentials signer is configured.")

    def verify(self, asset: Path) -> VerificationResult:
        return VerificationResult(valid=False, error="No signer is configured.")


def c2pa_sdk_available() -> bool:
    return importlib.util.find_spec("c2pa") is not None


def normalize_content_credentials_mode(value: str) -> ContentCredentialsMode:
    normalized = value.strip().lower()
    if normalized in {"sign_if_configured", "required"}:
        return normalized
    return "off"


def build_content_credentials_manifest(
    provenance: dict[str, Any],
    *,
    title: str,
    claim_generator: str,
) -> dict[str, Any]:
    lineage_nodes = provenance.get("lineage", {}).get("nodes") or []
    if not lineage_nodes:
        lineage_nodes = [provenance]
    classes = {
        str(node.get("contribution", {}).get("class") or "unknown")
        for node in lineage_nodes
    }
    if "ai_generated" in classes and not classes.intersection(
        {"human_recorded", "human_edited", "mixed"}
    ):
        action = "c2pa.created"
        digital_source_type = TRAINED_ALGORITHMIC_MEDIA
    elif classes.intersection({"ai_generated", "ai_transformed", "mixed"}):
        action = "c2pa.opened"
        digital_source_type = COMPOSITED_WITH_TRAINED_ALGORITHMIC_MEDIA
    else:
        action = "c2pa.opened"
        digital_source_type = (
            "http://cv.iptc.org/newscodes/digitalsourcetype/digitalCreation"
        )

    models: dict[str, dict[str, Any]] = {}
    for node in lineage_nodes:
        for model in node.get("models") or []:
            model_id = str(model.get("registry_id") or "")
            if model_id:
                models[model_id] = {
                    "registry_id": model_id,
                    "version": model.get("version"),
                    "weights_hash_status": model.get("weights_hash_status"),
                }

    custom_assertion = {
        "schema_version": provenance.get("schema_version"),
        "record_hash": provenance.get("integrity", {}).get("record_hash"),
        "workflow_hash": provenance.get("origin", {}).get("workflow_hash"),
        "contribution_classes": sorted(classes),
        "models": list(models.values()),
        "prompts_redacted": provenance.get("conditioning", {}).get(
            "prompts_redacted", True
        ),
        "lineage_root": provenance.get("lineage", {}).get("root_cache_id")
        or provenance.get("cache_id"),
    }
    return {
        "title": title,
        "claim_generator_info": [{"name": claim_generator}],
        "assertions": [
            {
                "label": "c2pa.actions.v2",
                "data": {
                    "actions": [
                        {
                            "action": action,
                            "digitalSourceType": digital_source_type,
                            "softwareAgent": claim_generator,
                        }
                    ]
                },
            },
            {
                "label": "org.groovyui.provenance.v1",
                "data": custom_assertion,
            },
        ],
    }


def process_content_credentials(
    *,
    signer: ContentCredentialSigner,
    mode: ContentCredentialsMode,
    source: Path,
    destination: Path,
    manifest: dict[str, Any],
) -> ContentCredentialResult:
    if mode == "off":
        source.replace(destination)
        return ContentCredentialResult(
            status="off",
            mode=mode,
            verified=False,
        )

    if not signer.available():
        if mode == "required":
            raise RuntimeError(
                "Content Credentials are required, but no signer is configured."
            )
        source.replace(destination)
        return ContentCredentialResult(
            status="unconfigured",
            mode=mode,
            verified=False,
        )

    signed = signer.sign(source, destination, manifest)
    if not destination.is_file():
        raise RuntimeError("Content Credentials signer did not produce an output file.")
    verification = signer.verify(destination)
    if not verification.valid:
        destination.unlink(missing_ok=True)
        raise RuntimeError(
            f"Content Credentials verification failed: "
            f"{verification.error or 'unknown error'}"
        )
    source.unlink(missing_ok=True)
    return ContentCredentialResult(
        status="signed",
        mode=mode,
        verified=True,
        trusted=verification.trusted,
        manifest_id=verification.manifest_id or signed.manifest_id,
        issuer=verification.issuer or signed.issuer,
        timestamp=signed.timestamp,
    )
