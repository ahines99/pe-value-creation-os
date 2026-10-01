"""Explicit, immutable hypothetical-close designations; never operating authorization."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .. import security
from .cases import CaseReview, CaseRevision, InvestmentCase, writer
from .models import Record
from .record_chain import content_hash, seal_json

UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class CloseBaselineRequest(Record):
    revision_id: str = Field(pattern=UUID_PATTERN)
    revision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_id: str = Field(pattern=UUID_PATTERN)
    mode: Literal["human", "simulation"]
    scenario_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    expected_previous_id: str | None = Field(default=None, pattern=UUID_PATTERN)


class CloseBaseline(Record):
    baseline_id: str
    company_id: str
    case_id: str
    sequence: int = Field(ge=1)
    request: CloseBaselineRequest
    recorded_at: datetime
    actor: str
    actor_type: Literal["human", "service", "model"]
    classification: Literal["constructed_operating_exercise"] = "constructed_operating_exercise"
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if content_hash(self) != self.content_sha256:
            raise ValueError("close baseline content hash mismatch")
        if self.request.mode == "human" and self.actor_type != "human":
            raise ValueError("human baseline designation requires human authorship")
        return self


def prepare_close_baseline(
    case: InvestmentCase,
    revision: CaseRevision,
    reviews: list[CaseReview],
    request: CloseBaselineRequest,
    previous: CloseBaseline | None,
) -> CloseBaseline:
    from ..approvals import can_approve

    principal = writer(case.company_id)
    if request.mode == "human" and not can_approve(principal, case.company_id, "approver"):
        raise security.deny("Human baseline designation requires a human approver", "case_review_authority")
    if (
        revision.case_id != case.case_id
        or revision.company_id != case.company_id
        or revision.revision_id != case.current_revision_id
    ):
        raise ValueError("close baseline requires the current same-company case revision")
    if request.revision_id != revision.revision_id or request.revision_sha256 != revision.content_sha256:
        raise ValueError("close baseline must bind the exact stored revision")
    if revision.draft.stage != "close_validation" or revision.schedule_result_json is None:
        raise ValueError("close baseline requires a capacity-tested close-validation revision")
    schedule = json.loads(revision.schedule_result_json)
    if any(t["status"] == "blocked" for t in schedule["tasks"]):
        raise ValueError("blocked capacity cannot support a close baseline")
    financial = json.loads(revision.financial_result_json)
    if request.scenario_id not in {s["scenario_id"] for s in financial["scenarios"]}:
        raise ValueError("baseline scenario is not in the stored forecast")
    review = next((r for r in reviews if r.review_id == request.review_id), None)
    if review is None or (
        review.company_id,
        review.case_id,
        review.revision_id,
        review.revision_sha256,
        review.mode,
        review.decision,
    ) != (case.company_id, case.case_id, revision.revision_id, revision.content_sha256, request.mode, "accept"):
        raise ValueError("close baseline requires an accepted exact-revision review in the same mode")
    if any(r.supersedes_review_id == review.review_id for r in reviews):
        raise ValueError("superseded review cannot support a close baseline")
    if previous is not None and (previous.case_id, previous.company_id, previous.request.mode) != (
        case.case_id,
        case.company_id,
        request.mode,
    ):
        raise ValueError("baseline replacement must retain case, company and mode")
    if request.expected_previous_id != (previous.baseline_id if previous else None):
        raise ValueError("baseline replacement must bind the previous designation")
    raw: dict[str, Any] = {
        "baseline_id": str(uuid.uuid4()),
        "company_id": case.company_id,
        "case_id": case.case_id,
        "sequence": previous.sequence + 1 if previous else 1,
        "request": request.model_dump(mode="json"),
        "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "actor": principal.subject,
        "actor_type": principal.principal_type,
        "classification": "constructed_operating_exercise",
    }
    return seal_json(CloseBaseline, raw)


def close_baseline_view(
    baseline: CloseBaseline, revision: CaseRevision, reviews: list[CaseReview], baselines: list[CloseBaseline]
) -> dict[str, Any]:
    """Project validity without rewriting the original designation or recalculating its forecast."""
    if (baseline.case_id, baseline.company_id, baseline.request.revision_id, baseline.request.revision_sha256) != (
        revision.case_id,
        revision.company_id,
        revision.revision_id,
        revision.content_sha256,
    ):
        raise ValueError("baseline view requires its exact same-case revision")
    if any(r.case_id != baseline.case_id or r.company_id != baseline.company_id for r in reviews) or any(
        b.case_id != baseline.case_id or b.company_id != baseline.company_id for b in baselines
    ):
        raise ValueError("baseline view cannot mix cases or companies")
    review = next((r for r in reviews if r.review_id == baseline.request.review_id), None)
    current = not any(b.request.expected_previous_id == baseline.baseline_id for b in baselines)
    valid = (
        review is not None
        and review.decision == "accept"
        and review.mode == baseline.request.mode
        and review.revision_id == revision.revision_id
        and review.revision_sha256 == revision.content_sha256
        and not any(r.supersedes_review_id == review.review_id for r in reviews)
    )
    forecast = next(
        s
        for s in json.loads(revision.financial_result_json)["scenarios"]
        if s["scenario_id"] == baseline.request.scenario_id
    )
    return {
        "baseline": baseline.model_dump(mode="json"),
        "current_designation": current,
        "supporting_review_status": "accepted" if valid else "invalidated_or_missing",
        "usable_for_comparison": valid,
        "frozen_forecast": forecast,
        "authority": "Hypothetical-close comparison baseline for a constructed exercise. Not an acquisition, operating authorization or observed result. A new forecast never silently moves this baseline.",
    }
