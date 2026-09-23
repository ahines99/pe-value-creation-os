"""Approval API and review UI (PVC-060, PVC-062, PVC-063, PVC-124). Separate from the MCP surface.

Authentication: an access token from the identity provider, verified for signature, issuer, expiry and the API's
own audience (PVC_API_AUDIENCE). It arrives as `Authorization: Bearer <jwt>` (API clients) or, for the browser
pages, in `x-amzn-oidc-accesstoken`, which the load balancer sets after its OIDC sign-in. Either way the token is
fully verified here, so a forged header carries no weight. In dev only, PVC_DEV_TOKENS maps opaque tokens to
claims for local demos.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from .. import __version__, approvals, security
from ..adapters.evidence_store import EvidenceNotFound
from ..adapters.repositories import Conflict, NotFound
from ..auth import JwtTokenVerifier, principal_from_claims, verifier_from_env
from ..domain.runs import ApprovalDecision
from ..observability import RequestMetricsMiddleware, configure_telemetry, get_logger
from ..workflows import primary
from ..workflows.steps import RunContext
from . import views

log = get_logger(__name__)
configure_telemetry("pvc-api")
app = FastAPI(title="PE Value Creation OS - approvals", version=__version__, docs_url=None, redoc_url=None)
app.add_middleware(RequestMetricsMiddleware, service="api")

SECURITY_HEADERS = {
    # Server-rendered pages with one inline <style> block and no scripts.
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; form-action 'self'; "
    "frame-ancestors 'none'; base-uri 'none'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",  # plans, value cases and evidence must not sit in shared or browser caches
}


@app.middleware("http")
async def security_headers(request: Request, call_next: Any) -> Response:
    response: Response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


_ctx: RunContext | None = None
_verifier: JwtTokenVerifier | bool | None = False


def set_ctx(ctx: RunContext | None) -> None:
    global _ctx
    _ctx = ctx


def get_ctx() -> RunContext:
    global _ctx
    if _ctx is None:
        from ..app import build_context

        _ctx = build_context(actor="api")
    return _ctx


def _get_verifier() -> JwtTokenVerifier | None:
    global _verifier
    if _verifier is False:
        _verifier = verifier_from_env(for_api=True)
    return _verifier  # type: ignore[return-value]


def reset_auth() -> None:
    global _verifier
    _verifier = False


def _dev_tokens() -> dict[str, dict[str, Any]]:
    if os.environ.get("PVC_ENV", "prod") != "dev":
        return {}
    raw = os.environ.get("PVC_DEV_TOKENS", "")
    return json.loads(raw) if raw else {}


def current_principal(request: Request) -> security.Principal:
    auth = request.headers.get("authorization", "")
    token = (
        auth[7:].strip() if auth.lower().startswith("bearer ") else request.headers.get("x-amzn-oidc-accesstoken", "")
    )
    if not token:
        raise HTTPException(401, "Missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    dev = _dev_tokens()
    if token in dev:
        return principal_from_claims(dev[token])
    verifier = _get_verifier()
    if verifier is None:
        raise HTTPException(401, "Invalid token", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = verifier.decode(token)
    except Exception as e:
        raise HTTPException(401, "Invalid token", headers={"WWW-Authenticate": "Bearer"}) from e
    return principal_from_claims(claims)


Principal = Annotated[security.Principal, Depends(current_principal)]


@contextmanager
def scoped(p: security.Principal) -> Iterator[None]:
    with security.principal_scope(p):
        yield


def _load_run(run_id: str) -> Any:
    try:
        return get_ctx().repo.get_run(run_id)
    except NotFound as e:
        raise HTTPException(404, "Run not found") from e


class DecisionIn(BaseModel):
    decision: Literal["approved", "rejected", "changes_requested"]
    rationale: str | None = None
    remove_initiatives: list[str] = Field(default_factory=list, description="Initiatives removed when approving")
    exclude_opportunities: list[str] = Field(default_factory=list, description="For changes_requested")


def _decide(run_id: str, p: security.Principal, body: DecisionIn) -> dict[str, Any]:
    ctx = get_ctx()
    try:
        rec = approvals.decide(
            ctx,
            run_id,
            p,
            ApprovalDecision(body.decision),
            rationale=body.rationale,
            remove_initiatives=body.remove_initiatives,
            exclude_opportunities=body.exclude_opportunities,
        )
    except approvals.NotApprover as e:
        raise HTTPException(403, str(e)) from e
    except (approvals.ApprovalError, Conflict) as e:
        raise HTTPException(422, str(e)) from e
    # Automated runs are resumed by the worker (decide() requests it); interactive runs finalize in decide().
    return rec.model_dump(mode="json")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/runs/{run_id}")
def run_status(run_id: str, p: Principal) -> dict[str, Any]:
    with scoped(p):
        _load_run(run_id)
        return primary.status(get_ctx(), run_id)


@app.post("/runs/{run_id}/approvals")
def post_decision(run_id: str, body: DecisionIn, p: Principal) -> dict[str, Any]:
    with scoped(p):
        _load_run(run_id)
        return _decide(run_id, p, body)


@app.post("/runs/{run_id}/approvals/form")
def post_decision_form(
    run_id: str,
    request: Request,
    p: Principal,
    decision: Annotated[str, Form()],
    csrf: Annotated[str, Form()],
    rationale: Annotated[str, Form()] = "",
    remove_initiatives: Annotated[list[str] | None, Form()] = None,
) -> Response:
    if not secrets.compare_digest(csrf, request.cookies.get("pvc_csrf", "")):
        raise HTTPException(403, "CSRF check failed")
    if decision not in ("approved", "rejected", "changes_requested"):
        raise HTTPException(422, "Invalid decision")
    with scoped(p):
        _load_run(run_id)
        _decide(
            run_id,
            p,
            DecisionIn.model_validate(
                {"decision": decision, "rationale": rationale or None, "remove_initiatives": remove_initiatives or []}
            ),
        )
    return RedirectResponse(f"/runs/{run_id}/review", status_code=303)


@app.get("/runs/{run_id}/review", response_class=HTMLResponse)
def review(run_id: str, p: Principal) -> HTMLResponse:
    ctx = get_ctx()
    with scoped(p):
        run = _load_run(run_id)
        opps = ctx.repo.list_opportunities(run_id)
        cases = {v.opportunity_id: v for v in ctx.repo.list_value_cases(run_id)}
        approvals_ = ctx.repo.list_approvals(run_id)
        csrf = secrets.token_urlsafe(24)
        can = p.is_human and ctx.policy.approval.approver_role in p.roles
        html = views.review_page(
            run,
            ctx.repo.latest_plan(run_id),
            opps,
            cases,
            ctx.repo.list_findings(run_id),
            approvals_[-1] if approvals_ else None,
            csrf,
            can,
        )
    resp = HTMLResponse(html)
    resp.set_cookie("pvc_csrf", csrf, httponly=True, samesite="strict", secure=os.environ.get("PVC_ENV") != "dev")
    return resp


@app.get("/evidence/{evidence_id}")
def evidence(evidence_id: str, p: Principal) -> Response:
    with scoped(p):
        try:
            ev = get_ctx().repo.get_evidence(evidence_id)
            content = get_ctx().repo.evidence_content(evidence_id)
        except (NotFound, EvidenceNotFound) as e:
            raise HTTPException(404, "Evidence not found") from e
    name = ev.source_uri.rsplit("/", 1)[-1] or "evidence"
    return Response(
        content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'inline; filename="{name}"',
            "X-Content-Hash": ev.content_hash,
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/companies/{company_id}/kpis", response_class=HTMLResponse)
def kpis(company_id: str, p: Principal) -> HTMLResponse:
    ctx = get_ctx()
    with scoped(p):
        try:
            defs = ctx.repo.list_kpi_definitions(company_id)
            obs = ctx.repo.list_kpi_observations(company_id)
        except security.ScopeError as e:
            raise HTTPException(404, "Company not found") from e
    return HTMLResponse(views.kpi_page(company_id, defs, obs))


@app.get("/metrics/approvals")
def approval_metrics(p: Principal) -> dict[str, Any]:
    with scoped(p):
        return approvals.override_stats(get_ctx())


@app.exception_handler(security.ScopeError)
def _scope_error(_: Request, exc: security.ScopeError) -> JSONResponse:
    return JSONResponse({"detail": "Not found"}, status_code=404)
