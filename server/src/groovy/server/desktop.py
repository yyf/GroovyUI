"""Launch GroovyUI as a portable desktop session (API + browser)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from groovy.server.paths import resolve_bundle_root, resolve_default_project_dir


def _health_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/api/health"


def _wait_healthy(host: str, port: int, *, timeout_s: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout_s
    url = _health_url(host, port)
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if 200 <= getattr(resp, "status", 200) < 300:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(0.25)
    return False


def main() -> None:
    bundle = resolve_bundle_root()
    os.environ.setdefault("GROOVY_BUNDLE_ROOT", str(bundle))
    os.environ.setdefault("GROOVY_PROJECT_DIR", str(resolve_default_project_dir(bundle)))
    os.environ.setdefault("GROOVY_SERVE_STUDIO", "1")

    host = os.environ.get("GROOVY_HOST", "127.0.0.1")
    port = int(os.environ.get("GROOVY_PORT", "8188"))
    studio_url = f"http://{host}:{port}/"

    project_dir = Path(os.environ["GROOVY_PROJECT_DIR"])
    project_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "groovy.server.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    proc = subprocess.Popen(cmd, env=os.environ.copy())

    def _shutdown(*_args: object) -> None:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        if not _wait_healthy(host, port):
            _shutdown()
            proc.wait(timeout=10)
            print(
                f"GroovyUI API did not become healthy at {_health_url(host, port)}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"GroovyUI desktop ready — {studio_url}")
        webbrowser.open(studio_url)
        raise SystemExit(proc.wait())
    except KeyboardInterrupt:
        _shutdown()
        raise SystemExit(proc.wait())


if __name__ == "__main__":
    main()
