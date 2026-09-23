"""Authentication for the Streamable HTTP MCP endpoint and the approval API (PVC-091, PVC-092).

Tokens are OAuth 2.1 access tokens (JWT) issued by the fund's identity provider. The verifier checks signature,
issuer, audience and expiry, then exposes the claims the application uses:

- `pvc_companies`: list of company ids the principal may access (drives `security.require` and RLS)
- `pvc_roles`: e.g. ["analyst"], ["approver"]
- `pvc_principal_type`: "human" | "service" | "model"; only humans may approve

Configuration (environment):
- PVC_AUTH_ISSUER            issuer URL (required outside dev)
- PVC_AUTH_AUDIENCE          expected `aud` (the MCP resource URL)
- PVC_AUTH_JWKS_URL          JWKS endpoint, or PVC_AUTH_PUBLIC_KEY (PEM) for a static key
- PVC_MCP_RESOURCE_URL       this server's public URL (advertised as protected-resource metadata)
- PVC_AUTH_REQUIRED_SCOPES   comma-separated scopes required for MCP access (default: pvc.read)
- PVC_API_AUDIENCE           expected `aud` for the approval API (required outside dev). It must differ from the
                             MCP audience, so a token issued to an MCP client cannot be replayed against the API.
- PVC_API_CLIENT_IDS         comma-separated OAuth client ids (`azp`) allowed to record approval decisions,
                             i.e. the approval UI's client. Required outside dev.

Scopes: `pvc.read` for MCP access, `pvc.write` for MCP tools that change state, `pvc.approve` for approval
decisions (see `security.WRITE_SCOPE` / `security.APPROVE_SCOPE`).
"""

from __future__ import annotations

import os
from typing import Any

import jwt
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings

from .egress import check_url
from .security import Principal


class AuthConfigError(RuntimeError):
    pass


class JwtTokenVerifier:
    def __init__(
        self,
        issuer: str,
        audience: str,
        *,
        jwks_url: str | None = None,
        public_key: str | None = None,
        algorithms: tuple[str, ...] = ("RS256", "ES256"),
        leeway_s: int = 30,
    ):
        if not (jwks_url or public_key):
            raise AuthConfigError("Set PVC_AUTH_JWKS_URL or PVC_AUTH_PUBLIC_KEY")
        self.issuer, self.audience, self.algorithms, self.leeway = issuer, audience, list(algorithms), leeway_s
        self.public_key = public_key
        self.jwks = None
        if jwks_url:
            check_url(jwks_url)  # identity provider must be on the egress allow-list
            self.jwks = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=300)

    def decode(self, token: str) -> dict[str, Any]:
        key: Any = self.public_key
        if self.jwks is not None:
            key = self.jwks.get_signing_key_from_jwt(token).key
        claims: dict[str, Any] = jwt.decode(
            token,
            key=key,
            algorithms=self.algorithms,
            audience=self.audience,
            issuer=self.issuer,
            leeway=self.leeway,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
        return claims

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = self.decode(token)
        except jwt.PyJWTError:
            return None
        return AccessToken(
            token=token,
            client_id=str(claims.get("azp") or claims.get("client_id") or claims["sub"]),
            scopes=sorted(_scopes(claims)),
            expires_at=int(claims["exp"]),
            subject=str(claims["sub"]),
            claims=claims,
        )


def _scopes(claims: dict[str, Any]) -> frozenset[str]:
    raw = claims.get("scope", claims.get("scp", ""))
    return frozenset(raw.split() if isinstance(raw, str) else (str(s) for s in raw))


def principal_from_claims(claims: dict[str, Any]) -> Principal:
    return Principal(
        subject=str(claims.get("sub")),
        companies=frozenset(str(c) for c in claims.get("pvc_companies") or []),
        roles=frozenset(str(r) for r in claims.get("pvc_roles") or []),
        principal_type=str(claims.get("pvc_principal_type", "service")),
        scopes=_scopes(claims),
        client_id=str(claims.get("azp") or claims.get("client_id") or "") or None,
    )


def verifier_from_env(*, for_api: bool = False) -> JwtTokenVerifier | None:
    """Token verifier for the MCP endpoint, or (for_api=True) for the approval API with its own audience."""
    issuer = os.environ.get("PVC_AUTH_ISSUER")
    if not issuer:
        if os.environ.get("PVC_ENV", "prod") != "dev":
            raise AuthConfigError("PVC_AUTH_ISSUER is required outside dev (PVC_ENV=dev disables auth)")
        return None
    mcp_audience = os.environ.get("PVC_AUTH_AUDIENCE") or os.environ.get("PVC_MCP_RESOURCE_URL")
    if for_api:
        audience = os.environ.get("PVC_API_AUDIENCE")
        if not audience:
            raise AuthConfigError("Set PVC_API_AUDIENCE for the approval API")
        if audience == mcp_audience:
            raise AuthConfigError("PVC_API_AUDIENCE must differ from the MCP audience")
    else:
        audience = mcp_audience
    if not audience:
        raise AuthConfigError("Set PVC_AUTH_AUDIENCE")
    return JwtTokenVerifier(
        issuer, audience, jwks_url=os.environ.get("PVC_AUTH_JWKS_URL"), public_key=os.environ.get("PVC_AUTH_PUBLIC_KEY")
    )


def auth_settings_from_env() -> AuthSettings | None:
    issuer = os.environ.get("PVC_AUTH_ISSUER")
    if not issuer:
        return None
    scopes = [s.strip() for s in os.environ.get("PVC_AUTH_REQUIRED_SCOPES", "pvc.read").split(",") if s.strip()]
    return AuthSettings(
        issuer_url=issuer,
        resource_server_url=os.environ.get("PVC_MCP_RESOURCE_URL"),
        required_scopes=scopes,
        validate_token_resource=False,
    )
