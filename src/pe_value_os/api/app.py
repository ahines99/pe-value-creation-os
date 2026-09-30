"""Approval API and review UI (PVC-060, PVC-062, PVC-063, PVC-124). Separate from the MCP surface.

Authentication: an access token from the identity provider, verified for signature, issuer, expiry and the API's
own audience (PVC_API_AUDIENCE). It arrives as `Authorization: Bearer <jwt>` (API clients) or, for the browser
pages, in `x-amzn-oidc-accesstoken`, which the load balancer sets after its OIDC sign-in. Either way the token is
fully verified here, so a forged header carries no weight. In dev only, PVC_DEV_TOKENS maps opaque tokens to
claims for local demos.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from urllib.parse import parse_qsl, quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from jwt import PyJWTError
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .. import __version__, approvals, security
from ..adapters.evidence_store import EvidenceNotFound
from ..adapters.repositories import Conflict, NotFound
from ..auth import JwtTokenVerifier, principal_from_claims, verifier_from_env
from ..diligence.cases import ReviewRequest, RevisionDraft, compare_revisions
from ..diligence.close_baseline import CloseBaselineRequest, close_baseline_view
from ..diligence.execution import ExecutionRequest
from ..diligence.models import Record
from ..diligence.private_attribution import AttributionRequest as PrivateAttributionRequest
from ..diligence.private_attribution import AttributionReviewRequest
from ..diligence.private_baselines import (
    BaselineRequest,
    PlanReviewRequest,
    ReviewKind,
)
from ..diligence.private_baselines import (
    require_baseline_author as require_private_baseline_author,
)
from ..diligence.private_baselines import (
    require_reviewer as require_private_plan_reviewer,
)
from ..diligence.private_capacity import CapacityPlanRequest
from ..diligence.private_execution import PrivateExecutionRequest, reducing_support
from ..diligence.private_financials import FinancialSnapshotRequest, require_snapshot_writer
from ..diligence.private_grants import GrantRequest, permission_status
from ..diligence.private_intake import MAX_BYTES, parse_private
from ..diligence.private_observations import (
    CounterfactualRequest,
    CounterfactualReviewRequest,
    PrivateObservationRequest,
)
from ..diligence.private_records import (
    FinanceReviewRequest,
    IntakeRequest,
    require_finance_reviewer,
    require_intake_writer,
)
from ..diligence.private_review import review_note_request
from ..diligence.private_underwriting import UnderwritingRequest
from ..diligence.realization import AttributionRequest, ObservationRequest
from ..domain.runs import ApprovalDecision, RunRecord
from ..observability import RequestMetricsMiddleware, configure_telemetry, get_logger
from ..workflows import primary
from ..workflows.steps import RunContext
from . import private_review_views, views

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
    if not token and os.environ.get("PVC_ENV") == "dev":
        token = request.cookies.get("pvc_dev_session", "")
    if not token:
        raise HTTPException(401, "Missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    dev = _dev_tokens()
    if token in dev:
        try:
            return principal_from_claims(dev[token])
        except (TypeError, ValueError, PyJWTError) as exc:
            raise HTTPException(401, "Invalid token", headers={"WWW-Authenticate": "Bearer"}) from exc
    verifier = _get_verifier()
    if verifier is None:
        raise HTTPException(401, "Invalid token", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = verifier.decode(token)
        return principal_from_claims(claims)
    except Exception as e:
        raise HTTPException(401, "Invalid token", headers={"WWW-Authenticate": "Bearer"}) from e


Principal = Annotated[security.Principal, Depends(current_principal)]


@contextmanager
def scoped(p: security.Principal) -> Iterator[None]:
    with security.principal_scope(p):
        yield


class CaseCreateIn(BaseModel):
    model_config = {"extra": "forbid"}
    company_id: str
    case_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class CaseRevisionIn(BaseModel):
    model_config = {"extra": "forbid"}
    expected_parent_revision_id: str | None
    draft: RevisionDraft


@contextmanager
def case_request(p: security.Principal, request: Request, *, write: bool = False) -> Iterator[None]:
    # JSON writes accept explicit bearer credentials only; browser session cookies
    # cannot silently authorize state changes without a CSRF-aware form.
    if write and not request.headers.get("authorization", "").lower().startswith("bearer "):
        raise HTTPException(403, "Case writes require an explicit bearer credential")
    try:
        with scoped(p):
            yield
    except NotFound as exc:
        raise HTTPException(404, "Case record not found") from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, "Invalid case version, source policy or review binding") from exc


@app.post("/cases", status_code=201)
def create_case(body: CaseCreateIn, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request, write=True):
        return (
            get_ctx()
            .repo.create_investment_case(body.company_id, body.case_id, body.label, body.currency)
            .model_dump(mode="json")
        )


@app.post("/companies/{company_id}/private-grants/{grant_key}/events", status_code=201)
def record_private_grant(
    company_id: str, grant_key: str, body: GrantRequest, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request, write=True):
        return get_ctx().repo.record_private_grant(company_id, grant_key, body).model_dump(mode="json")


@app.get("/companies/{company_id}/private-grants/{grant_key}")
def private_grant_history(
    company_id: str, grant_key: str, policy_sha256: str, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request):
        events = get_ctx().repo.list_private_grants(company_id, grant_key)
        return {
            "events": [event.model_dump(mode="json") for event in events],
            "current": permission_status(events, policy_sha256, now=datetime.now(UTC)),
        }


class PrivateUpload(Record):
    intake: IntakeRequest
    source_base64: str = Field(min_length=1, max_length=((MAX_BYTES + 2) // 3) * 4)


@app.post("/companies/{company_id}/private-execution/baselines/{baseline_id}/events/{kind}", status_code=201)
async def record_private_execution(
    company_id: str,
    baseline_id: str,
    kind: Literal["authorization", "delivery", "acceptance"],
    request: Request,
    p: Principal,
) -> dict[str, Any]:
    with case_request(p, request, write=True):
        if kind == "authorization":
            require_private_baseline_author(company_id)
        elif kind == "acceptance":
            require_private_plan_reviewer(company_id, "operating")
        else:
            require_intake_writer(company_id)
        body = parse_private(PrivateExecutionRequest, await bounded_private_body(request, 1024 * 1024))
        if body.payload.kind != kind:
            raise ValueError("execution event kind differs from the requested route")
        environment = "" if reducing_support(body) else processing_environment()
        result = await run_in_threadpool(
            get_ctx().repo.record_private_execution, company_id, baseline_id, body, environment
        )
        return result.model_dump(mode="json")


@app.get("/companies/{company_id}/private-execution/baselines/{baseline_id}/events")
def private_execution_history(company_id: str, baseline_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        return {
            "events": [
                e.model_dump(mode="json") for e in get_ctx().repo.list_private_execution_events(company_id, baseline_id)
            ],
            "historical_records_only": True,
            "automated_action_executed": False,
            "causal_value_claim": False,
        }


@app.get("/companies/{company_id}/private-execution/baselines/{baseline_id}/status")
def private_execution_status(company_id: str, baseline_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        return get_ctx().repo.private_execution_status(company_id, baseline_id, processing_environment())


@app.get("/private-reviews", response_class=HTMLResponse)
def private_review_index(request: Request, p: Principal) -> HTMLResponse:
    with case_request(p, request):
        if not p.is_human or not p.has_scope("pvc.read"):
            raise security.deny("Private review requires a scoped human reader", "private_review_index")
        cards = []
        for company_id in sorted(p.companies):
            try:
                cards.extend(get_ctx().repo.private_review_index(company_id))
            except NotFound:
                continue
        return HTMLResponse(private_review_views.index_page(cards))


def _private_review_response(
    company_id: str,
    revision_id: str,
    *,
    error: str | None = None,
    status_code: int = 200,
    submitted: dict[str, str] | None = None,
) -> HTMLResponse:
    packet = get_ctx().repo.private_attribution_review_packet(
        company_id, revision_id, os.environ.get("PVC_PROCESSING_ENVIRONMENT_ID", "").strip()
    )
    csrf = secrets.token_urlsafe(32)
    html = private_review_views.review_page(
        packet,
        csrf,
        "review-" + secrets.token_hex(16),
        error=error,
        submitted=submitted,
    )
    response = HTMLResponse(html, status_code=status_code)
    response.set_cookie(
        "pvc_private_review_csrf",
        csrf,
        httponly=True,
        samesite="strict",
        secure=os.environ.get("PVC_ENV") != "dev",
        max_age=1800,
    )
    return response


@app.get("/companies/{company_id}/private-reviews/{revision_id}", response_class=HTMLResponse)
def private_review_page(company_id: str, revision_id: str, request: Request, p: Principal) -> HTMLResponse:
    with case_request(p, request):
        return _private_review_response(company_id, revision_id)


@app.post("/companies/{company_id}/private-reviews/{revision_id}/decision", response_class=HTMLResponse)
async def private_review_decision(company_id: str, revision_id: str, request: Request, p: Principal) -> Response:
    with case_request(p, request):
        require_finance_reviewer(company_id)
        raw = await bounded_private_body(request, 64 * 1024)
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/x-www-form-urlencoded":
            raise HTTPException(415, "Private review requires a URL-encoded form")
        pairs = parse_qsl(
            raw.decode("utf-8", errors="strict"), keep_blank_values=True, max_num_fields=20, errors="strict"
        )
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError("duplicate private review form field")
        csrf = request.cookies.get("pvc_private_review_csrf", "")
        if not csrf or not secrets.compare_digest(fields.get("csrf", "").encode(), csrf.encode()):
            return await run_in_threadpool(
                _private_review_response,
                company_id,
                revision_id,
                error="This form expired. Review the current version before submitting again.",
                status_code=403,
                submitted=fields,
            )
        try:
            body = review_note_request(fields)
            environment = "" if body.decision == "withdraw" else processing_environment()
            await run_in_threadpool(
                get_ctx().repo.review_private_attribution, company_id, revision_id, body, environment
            )
        except (ValueError, Conflict) as exc:
            changed = isinstance(exc, Conflict)
            return await run_in_threadpool(
                _private_review_response,
                company_id,
                revision_id,
                error=(
                    "The reviewed version changed. Inspect the updated evidence and submit a new decision."
                    if changed
                    else "The decision could not be recorded. Acceptance needs all five assessments and current source, delivery and version support."
                ),
                status_code=409 if changed else 422,
                submitted=fields,
            )
        return RedirectResponse(private_review_views.review_path(company_id, revision_id), status_code=303)


@app.post("/companies/{company_id}/private-attributions/cases/{case_key}/streams/{key}", status_code=201)
async def record_private_attribution(
    company_id: str, case_key: str, key: str, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request, write=True):
        require_intake_writer(company_id)
        body = parse_private(PrivateAttributionRequest, await bounded_private_body(request, 1024 * 1024))
        result = await run_in_threadpool(
            get_ctx().repo.record_private_attribution, company_id, case_key, key, body, processing_environment()
        )
        return result.model_dump(mode="json")


@app.get("/companies/{company_id}/private-attributions/cases/{case_key}/streams/{key}")
def private_attribution_history(
    company_id: str, case_key: str, key: str, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request):
        return {
            "revisions": [
                r.model_dump(mode="json") for r in get_ctx().repo.list_private_attributions(company_id, case_key, key)
            ],
            "historical_records_only": True,
            "causal_impact_proven": False,
        }


@app.post("/companies/{company_id}/private-attributions/revisions/{revision_id}/reviews", status_code=201)
async def review_private_attribution(
    company_id: str, revision_id: str, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request, write=True):
        require_finance_reviewer(company_id)
        body = parse_private(AttributionReviewRequest, await bounded_private_body(request, 1024 * 1024))
        environment = "" if body.decision == "withdraw" else processing_environment()
        result = await run_in_threadpool(
            get_ctx().repo.review_private_attribution, company_id, revision_id, body, environment
        )
        return result.model_dump(mode="json")


@app.get("/companies/{company_id}/private-attributions/revisions/{revision_id}/reviews")
def private_attribution_reviews(company_id: str, revision_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        return {
            "reviews": [
                r.model_dump(mode="json")
                for r in get_ctx().repo.list_private_attribution_reviews(company_id, revision_id)
            ],
            "historical_records_only": True,
            "causal_impact_proven": False,
        }


@app.get("/companies/{company_id}/private-attributions/revisions/{revision_id}/usable")
def usable_private_attribution(company_id: str, revision_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        proposal, review = get_ctx().repo.usable_private_attribution(company_id, revision_id, processing_environment())
        return {
            "revision": proposal.model_dump(mode="json"),
            "review": review.model_dump(mode="json"),
            "usable_for_reviewed_attribution": True,
            "causal_impact_proven": False,
        }


@app.post("/companies/{company_id}/private-counterfactuals/cases/{case_key}/streams/{key}", status_code=201)
async def record_private_counterfactual(
    company_id: str, case_key: str, key: str, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request, write=True):
        require_intake_writer(company_id)
        body = parse_private(CounterfactualRequest, await bounded_private_body(request, 1024 * 1024))
        result = await run_in_threadpool(
            get_ctx().repo.record_private_counterfactual, company_id, case_key, key, body, processing_environment()
        )
        return result.model_dump(mode="json")


@app.get("/companies/{company_id}/private-counterfactuals/cases/{case_key}/streams/{key}")
def private_counterfactual_history(
    company_id: str, case_key: str, key: str, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request):
        return {
            "revisions": [
                r.model_dump(mode="json")
                for r in get_ctx().repo.list_private_counterfactuals(company_id, case_key, key)
            ],
            "historical_records_only": True,
            "causal_value_claim": False,
        }


@app.post("/companies/{company_id}/private-counterfactuals/revisions/{revision_id}/reviews", status_code=201)
async def review_private_counterfactual(
    company_id: str, revision_id: str, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request, write=True):
        require_finance_reviewer(company_id)
        body = parse_private(CounterfactualReviewRequest, await bounded_private_body(request, 1024 * 1024))
        environment = "" if body.decision == "withdraw" else processing_environment()
        result = await run_in_threadpool(
            get_ctx().repo.review_private_counterfactual, company_id, revision_id, body, environment
        )
        return result.model_dump(mode="json")


@app.get("/companies/{company_id}/private-counterfactuals/revisions/{revision_id}/reviews")
def private_counterfactual_reviews(company_id: str, revision_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        return {
            "reviews": [
                r.model_dump(mode="json")
                for r in get_ctx().repo.list_private_counterfactual_reviews(company_id, revision_id)
            ],
            "historical_records_only": True,
            "causal_value_claim": False,
        }


@app.get("/companies/{company_id}/private-counterfactuals/revisions/{revision_id}/usable")
def usable_private_counterfactual(company_id: str, revision_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        proposal, review = get_ctx().repo.usable_private_counterfactual(
            company_id, revision_id, processing_environment()
        )
        return {
            "revision": proposal.model_dump(mode="json"),
            "review": review.model_dump(mode="json"),
            "usable_for_comparison": True,
            "causal_value_claim": False,
        }


@app.post("/companies/{company_id}/private-observations/cases/{case_key}/streams/{key}", status_code=201)
async def record_private_observation(
    company_id: str, case_key: str, key: str, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request, write=True):
        require_snapshot_writer(company_id)
        body = parse_private(PrivateObservationRequest, await bounded_private_body(request, 1024 * 1024))
        result = await run_in_threadpool(
            get_ctx().repo.record_private_observation, company_id, case_key, key, body, processing_environment()
        )
        return result.model_dump(mode="json")


@app.get("/companies/{company_id}/private-observations/cases/{case_key}/streams/{key}")
def private_observation_history(
    company_id: str, case_key: str, key: str, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request):
        return {
            "observations": [
                r.model_dump(mode="json") for r in get_ctx().repo.list_private_observations(company_id, case_key, key)
            ],
            "historical_records_only": True,
            "causal_value_claim": False,
        }


@app.get("/companies/{company_id}/private-observations/observations/{observation_id}/usable")
def usable_private_observation(company_id: str, observation_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        result = get_ctx().repo.usable_private_observation(company_id, observation_id, processing_environment())
        return {
            "observation": result.model_dump(mode="json"),
            "usable_for_comparison": True,
            "causal_value_claim": False,
            "operating_action_authorized": False,
        }


@app.post("/companies/{company_id}/private-capacity/revisions/{revision_id}/reviews/{review_kind}", status_code=201)
async def review_private_capacity(
    company_id: str,
    revision_id: str,
    review_kind: ReviewKind,
    request: Request,
    p: Principal,
) -> dict[str, Any]:
    with case_request(p, request, write=True):
        require_private_plan_reviewer(company_id, review_kind)
        body = parse_private(PlanReviewRequest, await bounded_private_body(request, 1024 * 1024))
        if body.review_kind != review_kind:
            raise ValueError("review body does not match the requested review role")
        environment = "" if body.decision == "withdraw" else processing_environment()
        result = await run_in_threadpool(
            get_ctx().repo.review_private_capacity, company_id, revision_id, body, environment
        )
        return result.model_dump(mode="json")


@app.get("/companies/{company_id}/private-capacity/revisions/{revision_id}/reviews")
def private_plan_review_history(company_id: str, revision_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        return {
            "reviews": [
                r.model_dump(mode="json") for r in get_ctx().repo.list_private_plan_reviews(company_id, revision_id)
            ],
            "historical_records_only": True,
            "operating_action_authorized": False,
        }


@app.post("/companies/{company_id}/private-baselines/cases/{case_key}", status_code=201)
async def freeze_private_baseline(company_id: str, case_key: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request, write=True):
        require_private_baseline_author(company_id)
        environment = processing_environment()
        body = parse_private(BaselineRequest, await bounded_private_body(request, 1024 * 1024))
        result = await run_in_threadpool(
            get_ctx().repo.freeze_private_baseline, company_id, case_key, body, environment
        )
        return result.model_dump(mode="json")


@app.get("/companies/{company_id}/private-baselines/cases/{case_key}")
def private_baseline_history(company_id: str, case_key: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        return {
            "baselines": [
                b.model_dump(mode="json") for b in get_ctx().repo.list_private_baselines(company_id, case_key)
            ],
            "historical_records_only": True,
            "operating_action_authorized": False,
        }


@app.get("/companies/{company_id}/private-baselines/designations/{baseline_id}/status")
def private_baseline_status(company_id: str, baseline_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        return get_ctx().repo.private_baseline_status(company_id, baseline_id, processing_environment())


@app.post("/companies/{company_id}/private-capacity/cases/{case_key}", status_code=201)
async def record_private_capacity_plan(
    company_id: str, case_key: str, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request, write=True):
        require_intake_writer(company_id)
        environment = processing_environment()
        body = parse_private(CapacityPlanRequest, await bounded_private_body(request, 1024 * 1024))
        revision = await run_in_threadpool(
            get_ctx().repo.record_private_capacity_plan, company_id, case_key, body, environment
        )
        return revision.model_dump(mode="json")


@app.get("/companies/{company_id}/private-capacity/cases/{case_key}")
def private_capacity_history(company_id: str, case_key: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        revisions = get_ctx().repo.list_private_capacity_plans(company_id, case_key)
        return {
            "revisions": [r.model_dump(mode="json") for r in revisions],
            "historical_records_only": True,
            "operating_action_authorized": False,
        }


@app.get("/companies/{company_id}/private-capacity/revisions/{revision_id}/usable")
def usable_private_capacity_plan(company_id: str, revision_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        revision = get_ctx().repo.usable_private_capacity_plan(company_id, revision_id, processing_environment())
        return {
            "revision": revision.model_dump(mode="json"),
            "source_currently_accepted": True,
            "operating_action_authorized": False,
        }


@app.post("/companies/{company_id}/private-underwriting/cases/{case_key}", status_code=201)
async def record_private_underwriting(company_id: str, case_key: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request, write=True):
        require_intake_writer(company_id)
        environment = processing_environment()
        body = parse_private(UnderwritingRequest, await bounded_private_body(request, 1024 * 1024))
        revision = await run_in_threadpool(
            get_ctx().repo.record_private_underwriting, company_id, case_key, body, environment
        )
        return revision.model_dump(mode="json")


@app.get("/companies/{company_id}/private-underwriting/cases/{case_key}")
def private_underwriting_history(company_id: str, case_key: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        revisions = get_ctx().repo.list_private_underwriting(company_id, case_key)
        return {
            "revisions": [r.model_dump(mode="json") for r in revisions],
            "historical_records_only": True,
            "operating_action_authorized": False,
        }


@app.get("/companies/{company_id}/private-underwriting/revisions/{revision_id}/usable")
def usable_private_underwriting(company_id: str, revision_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        revision = get_ctx().repo.usable_private_underwriting(company_id, revision_id, processing_environment())
        return {
            "revision": revision.model_dump(mode="json"),
            "source_currently_accepted": True,
            "operating_action_authorized": False,
        }


@app.post("/companies/{company_id}/private-financials/cases/{case_key}", status_code=201)
async def record_private_financial_snapshot(
    company_id: str, case_key: str, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request, write=True):
        require_snapshot_writer(company_id)
        environment = processing_environment()
        body = parse_private(FinancialSnapshotRequest, await bounded_private_body(request, 1024 * 1024))
        snapshot = await run_in_threadpool(
            get_ctx().repo.record_private_financial_snapshot, company_id, case_key, body, environment
        )
        return snapshot.model_dump(mode="json")


@app.get("/companies/{company_id}/private-financials/cases/{case_key}")
def private_financial_history(company_id: str, case_key: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        snapshots = get_ctx().repo.list_private_financial_snapshots(company_id, case_key)
        return {
            "snapshots": [s.model_dump(mode="json") for s in snapshots],
            "historical_records_only": True,
            "operating_action_authorized": False,
        }


@app.get("/companies/{company_id}/private-financials/snapshots/{snapshot_id}/usable")
def usable_private_financial_snapshot(
    company_id: str, snapshot_id: str, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request):
        snapshot = get_ctx().repo.usable_private_financial_snapshot(company_id, snapshot_id, processing_environment())
        return {
            "snapshot": snapshot.model_dump(mode="json"),
            "source_currently_accepted": True,
            "operating_action_authorized": False,
        }


def processing_environment() -> str:
    environment = os.environ.get("PVC_PROCESSING_ENVIRONMENT_ID", "").strip()
    if not environment:
        raise HTTPException(503, "Private processing environment is not configured")
    return environment


async def bounded_private_body(request: Request, limit: int) -> bytes:
    # Authentication and company/role checks must precede calling this helper.
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(413, "Private request exceeds the size limit")
        body.extend(chunk)
    return bytes(body)


@app.post("/companies/{company_id}/private-intakes/datasets/{dataset_key}", status_code=201)
async def record_private_intake(company_id: str, dataset_key: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request, write=True):
        require_intake_writer(company_id)
        environment = processing_environment()
        body = parse_private(PrivateUpload, await bounded_private_body(request, 16 * 1024 * 1024))
        try:
            raw = base64.b64decode(body.source_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid private source encoding") from exc
        record = await run_in_threadpool(
            get_ctx().repo.record_private_intake, company_id, dataset_key, body.intake, raw, environment
        )
        return record.model_dump(mode="json")


@app.get("/companies/{company_id}/private-intakes/datasets/{dataset_key}")
def private_intake_history(company_id: str, dataset_key: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        records = get_ctx().repo.list_private_intakes(company_id, dataset_key)
        return {
            "intakes": [r.model_dump(mode="json") for r in records],
            "current_intake_id": records[-1].intake_id if records else None,
            "operating_action_authorized": False,
        }


@app.post("/companies/{company_id}/private-intakes/{intake_id}/reviews", status_code=201)
async def review_private_intake(company_id: str, intake_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request, write=True):
        require_finance_reviewer(company_id)
        environment = processing_environment()
        body = parse_private(FinanceReviewRequest, await bounded_private_body(request, 1024 * 1024))
        record = await run_in_threadpool(get_ctx().repo.review_private_intake, company_id, intake_id, body, environment)
        return record.model_dump(mode="json")


@app.get("/companies/{company_id}/private-intakes/{intake_id}/reviews")
def private_finance_history(company_id: str, intake_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        return {
            "reviews": [
                r.model_dump(mode="json") for r in get_ctx().repo.list_private_finance_reviews(company_id, intake_id)
            ]
        }


@app.get("/companies/{company_id}/private-intakes/{intake_id}/source")
def private_intake_source(
    company_id: str, intake_id: str, request: Request, p: Principal, accepted_only: bool = False
) -> Response:
    with case_request(p, request):
        raw = get_ctx().repo.private_intake_source(
            company_id, intake_id, processing_environment(), accepted_only=accepted_only
        )
        return Response(
            raw,
            media_type="application/octet-stream",
            headers={"Content-Disposition": 'attachment; filename="private-ledger.json"'},
        )


@app.get("/cases/{case_id}")
def case_history(case_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        repo = get_ctx().repo
        case = repo.get_investment_case(case_id)
        # Bind this read to the observed head; a concurrent append cannot make the
        # comparison silently include a newer revision than the returned case.
        revisions = [r for r in repo.list_case_revisions(case_id) if r.sequence <= case.version]
        revision_ids = {r.revision_id for r in revisions}
        reviews = [r for r in repo.list_case_reviews(case_id) if r.revision_id in revision_ids]
        baselines = [b for b in repo.list_close_baselines(case_id) if b.request.revision_id in revision_ids]
        by_revision = {r.revision_id: r for r in revisions}
        return {
            "close_baselines": [
                close_baseline_view(b, by_revision[b.request.revision_id], reviews, baselines) for b in baselines
            ],
            "case": case.model_dump(mode="json"),
            "revisions": [r.model_dump(mode="json") for r in revisions],
            "reviews": [r.model_dump(mode="json") for r in reviews],
            "comparison": compare_revisions(revisions[0], revisions[-1]) if revisions else None,
        }


@app.post("/cases/{case_id}/execution-events", status_code=201)
def record_execution_event(case_id: str, body: ExecutionRequest, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request, write=True):
        return get_ctx().repo.record_execution_event(case_id, body).model_dump(mode="json")


@app.get("/cases/{case_id}/execution/{baseline_id}")
def case_execution(case_id: str, baseline_id: str, as_of: date, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        return get_ctx().repo.case_execution(case_id, baseline_id, as_of)


@app.post("/cases/{case_id}/observations", status_code=201)
def record_case_observation(case_id: str, body: ObservationRequest, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request, write=True):
        return get_ctx().repo.record_case_observation(case_id, body).model_dump(mode="json")


@app.post("/cases/{case_id}/attributions", status_code=201)
def record_case_attribution(case_id: str, body: AttributionRequest, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request, write=True):
        return get_ctx().repo.record_case_attribution(case_id, body).model_dump(mode="json")


@app.get("/cases/{case_id}/realization/{baseline_id}")
def case_realization(case_id: str, baseline_id: str, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request):
        return get_ctx().repo.case_realization(case_id, baseline_id)


@app.post("/cases/{case_id}/close-baselines", status_code=201)
def designate_close_baseline(
    case_id: str, body: CloseBaselineRequest, request: Request, p: Principal
) -> dict[str, Any]:
    with case_request(p, request, write=True):
        return get_ctx().repo.designate_close_baseline(case_id, body).model_dump(mode="json")


@app.post("/cases/{case_id}/revisions", status_code=201)
def append_case_revision(case_id: str, body: CaseRevisionIn, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request, write=True):
        return (
            get_ctx()
            .repo.append_case_revision(case_id, body.expected_parent_revision_id, body.draft)
            .model_dump(mode="json")
        )


@app.post("/case-revisions/{revision_id}/reviews", status_code=201)
def review_case_revision(revision_id: str, body: ReviewRequest, request: Request, p: Principal) -> dict[str, Any]:
    with case_request(p, request, write=True):
        return get_ctx().repo.review_case_revision(revision_id, body).model_dump(mode="json")


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


def _demo_login_response(*, error: str | None = None, status_code: int = 200) -> HTMLResponse:
    csrf = secrets.token_urlsafe(24)
    response = HTMLResponse(views.login_page(csrf, error=error), status_code=status_code)
    response.set_cookie("pvc_login_csrf", csrf, httponly=True, samesite="strict", max_age=600)
    return response


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> Response:
    try:
        principal = current_principal(request)
    except HTTPException as exc:
        if exc.status_code != 401 or os.environ.get("PVC_ENV") != "dev":
            raise
        return _demo_login_response()
    with scoped(principal):
        ctx = get_ctx()
        runs = ctx.repo.list_runs()
        latest: dict[str, RunRecord] = {}
        for run in sorted(runs, key=lambda r: (r.created_at, r.run_id), reverse=True):
            latest.setdefault(run.company_id, run)
        companies = {}
        plans = {}
        gaps = {}
        decisions = {}
        for company_id, run in latest.items():
            try:
                companies[company_id] = ctx.repo.get_company(company_id)
            except NotFound:
                pass  # A queued assessment can precede company intake.
            plan = ctx.repo.latest_plan(run.run_id)
            records = ctx.repo.list_approvals(run.run_id)
            if records:
                decisions[run.run_id] = records[-1]
                if plan is not None and records[-1].decision is not None:
                    approved = records[-1].edits.get("approved_plan")
                    if records[-1].decision == ApprovalDecision.APPROVED:
                        plan = plan.model_copy(
                            update={
                                "approved_plan": approved if approved is not None else plan.plan,
                                "status": "approved",
                            }
                        )
                    elif records[-1].decision in {ApprovalDecision.REJECTED, ApprovalDecision.CHANGES_REQUESTED}:
                        plan = plan.model_copy(
                            update={
                                "status": "rejected"
                                if records[-1].decision == ApprovalDecision.REJECTED
                                else "superseded"
                            }
                        )
            if plan is not None:
                plans[run.run_id] = plan
            gaps[run.run_id] = sum(f.finding_type.value == "data_gap" for f in ctx.repo.list_findings(run.run_id))
    return HTMLResponse(
        views.home_page(
            runs,
            dev=os.environ.get("PVC_ENV") == "dev",
            companies=companies,
            plans=plans,
            gaps=gaps,
            decisions=decisions,
        )
    )


@app.post("/dev/login")
def dev_login(request: Request, token: Annotated[str, Form()], csrf: Annotated[str, Form()]) -> Response:
    if os.environ.get("PVC_ENV") != "dev":
        raise HTTPException(404, "Not found")
    expected = request.cookies.get("pvc_login_csrf", "")
    if not expected or not secrets.compare_digest(csrf, expected):
        return _demo_login_response(
            error="This sign-in page expired. Enter the local approver token and try again.", status_code=403
        )
    token = token.strip()
    claims = _dev_tokens().get(token)
    if not claims:
        return _demo_login_response(
            error="That token was not recognized. Copy the current token and try again.", status_code=401
        )
    try:
        principal_from_claims(claims)
    except (TypeError, ValueError, PyJWTError):
        return _demo_login_response(
            error="That token was not recognized. Copy the current token and try again.", status_code=401
        )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("pvc_dev_session", token, httponly=True, samesite="strict", max_age=3600)
    response.delete_cookie("pvc_login_csrf")
    return response


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/readyz")
def readyz() -> JSONResponse:
    from ..readiness import is_ready

    try:
        ready = is_ready(get_ctx())
    except Exception:
        ready = False
    return JSONResponse({"status": "ready" if ready else "unready"}, status_code=200 if ready else 503)


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
    decision: Annotated[str, Form()] = "",
    csrf: Annotated[str, Form()] = "",
    rationale: Annotated[str, Form()] = "",
    remove_initiatives: Annotated[list[str] | None, Form()] = None,
) -> Response:
    with scoped(p):
        _load_run(run_id)
        expected_csrf = request.cookies.get("pvc_csrf", "")
        if not expected_csrf or not secrets.compare_digest(csrf, expected_csrf):
            return _review_response(
                run_id,
                p,
                error="This decision form expired. Review your choices and submit again.",
                status_code=403,
                rationale=rationale,
                selected_initiatives=remove_initiatives,
            )
        if decision not in ("approved", "rejected", "changes_requested"):
            return _review_response(
                run_id,
                p,
                error="Choose approve, request changes or reject.",
                status_code=422,
                rationale=rationale,
                selected_initiatives=remove_initiatives,
            )
        try:
            _decide(
                run_id,
                p,
                DecisionIn.model_validate(
                    {
                        "decision": decision,
                        "rationale": rationale or None,
                        "remove_initiatives": remove_initiatives or [] if decision == "approved" else [],
                        "exclude_opportunities": remove_initiatives or [] if decision == "changes_requested" else [],
                    }
                ),
            )
        except HTTPException as exc:
            if exc.status_code not in {403, 422}:
                raise
            return _review_response(
                run_id,
                p,
                error=str(exc.detail),
                status_code=exc.status_code,
                rationale=rationale,
                selected_initiatives=remove_initiatives,
            )
    return RedirectResponse(f"/runs/{run_id}/review", status_code=303)


@app.get("/runs/{run_id}/review", response_class=HTMLResponse)
def review(run_id: str, p: Principal) -> HTMLResponse:
    return _review_response(run_id, p)


def _review_response(
    run_id: str,
    p: security.Principal,
    *,
    error: str | None = None,
    status_code: int = 200,
    rationale: str = "",
    selected_initiatives: list[str] | None = None,
) -> HTMLResponse:
    ctx = get_ctx()
    with scoped(p):
        run = _load_run(run_id)
        opps = ctx.repo.list_opportunities(run_id)
        cases = {v.opportunity_id: v for v in ctx.repo.list_value_cases(run_id)}
        approvals_ = ctx.repo.list_approvals(run_id)
        csrf = secrets.token_urlsafe(24)
        can = approvals.can_approve(p, run.company_id, ctx.policy.approval.approver_role)
        try:
            company = ctx.repo.get_company(run.company_id)
        except NotFound:
            company = None
        html = views.review_page(
            run,
            ctx.repo.latest_plan(run_id),
            opps,
            cases,
            ctx.repo.list_findings(run_id),
            approvals_[-1] if approvals_ else None,
            csrf,
            can,
            company_name=company.name if company else None,
            currency=company.currency if company else None,
            error=error,
            rationale=rationale,
            selected_initiatives=selected_initiatives,
            workflow_state=primary.status(ctx, run_id),
        )
    resp = HTMLResponse(html, status_code=status_code)
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
            "Content-Disposition": f"inline; filename=\"evidence.txt\"; filename*=UTF-8''{quote(name, safe='')}",
            "X-Content-Hash": ev.content_hash,
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/evidence/{evidence_id}/review", response_class=HTMLResponse)
def evidence_review(evidence_id: str, p: Principal, run_id: str | None = None) -> HTMLResponse:
    ctx = get_ctx()
    with scoped(p):
        try:
            ev = ctx.repo.get_evidence(evidence_id)
            content = ctx.repo.evidence_content(evidence_id)
            if run_id and _load_run(run_id).company_id != ev.company_id:
                raise HTTPException(404, "Evidence not found for this company")
            try:
                company = ctx.repo.get_company(ev.company_id)
            except NotFound:
                company = None
        except (NotFound, EvidenceNotFound) as exc:
            raise HTTPException(404, "Evidence not found") from exc
    return HTMLResponse(
        views.evidence_page(ev, content, company_name=company.name if company else ev.company_id, run_id=run_id)
    )


@app.get("/companies/{company_id}/kpis", response_class=HTMLResponse)
def kpis(company_id: str, p: Principal, run_id: str | None = None) -> HTMLResponse:
    ctx = get_ctx()
    with scoped(p):
        try:
            defs = ctx.repo.list_kpi_definitions(company_id, active_only=not bool(run_id))
            obs = ctx.repo.list_kpi_observations(company_id)
            if run_id:
                if _load_run(run_id).company_id != company_id:
                    raise HTTPException(404, "Run not found for this company")
                defs = [d for d in defs if d.run_id == run_id]
                ids = {d.kpi_id for d in defs}
                obs = [o for o in obs if o.kpi_id in ids]
            try:
                company = ctx.repo.get_company(company_id)
            except NotFound:
                company = None
        except security.ScopeError as e:
            raise HTTPException(404, "Company not found") from e
    return HTMLResponse(
        views.kpi_page(
            company_id,
            defs,
            obs,
            company_name=company.name if company else None,
            currency=company.currency if company else None,
            include_inactive=bool(run_id),
        )
    )


@app.get("/metrics/approvals")
def approval_metrics(p: Principal) -> dict[str, Any]:
    with scoped(p):
        return approvals.override_stats(get_ctx())


@app.exception_handler(security.ScopeError)
def _scope_error(_: Request, exc: security.ScopeError) -> JSONResponse:
    return JSONResponse({"detail": "Not found"}, status_code=404)
