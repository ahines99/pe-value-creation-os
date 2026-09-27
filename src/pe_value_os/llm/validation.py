"""Interactive boundaries reuse calculation, screening and evidence policy."""

from __future__ import annotations

from typing import Any

from ..domain import sufficiency
from ..domain.baselines import baseline_overlap
from ..domain.project_models import Opportunity
from .eligibility import BRANCH, branch_context, eligibility_error
from .quantities import SourceQuantity, render_claims, source_quantities


def interactive_sources(ctx: Any, data: Any, contexts: dict[str, Any] | None = None) -> dict[str, SourceQuantity]:
    sources: dict[str, SourceQuantity] = {}
    contexts = contexts if contexts is not None else {}
    for branch in sufficiency.ANALYSES:
        if not sufficiency.check(data, branch, ctx.policy).sufficient:
            continue
        context = branch_context(data, branch, ctx.policy)
        contexts[branch] = context
        sources.update(
            source_quantities(
                context.result,
                company_id=data.company_id,
                evidence_ids=context.evidence_ids,
                period=str(data.reference_date),
                prefix=branch,
            )
        )
    return sources


def validate_interactive_opportunity(
    ctx: Any,
    data: Any,
    opp: Opportunity,
    existing: list[Opportunity],
    *,
    sources: dict[str, SourceQuantity] | None = None,
    contexts: dict[str, Any] | None = None,
) -> None:
    branch = BRANCH[opp.lever]
    if contexts is None:
        contexts = {}
        sources = interactive_sources(ctx, data, contexts)
    if branch not in contexts:
        raise ValueError(f"INSUFFICIENT {branch}: required source data are missing, invalid or stale")
    eligible = eligibility_error(contexts[branch], opp.lever, opp.baseline_metric, opp.metric_params)
    if eligible:
        raise ValueError(eligible)
    known = {e.evidence_id: e for e in ctx.repo.list_evidence(data.company_id, opp.evidence_ids)}
    if not opp.evidence_ids or set(opp.evidence_ids) - set(known):
        raise ValueError("Evidence missing or outside this company")
    if any(
        e.as_of and (data.reference_date - e.as_of.date()).days > ctx.policy.freshness.max_age_days
        for e in known.values()
    ):
        raise ValueError("Evidence is stale")
    for other in existing:
        if other.opportunity_id == opp.opportunity_id:
            continue
        clash = baseline_overlap(opp.baseline_metric, opp.metric_params, other.baseline_metric, other.metric_params)
        if clash:
            raise ValueError(f"Overlapping opportunity: {clash}; update or start a new run")
    assert sources is not None
    for text in [opp.title, opp.rationale, *opp.assumptions]:
        render_claims(text, sources)


def validate_interactive_run(ctx: Any, data: Any, state: Any) -> None:
    from ..workflows.steps import evidence_review

    opportunities = ctx.repo.list_opportunities(state.run_id)
    contexts: dict[str, Any] = {}
    sources = interactive_sources(ctx, data, contexts)
    for opp in opportunities:
        validate_interactive_opportunity(ctx, data, opp, opportunities, sources=sources, contexts=contexts)
    review = evidence_review(ctx, state)
    if review["violations"]:
        raise ValueError(f"Evidence review failed: {review['violations']}")
