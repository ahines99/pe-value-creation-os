"""Company-scope enforcement (PVC-026, PVC-092).

The current principal comes from, in order:
1. an explicit `principal_scope(...)` context (worker jobs, tests),
2. the MCP bearer token (claims `pvc_companies`, `pvc_roles`, `pvc_principal_type`),
3. in dev only (PVC_ENV=dev), the `PVC_ALLOWED_COMPANIES` environment variable.
Anything else is denied.
"""

from __future__ import annotations

import contextvars
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


class ScopeError(PermissionError):
    """The caller may not access this company."""


@dataclass(frozen=True)
class Principal:
    subject: str
    companies: frozenset[str]
    roles: frozenset[str] = field(default_factory=frozenset)
    principal_type: str = "service"  # human | service | model

    @property
    def is_human(self) -> bool:
        return self.principal_type == "human"


_current: contextvars.ContextVar[Principal | None] = contextvars.ContextVar("pvc_principal", default=None)


@contextmanager
def principal_scope(principal: Principal) -> Iterator[Principal]:
    token = _current.set(principal)
    try:
        yield principal
    finally:
        _current.reset(token)


def system_principal(*company_ids: str, subject: str = "system:worker") -> Principal:
    return Principal(subject=subject, companies=frozenset(company_ids), principal_type="service")


def _from_mcp_token() -> Principal | None:
    try:
        from mcp.server.auth.middleware.auth_context import get_access_token
    except ImportError:  # pragma: no cover
        return None
    token = get_access_token()
    if token is None:
        return None
    claims = token.claims or {}
    companies = claims.get("pvc_companies") or []
    roles = claims.get("pvc_roles") or []
    return Principal(
        subject=token.subject or token.client_id,
        companies=frozenset(str(c) for c in companies),
        roles=frozenset(str(r) for r in roles),
        principal_type=str(claims.get("pvc_principal_type", "service")),
    )


def _from_dev_env() -> Principal | None:
    if os.environ.get("PVC_ENV", "prod") != "dev":
        return None
    raw = os.environ.get("PVC_ALLOWED_COMPANIES", "")
    companies = frozenset(c.strip() for c in raw.split(",") if c.strip())
    return Principal(subject="dev", companies=companies, principal_type="service")


def current_principal() -> Principal | None:
    return _current.get() or _from_mcp_token() or _from_dev_env()


def allowed_companies() -> frozenset[str]:
    p = current_principal()
    return p.companies if p else frozenset()


def require(company_id: str) -> Principal:
    p = current_principal()
    if p is None:
        raise ScopeError("No authenticated principal")
    if company_id not in p.companies:
        raise ScopeError(f"Principal {p.subject!r} may not access company {company_id!r}")
    return p
