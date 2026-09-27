"""Container health check for the pvc image (PVC-130).

One image serves several roles, so the check inspects the running command line:

- approval API and MCP server: ``GET /readyz`` must return 200 after dependency checks.
- worker: a live process must have published a recent successful database heartbeat.
- explicit one-off migration/bootstrap commands: no long-running health requirement.
- unrecognized or missing service process: fail closed.

``PVC_HEALTHCHECK_URL`` overrides detection; ``PVC_HEALTHCHECK_EXPECT`` is then the accepted status
("200" by default, or "<500").
Standard library only; exits 0 when healthy and 1 otherwise.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

TIMEOUT_S = 4.0


def _cmdlines() -> list[list[str]]:
    out = []
    for p in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if raw:
            out.append([a.decode(errors="replace") for a in raw.split(b"\0") if a])
    return out


def _port(argv: list[str], default: int) -> int:
    for i, arg in enumerate(argv):
        if arg == "--port" and i + 1 < len(argv):
            return int(argv[i + 1])
        if arg.startswith("--port="):
            return int(arg.split("=", 1)[1])
    return default


def _target() -> tuple[str, str] | None:
    url = os.environ.get("PVC_HEALTHCHECK_URL")
    if url:
        return url, os.environ.get("PVC_HEALTHCHECK_EXPECT", "200")
    for argv in _cmdlines():
        joined = " ".join(argv)
        if "pe_value_os.api.app" in joined:
            return f"http://127.0.0.1:{_port(argv, 8080)}/readyz", "200"
        if "pe_value_os.mcp_server" in joined:
            return f"http://127.0.0.1:{_port(argv, 8000)}/readyz", "200"
    return None


def _status(url: str) -> int:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"unsupported health check URL scheme: {url}")
    headers = {"Accept": "application/json, text/event-stream"}
    req = urllib.request.Request(url, method="GET", headers=headers)  # noqa: S310 - scheme checked above
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 - scheme checked above
            return int(resp.status)
    except urllib.error.HTTPError as e:
        return int(e.code)


def main() -> int:
    target = _target()
    if target is None:
        commands = _cmdlines()
        if any("worker" in argv and any(Path(a).name == "pvc" for a in argv) for argv in commands):
            return 0 if worker_ready() else 1
        if any("bootstrap_db.py" in " ".join(argv) or ("db" in argv and "upgrade" in argv) for argv in commands):
            return 0
        print("unhealthy: service process not found", file=sys.stderr)
        return 1
    url, expect = target
    try:
        status = _status(url)
    except (OSError, ValueError) as e:
        print(f"unhealthy: {url}: {e}", file=sys.stderr)
        return 1
    ok = status < 500 if expect == "<500" else status == int(expect)
    if not ok:
        print(f"unhealthy: {url} returned {status}, expected {expect}", file=sys.stderr)
    return 0 if ok else 1


def worker_ready() -> bool:
    try:
        data = json.loads(Path(os.environ.get("PVC_WORKER_HEARTBEAT_PATH", "var/worker-heartbeat")).read_text())
        pid = int(data["pid"])
        if pid <= 0:
            return False
        os.kill(pid, 0)
        stamp = data["updated_at"]
        updated = float(stamp) if isinstance(stamp, (int, float)) else datetime.fromisoformat(stamp).timestamp()
        return 0 <= time.time() - updated <= 90
    except (OSError, ValueError, KeyError, TypeError):
        return False


if __name__ == "__main__":
    sys.exit(main())
