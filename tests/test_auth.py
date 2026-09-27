"""PVC-091/092: OAuth bearer tokens on the Streamable HTTP MCP endpoint and company scope from claims."""

from __future__ import annotations

import socket
import threading
import time
from datetime import UTC, datetime, timedelta

import anyio
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from pe_value_os import security
from pe_value_os.auth import AuthConfigError, JwtTokenVerifier, verifier_from_env

ISS, AUD = "https://idp.example.test", "https://mcp.example.test/mcp"


@pytest.fixture(scope="module")
def keys():
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return k, pub.decode()


def token(key, **over):
    now = datetime.now(UTC)
    claims = {
        "iss": ISS,
        "aud": AUD,
        "sub": "user-1",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "scope": "pvc.read",
        "pvc_companies": ["beacon-pricing"],
        "pvc_roles": ["analyst"],
        "pvc_principal_type": "human",
        **over,
    }
    return jwt.encode(claims, key, algorithm="RS256")


def test_verifier_accepts_valid_and_rejects_bad_tokens(keys):
    key, pub = keys
    v = JwtTokenVerifier(ISS, AUD, public_key=pub)
    ok = anyio.run(v.verify_token, token(key))
    assert ok is not None and ok.subject == "user-1" and ok.claims["pvc_companies"] == ["beacon-pricing"]
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for bad in (
        token(key, aud="https://other"),
        token(key, iss="https://evil"),
        token(key, exp=datetime.now(UTC) - timedelta(minutes=5)),
        token(other),
        jwt.encode({"iss": ISS, "aud": AUD, "sub": "x"}, key=None, algorithm="none"),
    ):
        assert anyio.run(v.verify_token, bad) is None


def test_principal_comes_from_token_claims(keys, monkeypatch):
    from mcp.server.auth.middleware.auth_context import auth_context_var
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser

    monkeypatch.setenv("PVC_ENV", "prod")
    monkeypatch.setenv("PVC_ALLOWED_COMPANIES", "cedar-churn")  # ignored outside dev
    key, pub = keys
    at = anyio.run(JwtTokenVerifier(ISS, AUD, public_key=pub).verify_token, token(key))
    reset = auth_context_var.set(AuthenticatedUser(at))
    try:
        assert security.require("beacon-pricing").subject == "user-1"
        with pytest.raises(security.ScopeError):
            security.require("cedar-churn")
    finally:
        auth_context_var.reset(reset)
    with pytest.raises(security.ScopeError, match="No authenticated principal"):
        security.require("cedar-churn")


def test_auth_required_outside_dev(monkeypatch):
    monkeypatch.setenv("PVC_ENV", "prod")
    monkeypatch.delenv("PVC_AUTH_ISSUER", raising=False)
    with pytest.raises(AuthConfigError):
        verifier_from_env()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_streamable_http_requires_bearer_and_enforces_scope(keys, monkeypatch, tmp_path):
    import httpx
    import httpx2
    import uvicorn
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    key, pub = keys
    port = _free_port()
    monkeypatch.setenv("PVC_ENV", "staging")
    monkeypatch.setenv("PVC_AUTH_ISSUER", ISS)
    monkeypatch.setenv("PVC_AUTH_AUDIENCE", AUD)
    monkeypatch.setenv("PVC_AUTH_PUBLIC_KEY", pub)
    monkeypatch.setenv("PVC_MCP_RESOURCE_URL", f"http://127.0.0.1:{port}/mcp")
    monkeypatch.setenv("PVC_EVIDENCE_DIR", str(tmp_path / "ev"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore
    from pe_value_os.adapters.repositories import InMemoryRepository
    from pe_value_os.app import build_context
    from pe_value_os.mcp_server import build_server, create_http_app
    from pe_value_os.tools import _runtime

    # This test isolates the real HTTP/auth boundary with an explicit test repository.
    # Production environment wiring separately rejects a missing DATABASE_URL.
    _runtime.set_ctx(build_context(repo=InMemoryRepository(FileSystemEvidenceStore(tmp_path / "ev"))))
    app = create_http_app(build_server())
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        url = f"http://127.0.0.1:{port}/mcp"
        r = httpx.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert r.status_code == 401 and "Bearer" in r.headers.get("www-authenticate", "")

        async def session_calls(tok):
            async with (
                httpx2.AsyncClient(headers={"Authorization": f"Bearer {tok}"}, timeout=30) as http,
                streamable_http_client(url, http_client=http) as (read, write),
                ClientSession(read, write) as s,
            ):
                await s.initialize()
                ok = await s.call_tool("get_company_profile", {"company_id": "beacon-pricing"})
                denied = await s.call_tool("get_company_profile", {"company_id": "cedar-churn"})
                start = await s.call_tool(
                    "start_diagnostic_run", {"company_id": "beacon-pricing", "mode": "interactive"}
                )
                return ok, denied, start

        ok, denied, start = anyio.run(session_calls, token(key))
        assert ok.is_error is False and ok.structured_content["profile"]["company_id"] == "beacon-pricing"
        assert denied.is_error and "Access denied" in denied.content[0].text
        assert start.is_error and "pvc.write" in start.content[0].text  # read-only token cannot change state
        _, _, start = anyio.run(session_calls, token(key, scope="pvc.read pvc.write"))
        assert start.is_error is False and start.structured_content["status"] == "running"
        rebind = httpx.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={
                "Accept": "application/json, text/event-stream",
                "Host": "evil.example",
                "Authorization": f"Bearer {token(key)}",
            },
        )
        assert rebind.status_code in (400, 403, 421), rebind.status_code  # DNS-rebinding protection
    finally:
        server.should_exit = True
        th.join(timeout=10)
        _runtime.set_ctx(None)
