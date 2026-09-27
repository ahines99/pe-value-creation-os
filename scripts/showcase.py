"""Start, seed or stop an isolated, local-only synthetic showcase using Docker Compose."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "var" / "local-showcase"
PROJECT = "pvc-showcase"
SEED = """
import json, uuid
from pe_value_os.app import build_context
from pe_value_os.security import principal_scope, system_principal
from pe_value_os.workflows.primary import start
ctx = build_context()
result = {}
for company in ('beacon-pricing', 'delta-broken'):
    with principal_scope(system_principal(company)):
        ctx.repo.upsert_company(ctx.adapter.load(company).profile)
        ctx.adapter.load(company, sink=ctx.repo)
        run, _ = start(ctx, company, 'human:showcase',
            idempotency_key='showcase-' + str(uuid.uuid4()), params={'mode': 'automated'})
        result[company] = run.run_id
print(json.dumps(result))
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "seed", "down", "reset"])
    parser.add_argument("--observability", action="store_true", help="Start local metrics, traces and Grafana")
    parser.add_argument("--confirm-reset", help="Must equal pvc-showcase to erase this project's synthetic volumes")
    args = parser.parse_args()
    docker = shutil.which("docker")
    if not docker and os.name == "nt":
        candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/DockerDesktop/resources/bin/docker.exe"
        if candidate.exists():
            docker = str(candidate)
    if not docker:
        parser.error("Docker was not found. Install/start Docker Desktop, then reopen your terminal.")
    STATE.mkdir(parents=True, exist_ok=True)
    config = STATE / "settings.json"
    if not config.exists():
        config.write_text(json.dumps({"token": secrets.token_urlsafe(24)}), encoding="utf-8")
    settings = json.loads(config.read_text(encoding="utf-8"))
    token = settings["token"]
    claims = {
        token: {
            "sub": "human:showcase",
            "pvc_companies": ["beacon-pricing", "delta-broken"],
            "pvc_roles": ["approver"],
            "pvc_principal_type": "human",
            "scope": "pvc.read pvc.approve",
        }
    }
    env = {
        **os.environ,
        "PATH": str(Path(docker).parent) + os.pathsep + os.environ.get("PATH", ""),
        "PVC_ENV_FILE": "var/local-showcase/runtime.env",
        "PVC_DB_PORT": "54332",
        "PVC_MCP_PORT": "18001",
        "PVC_API_PORT": "18081",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel-collector:4318" if args.observability else "",
    }
    runtime = (ROOT / ".env.example").read_text(encoding="utf-8")
    overrides = {
        "PVC_ENV": "dev",
        "PVC_PROPOSER": "rules",
        "PVC_DEV_TOKENS": "'" + json.dumps(claims) + "'",
        "PVC_WORKER_COMPANIES": "beacon-pricing,delta-broken",
        "PVC_ALLOWED_COMPANIES": "beacon-pricing,delta-broken",
        "PVC_MCP_RESOURCE_URL": "http://localhost:18001/mcp",
    }
    lines = [line for line in runtime.splitlines() if line.split("=", 1)[0] not in overrides]
    lines.extend(f"{key}={value}" for key, value in overrides.items())
    (STATE / "runtime.env").write_text("\n".join(lines) + "\n", encoding="utf-8")
    command = [docker, "compose", "--project-name", PROJECT]

    def compose(*parts: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run([*command, *parts], cwd=ROOT, env=env, check=True, text=True, capture_output=capture)

    if args.action in {"down", "reset"}:
        if args.action == "reset" and args.confirm_reset != PROJECT:
            parser.error("Reset deletes only pvc-showcase synthetic volumes; pass --confirm-reset pvc-showcase")
        parts = ["--profile", "observability", "down"]
        if args.action == "reset":
            parts.append("--volumes")
        compose(*parts)
        print("Showcase stopped." if args.action == "down" else "Synthetic showcase volumes reset.")
        return
    if args.action == "up":
        parts = ["--profile", "observability"] if args.observability else []
        compose(*parts, "up", "--build", "--wait", "--wait-timeout", "180")
    result = compose("exec", "-T", "mcp", "python", "-c", SEED, capture=True)
    runs = json.loads(result.stdout.splitlines()[-1])
    (STATE / "runs.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")
    for company, run_id in runs.items():
        wanted = "awaiting_approval" if company == "beacon-pricing" else "needs_evidence"
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            request = Request(f"http://localhost:18081/runs/{run_id}", headers={"Authorization": f"Bearer {token}"})
            with urlopen(request, timeout=10) as response:  # noqa: S310 - fixed loopback URL
                status = json.load(response)["status"]
            if status == wanted:
                break
            if status in {"failed", "complete", "rejected"}:
                raise RuntimeError(f"{company}: unexpected terminal status {status}")
            time.sleep(2)
        else:
            raise TimeoutError(f"{company} did not reach {wanted}")
    print("\nOpen http://localhost:18081/\nLocal approver token:", token)
    print("Beacon is ready for review; Delta demonstrates a controlled pause. All data is fictional.")
    print("Stop: python scripts/showcase.py down\nNew review runs: python scripts/showcase.py seed")


if __name__ == "__main__":
    main()
