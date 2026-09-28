"""Reproduce a proposed, constructed plan; staffing and deliverables are not observed."""

from datetime import timedelta
from pathlib import Path

from scripts.build_underwriting_example import example as underwriting_example

from pe_value_os.diligence.scheduling import OperatingPlan, fingerprint


def example() -> OperatingPlan:
    case = underwriting_example()
    resources = [
        {
            "resource_id": key,
            "proposed_operator": operator,
            "weekly_hours": [hours] * 14 + ["0"],
            "basis": "Authored net change capacity after normal duties; no actual assignment or staff availability verified.",
        }
        for key, operator, hours in (
            ("finance", "Proposed finance lead", "20"),
            ("data", "Proposed data engineer", "24"),
            ("commercial", "Proposed commercial operations lead", "24"),
            ("service", "Proposed service operations lead", "20"),
        )
    ]
    tasks = []

    def add(key, title, stream, initiative, owner, weeks, prerequisites, demands, deliverable, evidence, reviewer):
        tasks.append(
            {
                "task_id": key,
                "title": title,
                "workstream_id": stream,
                "initiative_id": initiative,
                "accountable_resource": owner,
                "earliest_start": case.start.isoformat(),
                "duration_weeks": weeks,
                "prerequisites": prerequisites,
                "demands": [{"resource_id": resource, "hours_per_week": hours} for resource, hours in demands],
                "deliverable": deliverable,
                "acceptance_evidence": evidence,
                "acceptance_reviewer": reviewer,
            }
        )

    add(
        "foundation",
        "Reconcile scope and freeze baseline",
        "foundation",
        None,
        "finance",
        2,
        [],
        [("finance", 16), ("data", 24)],
        "Versioned source manifest and reconciliation exceptions",
        "Finance-reviewed tie-out and exclusions; no unresolved material scope mismatch",
        "Proposed finance reviewer",
    )
    add(
        "collections-review",
        "Confirm collectible cohort and terms",
        "collections",
        "collections-timing",
        "finance",
        2,
        ["foundation"],
        [("finance", 16), ("data", 8)],
        "Eligible invoice cohort with original payment-date counterfactual",
        "Aging reconciles to ledger; disputes and credits excluded; no term override",
        "Proposed controller",
    )
    add(
        "collections-gate",
        "Review bounded collection action",
        "collections",
        "collections-timing",
        "finance",
        2,
        ["collections-review"],
        [("finance", 16), ("data", 8)],
        "Contained intervention and harm-monitoring worksheet",
        "Manager reviews cohort, communication, quality stop and original collection dates",
        "Proposed company sponsor",
    )
    add(
        "pricing-review",
        "Test enforceability and retention downside",
        "pricing",
        "pricing-renewals",
        "commercial",
        3,
        ["foundation"],
        [("finance", 16), ("commercial", 20)],
        "Contract eligibility and combined price/churn challenge",
        "Notice dates, caps, channel terms and concessions reconciled; downside retained",
        "Proposed finance and commercial reviewers",
    )
    add(
        "pricing-gate",
        "Review renewal wave",
        "pricing",
        "pricing-renewals",
        "commercial",
        2,
        ["pricing-review"],
        [("finance", 8), ("commercial", 20)],
        "Proposed renewal cohort and monitoring plan",
        "Human decision on exact cohort; retention stop and contract notice checks complete",
        "Proposed commercial executive",
    )
    add(
        "service-trial",
        "Evaluate service quality and cost action",
        "service",
        "service-automation",
        "service",
        4,
        ["foundation"],
        [("data", 24), ("finance", 4), ("service", 16)],
        "Evaluation set, recontact results and vendor-spend hypothesis",
        "Safe resolution/reopens assessed; removable cost confirmed separately from freed hours",
        "Proposed service and finance reviewers",
    )
    add(
        "service-gate",
        "Review rollout and vendor commitment",
        "service",
        "service-automation",
        "service",
        3,
        ["service-trial"],
        [("data", 16), ("finance", 8), ("service", 16)],
        "Bounded rollout, vendor action and rollback plan",
        "Quality threshold, vendor terms, HR/legal implications and rollback owner reviewed",
        "Proposed operations executive",
    )
    return OperatingPlan.model_validate(
        {
            "plan_id": "progress-constructed-100-day-plan",
            "revision_id": "capacity-draft-v1",
            "case_id": case.case_id,
            "underwriting_sha256": fingerprint(case),
            "classification": "constructed_operating_exercise",
            "start": case.start,
            "maximum_active_workstreams": 3,
            "sequencing_rationale": "Baseline first; validate the temporary cash mechanism before the higher-judgment renewal and service cases. This analyst-authored order demonstrates constrained sequencing, not a company priority decision or optimal schedule.",
            "resources": resources,
            "tasks": tasks,
            "priority_order": [t["task_id"] for t in tasks],
            "benefit_gates": [
                {"initiative_id": initiative, "task_id": task}
                for initiative, task in (
                    ("pricing-renewals", "pricing-gate"),
                    ("service-automation", "service-gate"),
                    ("collections-timing", "collections-gate"),
                )
            ],
        }
    )


if __name__ == "__main__":
    target = Path("data/constructed/progress/operating-plan.json")
    target.write_text(example().model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Wrote proposed constructed plan through {example().start + timedelta(days=99)}: {target}")
