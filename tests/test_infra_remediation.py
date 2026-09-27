"""Behavioral regressions for deployment promotion, service health and load gates."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_idle_database_connection_is_replaced_after_server_termination(pg_database, tmp_path):
    import psycopg

    from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
    from pe_value_os.adapters.postgres import PostgresRepository
    from pe_value_os.security import principal_scope, system_principal

    admin_url, app_url = pg_database
    repo = PostgresRepository(app_url, FileSystemEvidenceStore(tmp_path / "ev"), min_size=1, max_size=1)
    try:
        with principal_scope(system_principal("beacon-pricing")):
            before = repo.list_runs()
        with repo.pool.connection() as conn:
            pid = conn.info.backend_pid
        with psycopg.connect(admin_url, autocommit=True) as admin:
            assert admin.execute("select pg_terminate_backend(%s, 5000)", (pid,)).fetchone()[0]
        with principal_scope(system_principal("beacon-pricing")):
            assert repo.list_runs() == before
        with repo.pool.connection() as conn:
            assert conn.info.backend_pid != pid
    finally:
        repo.close()


def load_script(path: str):
    spec = importlib.util.spec_from_file_location(Path(path).stem, ROOT / path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def health():
    return load_script("infra/docker/healthcheck.py")


def test_dependency_readiness_fails_on_unavailable_database(health, monkeypatch):
    monkeypatch.delenv("PVC_HEALTHCHECK_URL", raising=False)
    monkeypatch.setattr(health, "_cmdlines", lambda: [["uvicorn", "pe_value_os.mcp_server:app"]])
    assert health._target() == ("http://127.0.0.1:8000/readyz", "200")
    monkeypatch.setattr(health, "_status", lambda url: 503)
    assert health.main() == 1
    monkeypatch.setattr(health, "_status", lambda url: 401)
    assert health.main() == 1
    monkeypatch.setattr(health, "_status", lambda url: 200)
    assert health.main() == 0


def test_worker_requires_recent_successful_heartbeat(health, tmp_path, monkeypatch):
    heartbeat = tmp_path / "heartbeat"
    monkeypatch.setenv("PVC_WORKER_HEARTBEAT_PATH", str(heartbeat))
    monkeypatch.delenv("PVC_HEALTHCHECK_URL", raising=False)
    monkeypatch.setattr(health, "_cmdlines", lambda: [["/app/.venv/bin/pvc", "worker"]])
    monkeypatch.setattr(health.os, "kill", lambda pid, signal: None)
    assert health.main() == 1
    heartbeat.write_text(json.dumps({"pid": 42, "updated_at": time.time()}))
    assert health.main() == 0
    heartbeat.write_text(json.dumps({"pid": 42, "updated_at": time.time() - 91}))
    assert health.main() == 1
    heartbeat.write_text(json.dumps({"pid": 42, "updated_at": time.time() + 100}))
    assert health.main() == 1
    heartbeat.write_text("invalid")
    assert health.main() == 1


def test_absent_worker_process_is_unhealthy(health, monkeypatch):
    monkeypatch.delenv("PVC_HEALTHCHECK_URL", raising=False)
    monkeypatch.setattr(health, "_cmdlines", lambda: [])
    assert health.main() == 1


def test_load_step_slo_is_an_enforced_gate(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    load = load_script("scripts/load_test.py")
    assert load.check_step_latency([1, 2, 3]) == 3
    with pytest.raises(AssertionError, match="exceeds"):
        load.check_step_latency([1, 2, 5.1])
    with pytest.raises(AssertionError, match="no completed"):
        load.check_step_latency([])


@pytest.fixture
def deploy_stub(tmp_path):
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = str(git_bash) if sys.platform == "win32" and git_bash.exists() else shutil.which("bash")
    if not bash:
        pytest.skip("bash required for deployment script regression")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    scripts = {
        "aws": '#!/usr/bin/env bash\nprintf "%s\\n" "$REMOTE_DIGEST"\n',
        "docker": """#!/usr/bin/env bash
if [[ "$1" == image && "$2" == inspect ]]; then
  if [[ "${*: -1}" == *@* ]]; then echo "$REMOTE_ID"; else echo "$LOCAL_ID"; fi
else
  exit 0
fi
""",
    }
    for name, text in scripts.items():
        script = bin_dir / name
        script.write_text(text, newline="\n")
        script.chmod(0o755)

    def run(**overrides):
        env = {
            **os.environ,
            "ECR_REPOSITORY_URL": "example.ecr/repo",
            "LOCAL_ID": "sha256:" + "a" * 64,
            "REMOTE_ID": "sha256:" + "a" * 64,
            "REMOTE_DIGEST": "sha256:" + "b" * 64,
            "DEPLOY_SCRIPT": (ROOT / "infra/scripts/deploy.sh").as_posix(),
            **overrides,
        }
        return subprocess.run(  # noqa: S603 - fixed repository script, synthetic command stubs
            [bash, "-c", 'export PATH="$PWD/bin:$PATH"; bash "$DEPLOY_SCRIPT" push local'],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    return run


def test_rerun_promotes_matching_scanned_content(deploy_stub):
    result = deploy_stub()
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "example.ecr/repo@sha256:" + "b" * 64
    assert "image-" + "a" * 64 in result.stderr


def test_existing_remote_tag_cannot_substitute_old_image(deploy_stub):
    result = deploy_stub(REMOTE_ID="sha256:" + "c" * 64)
    assert result.returncode != 0
    assert "remote image differs" in result.stderr


def test_production_manifest_must_match_staging(deploy_stub):
    result = deploy_stub(EXPECTED_MANIFEST_DIGEST="sha256:" + "c" * 64)
    assert result.returncode != 0
    assert "production manifest differs" in result.stderr


def test_local_artifact_must_match_scan(deploy_stub):
    result = deploy_stub(EXPECTED_IMAGE_ID="sha256:" + "c" * 64)
    assert result.returncode != 0
    assert "image differs from scanned artifact" in result.stderr


@pytest.mark.skipif(not os.environ.get("PVC_TEST_DATABASE_URL"), reason="requires isolated PostgreSQL")
def test_operational_test_roles_never_reset_shared_passwords():
    import psycopg

    drill = load_script("scripts/restore_drill.py")
    url = os.environ["PVC_TEST_DATABASE_URL"]
    query = "select rolname,rolpassword from pg_authid where rolname in ('pvc_app','pvc_readonly','pvc_migrator') order by rolname"
    with psycopg.connect(url) as conn:
        before = conn.execute(query).fetchall()
    role, _ = drill.create_test_role(url)
    try:
        with psycopg.connect(url) as conn:
            assert conn.execute(query).fetchall() == before
            assert conn.execute("select pg_has_role(%s,'pvc_app','MEMBER')", (role,)).fetchone() == (True,)
    finally:
        drill.drop_test_role(url, role)


@pytest.fixture
def ci_gate_stub(tmp_path):
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = str(git_bash) if sys.platform == "win32" and git_bash.exists() else shutil.which("bash")
    if not bash:
        pytest.skip("bash required for release gate regression")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    scripts = {
        "gh": """#!/usr/bin/env bash
[[ "$1" == api && "$2" == "repos/test/repo/actions/workflows/ci.yml/runs?head_sha=exact-sha&event=push&branch=main&per_page=100" ]] || exit 9
printf '%s\n' "$CI_RUN_JSON"
""",
        "jq": """#!/usr/bin/env python
import json,sys
print(json.load(sys.stdin).get(sys.argv[-1].lstrip('.'), 'null'))
""",
        "sleep": "#!/usr/bin/env bash\nexit 0\n",
    }
    for name, text in scripts.items():
        script = bin_dir / name
        script.write_text(text, newline="\n")
        script.chmod(0o755)

    def run(record):
        return subprocess.run(  # noqa: S603 - fixed repository script and test-only API stubs
            [bash, "-c", 'export PATH="$PWD/bin:$PATH"; bash "$GATE_SCRIPT"'],
            cwd=tmp_path,
            env={
                **os.environ,
                "GITHUB_SHA": "exact-sha",
                "GITHUB_REPOSITORY": "test/repo",
                "CI_RUN_JSON": json.dumps(record),
                "GATE_SCRIPT": (ROOT / "infra/scripts/verify-ci.sh").as_posix(),
            },
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    return run


def test_release_gate_accepts_successful_exact_sha(ci_gate_stub):
    result = ci_gate_stub({"id": 123, "head_sha": "exact-sha", "status": "completed", "conclusion": "success"})
    assert result.returncode == 0, result.stderr
    assert "Verified CI run 123 for exact-sha" in result.stdout


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", "neutral"])
def test_release_gate_rejects_unsuccessful_ci(ci_gate_stub, conclusion):
    result = ci_gate_stub({"id": 123, "head_sha": "exact-sha", "status": "completed", "conclusion": conclusion})
    assert result.returncode != 0
    assert "Exact-SHA CI failed" in result.stderr


def test_release_gate_rejects_wrong_sha(ci_gate_stub):
    result = ci_gate_stub({"id": 123, "head_sha": "other-sha", "status": "completed", "conclusion": "success"})
    assert result.returncode != 0


def test_release_gate_rejects_unknown_response(ci_gate_stub):
    assert ci_gate_stub({"message": "Not Found"}).returncode != 0


def test_release_gate_times_out_when_ci_absent(ci_gate_stub):
    result = ci_gate_stub(None)
    assert result.returncode != 0
    assert "No successful exact-SHA CI run" in result.stderr
