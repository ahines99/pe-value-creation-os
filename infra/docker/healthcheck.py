"""Container health check for the pvc image (PVC-130).

One image serves several roles, so the check inspects the running command line:

- approval API (``pe_value_os.api.app``): ``GET /healthz`` must return 200.
- MCP server (``pe_value_os.mcp_server``): ``GET /mcp`` must get any HTTP answer below 500. Outside dev the
  endpoint requires a bearer token, so a healthy server answers 401.
- anything else (``pvc worker``, migrations, role bootstrap): no HTTP surface, so the check passes.

``PVC_HEALTHCHECK_URL`` overrides detection; ``PVC_HEALTHCHECK_EXPECT`` is then the accepted status
("200" by default, or "<500").
Standard library only; exits 0 when healthy and 1 otherwise.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
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
            return f"http://127.0.0.1:{_port(argv, 8080)}/healthz", "200"
        if "pe_value_os.mcp_server" in joined:
            return f"http://127.0.0.1:{_port(argv, 8000)}/mcp", "<500"
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
        return 0
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


if __name__ == "__main__":
    sys.exit(main())
