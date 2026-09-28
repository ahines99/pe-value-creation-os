"""Reopen a conditional executive preference using an exact constructed case history."""

from __future__ import annotations

import json
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .cases import CaseReview, CaseRevision
from .models import Record
from .operating_sources import OperatingSourceBook, source_forecast
from .scheduling import OperatingPlan, fingerprint
from .source_revisions import SourceCasePayload, financial_snapshot
from .underwriting import UnderwritingCase


class MemoReviewContext(Record):
    classification: Literal["constructed_source_review_exercise"]
    revisions: tuple[CaseRevision, ...] = Field(min_length=2)
    reviews: tuple[CaseReview, ...]

    @model_validator(mode="after")
    def history(self) -> Self:
        first = self.revisions[0]
        if first.sequence != 1 or first.parent_revision_id is not None or first.draft.stage != "underwriting":
            raise ValueError("memo review requires the original case revision")
        ids = {r.revision_id: r for r in self.revisions}
        if len(ids) != len(self.revisions):
            raise ValueError("duplicate case revision")
        for revision in self.revisions:
            if revision.case_id != revision.draft.payload.underwriting.case_id:
                raise ValueError("revision envelope and underwriting case must agree")
        for prior, current in zip(self.revisions[:-1], self.revisions[1:], strict=True):
            a, b = prior.draft.payload.underwriting, current.draft.payload.underwriting
            if (
                current.sequence != prior.sequence + 1
                or current.parent_revision_id != prior.revision_id
                or (current.case_id, current.company_id) != (first.case_id, first.company_id)
                or (b.case_id, b.company, b.currency, b.start, b.months)
                != (a.case_id, a.company, a.currency, a.start, a.months)
                or current.draft.effective_on < prior.draft.effective_on
                or {(d.initiative_id, d.kind, d.benefit_pool) for d in a.scenarios[0].drivers}
                != {(d.initiative_id, d.kind, d.benefit_pool) for d in b.scenarios[0].drivers}
            ):
                raise ValueError("memo review requires a contiguous same-case comparison history")
            if isinstance(current.draft.payload, SourceCasePayload):
                current.draft.payload.bind_parent(prior)
            elif isinstance(prior.draft.payload, SourceCasePayload):
                raise ValueError("source basis cannot be discarded")
        seen: dict[str, CaseReview] = {}
        superseded: set[str] = set()
        for receipt in self.reviews:
            reviewed = ids.get(receipt.revision_id)
            if reviewed is None or (receipt.revision_sha256, receipt.case_id, receipt.company_id) != (
                reviewed.content_sha256,
                first.case_id,
                first.company_id,
            ):
                raise ValueError("memo review receipt requires its exact case revision")
            if receipt.mode != "simulation":
                raise ValueError("public constructed review context accepts simulation receipts only")
            if receipt.review_id in seen:
                raise ValueError("duplicate review receipt")
            if receipt.supersedes_review_id:
                old = seen.get(receipt.supersedes_review_id)
                if (
                    old is None
                    or old.review_id in superseded
                    or (old.revision_id, old.actor, old.actor_type, old.mode)
                    != (receipt.revision_id, receipt.actor, receipt.actor_type, receipt.mode)
                ):
                    raise ValueError("review correction must preserve the receipt's actor, revision and mode")
                superseded.add(old.review_id)
            elif receipt.decision == "withdraw":
                raise ValueError("withdrawal requires its original review receipt")
            seen[receipt.review_id] = receipt
        if not isinstance(self.revisions[-1].draft.payload, SourceCasePayload):
            raise ValueError("latest memo context must contain a source-backed revision")
        return self

    @classmethod
    def from_export(cls, raw: dict[str, Any]) -> MemoReviewContext:
        review = raw.get("source_review", {})
        return cls.model_validate(
            {
                "classification": review.get("classification"),
                "revisions": raw.get("revisions"),
                "reviews": review.get("reviews"),
            }
        )


def challenge_options(
    context: MemoReviewContext, original: UnderwritingCase, plan: OperatingPlan, options: list[dict[str, Any]]
) -> dict[str, Any]:
    first, parent, latest = context.revisions[0], context.revisions[-2], context.revisions[-1]
    if fingerprint(first.draft.payload.underwriting) != fingerprint(original) or not any(
        r.draft.payload.operating_plan is not None and fingerprint(r.draft.payload.operating_plan) == fingerprint(plan)
        for r in context.revisions
    ):
        raise ValueError("memo source review must descend from its exact original underwriting and plan")
    payload = latest.draft.payload
    assert isinstance(payload, SourceCasePayload)
    computed = financial_snapshot(
        payload, parent, source_forecast(payload.operating_sources, payload.underwriting, payload.operating_plan)
    )
    normalized = json.loads(json.dumps(computed, default=str, sort_keys=True))
    if normalized != json.loads(latest.financial_result_json):
        raise ValueError("stored source forecast differs from its reproduced inputs and calculator")
    challenged = []
    for option in options:
        proposed = OperatingPlan.model_validate(
            {
                **payload.operating_plan.model_dump(mode="json"),
                "priority_order": option["priority_order"],
                "revision_id": payload.operating_plan.revision_id + ":source-challenge:" + option["option_id"],
                "sequencing_rationale": option["rationale"],
            }
        )
        sources = OperatingSourceBook.model_validate(
            {
                **payload.operating_sources.model_dump(mode="json"),
                "plan_sha256": fingerprint(proposed),
            }
        )
        candidate = SourceCasePayload.model_validate(
            {
                **payload.model_dump(mode="json"),
                "operating_plan": proposed.model_dump(mode="json"),
                "operating_sources": sources.model_dump(mode="json"),
            }
        )
        evaluated = source_forecast(sources, payload.underwriting, proposed)
        financial = financial_snapshot(candidate, parent, evaluated)
        blocked = [t["task_id"] for t in evaluated["schedule"]["tasks"] if t["status"] == "blocked"]
        challenged.append(
            {
                "option_id": option["option_id"],
                "label": option["label"],
                "feasible": not blocked,
                "blocked_tasks": blocked,
                "plan": proposed.model_dump(mode="json"),
                "source_book_sha256": fingerprint(sources),
                "analysis": {
                    **{
                        k: v
                        for k, v in evaluated["schedule"].items()
                        if k not in {"scheduled_financials", "original_financials"}
                    },
                    "scheduled_financials": financial,
                },
            }
        )
    nonpositive = all(
        next(s for s in o["analysis"]["scheduled_financials"]["scenarios"] if s["scenario_id"] == "base")["year_one"][
            "incremental_ebitda"
        ]
        <= 0
        for o in challenged
    )
    superseded = {r.supersedes_review_id for r in context.reviews}
    active = [r for r in context.reviews if r.revision_id == latest.revision_id and r.review_id not in superseded]
    states = {r.decision for r in active}
    review_state = (
        "withdrawn_or_rejected"
        if states & {"withdraw", "reject"}
        else "changes_requested"
        if "request_changes" in states
        else "simulated_acceptance"
        if "accept" in states
        else "unreviewed"
    )
    return {
        "context_sha256": fingerprint(context),
        "context": context.model_dump(mode="json"),
        "current_revision_id": latest.revision_id,
        "current_revision_sha256": latest.content_sha256,
        "exercise_effective_on": latest.draft.effective_on,
        "recorded_at": latest.recorded_at,
        "review_state": review_state,
        "active_receipts": [r.model_dump(mode="json") for r in active],
        "latest_financials": computed,
        "options": challenged,
        "all_base_year_one_nonpositive": nonpositive,
        "status": "reopen_source_constrained_preference",
        "recommendation": "Reopen first-wave selection: every tested sequence has nonpositive base year-one EBITDA after the corrected source constraints and retained costs. Changing task order does not repair the business case."
        if nonpositive
        else "Reopen first-wave selection against the latest source constraints; compare economics, capacity and evidence before choosing an alternative.",
        "source_treatment": "Each alternative keeps the latest underwriting assumptions, source rows, resources, work packages and costs. Only priority order and its resulting dates change; source-book plan hashes are explicitly rebound to each hypothetical schedule.",
        "authority": "Derived research challenge, not a new case revision or operating approval. A receipt for the stored case does not accept these recomputed alternatives. Constructed exercise dates do not change the public-filing information cutoff; this is not a historical point-in-time forecast.",
    }
