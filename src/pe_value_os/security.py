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
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


class ScopeError(PermissionError):
    """The caller may not access this company."""


def validate_company_id(company_id: str) -> str:
    """Canonical tenant IDs are safe in paths and comma-separated PostgreSQL scope settings."""
    if not isinstance(company_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", company_id):
        raise ValueError("Invalid company identifier")
    return company_id


def deny(message: str, reason: str = "company_scope") -> ScopeError:
    """A ScopeError, counted in `pvc.access.denied` so probing is visible whatever surface it hits."""
    from .observability import metrics

    metrics().access_denied.add(1, {"reason": reason})
    return ScopeError(message)


@dataclass(frozen=True)
class Principal:
    subject: str
    companies: frozenset[str]
    roles: frozenset[str] = field(default_factory=frozenset)
    principal_type: str = "service"  # human | service | model
    # OAuth scopes and client for token-based principals; None for system, test and dev principals, which are
    # not issued by the identity provider and are not scope-bound.
    scopes: frozenset[str] | None = None
    client_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.companies, frozenset):
            raise ValueError("Principal companies must be a frozenset")
        for company_id in self.companies:
            validate_company_id(company_id)

    @property
    def is_human(self) -> bool:
        return self.principal_type == "human"

    def has_scope(self, scope: str) -> bool:
        return self.scopes is None or scope in self.scopes


WRITE_SCOPE = "pvc.write"  # required by MCP tools that change state
APPROVE_SCOPE = "pvc.approve"  # required by approval decisions in the approval API


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
    from .auth import principal_from_claims

    return principal_from_claims(
        {
            **(token.claims or {}),
            "sub": token.subject or token.client_id,
            "scope": token.scopes or [],
            "client_id": token.client_id,
        }
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
    try:
        validate_company_id(company_id)
    except ValueError as exc:
        raise deny("Invalid company identifier") from exc
    p = current_principal()
    if p is None:
        raise deny("No authenticated principal", "unauthenticated")
    if company_id not in p.companies:
        raise deny(f"Principal {p.subject!r} may not access company {company_id!r}")
    return p
