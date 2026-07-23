from __future__ import annotations

import hashlib
import shutil
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_HOSTS = frozenset(
    {
        "huggingface.co",
        "cdn.huggingface.co",
        "github.com",
        "raw.githubusercontent.com",
    }
)

CHUNK_SIZE = 256 * 1024


class DownloadError(Exception):
    pass


class DownloadCancelled(DownloadError):
    """Raised when an install cancel check trips mid-download."""


def assert_allowed_url(url: str) -> None:
    host = urlparse(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise DownloadError(f"URL host not allowlisted: {host}")


def download_file(
    url: str,
    dest: Path,
    *,
    expected_sha256: str | None = None,
    hf_token: str | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> Path:
    assert_allowed_url(url)
    dest.parent.mkdir(parents=True, exist_ok=True)

    import urllib.request

    request = urllib.request.Request(url)
    if hf_token and "huggingface.co" in url:
        request.add_header("Authorization", f"Bearer {hf_token}")

    partial = dest.with_suffix(dest.suffix + ".partial")
    hasher = hashlib.sha256()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with partial.open("wb") as out:
                while True:
                    if cancel_check and cancel_check():
                        raise DownloadCancelled(f"Download cancelled: {url}")
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    out.write(chunk)
        digest = hasher.hexdigest()
        if expected_sha256 and digest != expected_sha256.removeprefix("sha256:"):
            raise DownloadError(f"Checksum mismatch for {url}")
        partial.replace(dest)
        return dest
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def copy_bundle_file(bundle_name: str, dest: Path, *, expected_sha256: str | None = None) -> Path:
    bundle_root = resources.files("groovy.registry") / "bundles"
    source = bundle_root / bundle_name
    if not source.is_file():
        raise DownloadError(f"Bundle not found: {bundle_name}")
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 and digest != expected_sha256.removeprefix("sha256:"):
        raise DownloadError(f"Checksum mismatch for bundle {bundle_name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    return dest
