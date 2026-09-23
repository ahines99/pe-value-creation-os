"""Operational commands: recompute (PVC-145), offboarding deletion (PVC-144), access review and audit export
(PVC-146), and the onboarding readiness check (PVC-155). Every command that changes state writes an audit event
first; the readiness check is read-only.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .domain.models import AuditEvent
from .domain.prioritization import prioritize
from .domain.services import CALC_VERSION, size_value_case
from .workflows.steps import RunContext


def _audit(
    ctx: RunContext, company_id: str, event_type: str, actor: str, run_id: str | None = None, **payload: Any
) -> None:
    ctx.repo.append_audit(
        AuditEvent(
            run_id=run_id,
            company_id=company_id,
            step="ops",
            actor=actor,
            event_type=event_type,
            created_at=datetime.now(UTC),
            payload=payload,
        )
    )


def recompute_run(ctx: RunContext, run_id: str, actor: str, *, reason: str) -> dict[str, Any]:
    """Re-size every opportunity in a run with the current calculation version. Superseded value cases are kept."""
    if not reason.strip():
        raise ValueError("A reason (incident or ticket id) is required")
    run = ctx.repo.get_run(run_id)
    changes = []
    items = []
    for opp in ctx.repo.list_opportunities(run_id):
        before = ctx.repo.get_value_case(run.company_id, opp.opportunity_id)
        after = size_value_case(opp)
        items.append((opp, after))
        if (before.calc_version, before.annual_ebitda_base) != (after.calc_version, after.annual_ebitda_base):
            ctx.repo.save_value_case(run.company_id, run_id, after, ctx.policy.version)
            changes.append(
                {
                    "opportunity_id": opp.opportunity_id,
                    "calc_version_before": before.calc_version,
                    "calc_version_after": after.calc_version,
                    "base_before": str(before.annual_ebitda_base),
                    "base_after": str(after.annual_ebitda_base),
                }
            )
    if changes:
        ctx.repo.save_priorities(run_id, run.company_id, prioritize(items, ctx.policy))
    _audit(
        ctx,
        run.company_id,
        "value_cases_recomputed",
        actor,
        run_id,
        reason_code=reason[:80],
        count=len(changes),
        calc_version=CALC_VERSION,
    )
    return {"run_id": run_id, "calc_version": CALC_VERSION, "changed": changes, "unchanged": len(items) - len(changes)}


def offboard_company(ctx: RunContext, company_id: str, actor: str) -> dict[str, Any]:
    """Delete a company's data and evidence per docs/data_retention.md. Audit events are retained."""
    _audit(ctx, company_id, "company_offboarding_started", actor)
    try:
        counts = ctx.repo.delete_company_data(company_id)
    except Exception as exc:
        # Deletion is idempotent: fix the cause (e.g. storage permissions) and re-run `pvc offboard`.
        _audit(ctx, company_id, "company_offboarding_failed", actor, error_type=type(exc).__name__)
        raise
    _audit(ctx, company_id, "company_offboarded", actor, deleted=counts)
    return {"company_id": company_id, "deleted": counts, "audit_retained": True}


def export_audit(ctx: RunContext, company_id: str, out: Path) -> int:
    events = ctx.repo.list_audit(company_id=company_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e.model_dump(mode="json"), sort_keys=True) + "\n")
    return len(events)


def access_review(
    grants_file: Path | None, *, now: datetime | None = None, stale_days: int = 90, max_companies_per_approver: int = 5
) -> dict[str, Any]:
    """Quarterly access review from an identity-provider export.

    Input JSON: [{"subject", "principal_type", "roles": [...], "pvc_companies": [...], "last_login": ISO8601}, ...]
    Findings: model or service principals holding the approver role, approvers spanning many companies,
    principals with no login within `stale_days`, and human principals with no company scope.
    """
    now = now or datetime.now(UTC)
    if grants_file is None:
        return {
            "generated_at": now.isoformat(),
            "principals": 0,
            "findings": [],
            "note": "Provide --grants with the identity-provider export to review principals.",
        }
    grants = json.loads(grants_file.read_text(encoding="utf-8"))
    findings: list[dict[str, str]] = []
    for g in grants:
        sub, ptype, roles, cos = (
            g["subject"],
            g.get("principal_type", "service"),
            set(g.get("roles", [])),
            set(g.get("pvc_companies", [])),
        )
        if "approver" in roles and ptype != "human":
            findings.append({"subject": sub, "severity": "high", "finding": "non-human principal holds approver role"})
        if "approver" in roles and len(cos) > max_companies_per_approver:
            findings.append(
                {
                    "subject": sub,
                    "severity": "medium",
                    "finding": f"approver scoped to {len(cos)} companies (> {max_companies_per_approver})",
                }
            )
        last = g.get("last_login")
        if last and now - datetime.fromisoformat(last) > timedelta(days=stale_days):
            findings.append(
                {"subject": sub, "severity": "medium", "finding": f"no login for more than {stale_days} days"}
            )
        if ptype == "human" and not cos:
            findings.append({"subject": sub, "severity": "low", "finding": "human principal with no company scope"})
    return {"generated_at": now.isoformat(), "principals": len(grants), "findings": findings}


def onboarding_check(adapter: Any, company_id: str, policy: Any) -> dict[str, Any]:
    """Read-only readiness report for a new company (PVC-155): what loaded, how fresh it is, which analyses the
    data supports, and entity-resolution results. Nothing is stored and no run is started."""
    from .domain import sufficiency
    from .freshness import source_ages

    data = adapter.load(company_id)
    ages = source_ages(data)
    stale = sorted(d for d, a in ages.items() if a > policy.freshness.max_age_days)
    results = sufficiency.check_all(data, policy)
    sufficient = sorted(a for a, r in results.items() if r.sufficient)
    needed = policy.run.min_sufficient_analyses
    return {
        "company_id": company_id,
        "reference_date": data.reference_date.isoformat(),
        "ready": len(sufficient) >= needed,
        "sufficient_analyses": sufficient,
        "min_sufficient_analyses": needed,
        "datasets": [{**d, "age_days": ages.get(d["kind"])} for d in data.inventory()],
        "stale_datasets": stale,
        "gaps": {a: [g.model_dump() for g in r.gaps] for a, r in results.items() if r.gaps},
        "entity_resolution": data.entity_resolution,
        "policy_version": policy.version,
    }
