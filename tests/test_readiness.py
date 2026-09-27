"""A18: health stays live while dependency readiness fails safely."""

from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from pe_value_os import readiness
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore, S3EvidenceStore
from pe_value_os.adapters.repositories import InMemoryRepository
from pe_value_os.api import app as api


def test_readiness_checks_storage_and_hides_failure_detail(monkeypatch, tmp_path):
    store = FileSystemEvidenceStore(tmp_path / "ev")
    ctx = SimpleNamespace(repo=InMemoryRepository(store))
    monkeypatch.setattr(api, "get_ctx", lambda: ctx)
    with TestClient(api.app) as client:
        assert client.get("/readyz").json() == {"status": "ready"}
        store.root.rmdir()
        store.root.write_text("not a directory")
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json() == {"status": "unready"}
        assert str(tmp_path) not in response.text
        assert client.get("/healthz").status_code == 200


def test_production_cannot_report_in_memory_repository_ready(monkeypatch, tmp_path):
    monkeypatch.setenv("PVC_ENV", "prod")
    ctx = SimpleNamespace(repo=InMemoryRepository(FileSystemEvidenceStore(tmp_path)))
    assert not readiness.is_ready(ctx)


def test_production_repository_configuration_fails_closed(monkeypatch):
    import pytest

    from pe_value_os.adapters import repositories

    monkeypatch.setenv("PVC_ENV", "prod")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    repositories.set_repository(None)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        repositories.get_repository()


def test_s3_probe_uses_allowed_prefix_and_propagates_denials():
    import pytest

    client = Mock()
    store = S3EvidenceStore("bucket", client=client)
    readiness._evidence(store)
    client.list_objects_v2.assert_called_once_with(Bucket="bucket", Prefix="evidence/__readiness__/", MaxKeys=1)
    client.list_objects_v2.side_effect = PermissionError("denied")
    with pytest.raises(PermissionError):
        readiness._evidence(store)


def test_mcp_readiness_route_probes_dependencies_without_exposing_data(monkeypatch, tmp_path):
    from pe_value_os import mcp_server

    ctx = SimpleNamespace(repo=InMemoryRepository(FileSystemEvidenceStore(tmp_path)))
    monkeypatch.setattr(mcp_server, "get_ctx", lambda: ctx)
    with TestClient(mcp_server.create_http_app()) as client:
        assert client.get("/readyz").status_code == 200
        monkeypatch.setenv("PVC_ENV", "prod")
        assert client.get("/readyz").status_code == 503


def test_postgres_runtime_role_readiness_and_missing_grant(pg_repo, pg_database):
    import psycopg

    ctx = SimpleNamespace(repo=pg_repo)
    assert readiness.is_ready(ctx)
    admin, _ = pg_database
    with psycopg.connect(admin) as conn:
        conn.execute("revoke insert on workflow_runs from pvc_app")
    try:
        assert not readiness.is_ready(ctx)
    finally:
        with psycopg.connect(admin) as conn:
            conn.execute("grant insert on workflow_runs to pvc_app")


def test_malformed_dev_claims_return_unauthorized(monkeypatch):
    import json

    monkeypatch.setenv("PVC_DEV_TOKENS", json.dumps({"bad": {"sub": "x", "pvc_companies": "tenant-a"}}))
    with TestClient(api.app) as client:
        assert client.get("/runs/unknown", headers={"Authorization": "Bearer bad"}).status_code == 401
