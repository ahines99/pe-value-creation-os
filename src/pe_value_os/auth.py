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
        scopes = claims.get("scope", "")
        return AccessToken(
            token=token,
            client_id=str(claims.get("azp") or claims.get("client_id") or claims["sub"]),
            scopes=scopes.split() if isinstance(scopes, str) else list(scopes),
            expires_at=int(claims["exp"]),
            subject=str(claims["sub"]),
            claims=claims,
        )


def principal_from_claims(claims: dict[str, Any]) -> Principal:
    return Principal(
        subject=str(claims.get("sub")),
        companies=frozenset(str(c) for c in claims.get("pvc_companies") or []),
        roles=frozenset(str(r) for r in claims.get("pvc_roles") or []),
        principal_type=str(claims.get("pvc_principal_type", "service")),
    )


def verifier_from_env() -> JwtTokenVerifier | None:
    issuer = os.environ.get("PVC_AUTH_ISSUER")
    if not issuer:
        if os.environ.get("PVC_ENV", "prod") != "dev":
            raise AuthConfigError("PVC_AUTH_ISSUER is required outside dev (PVC_ENV=dev disables auth)")
        return None
    audience = os.environ.get("PVC_AUTH_AUDIENCE") or os.environ.get("PVC_MCP_RESOURCE_URL")
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
