"""Author a late acceptance and withdrawn-support rehearsal, without company data."""

import json
from pathlib import Path

from pe_value_os.diligence.cases import digest
from pe_value_os.diligence.execution_demo import ExecutionExercise
from pe_value_os.diligence.realization_render import RealizationExercise
from pe_value_os.diligence.scheduling import fingerprint


def example(realization: RealizationExercise) -> ExecutionExercise:
    extensions = []
    for name, start, end, amounts, ebitda, claims in [
        (
            "jan-close",
            "2027-01-01",
            "2027-01-31",
            [1030000, -334000, -1000, 690000, 0, 0],
            695000,
            [20000, 4000, -1000, 24000, 0, 0],
        ),
        (
            "feb-close",
            "2027-02-01",
            "2027-02-28",
            [1035000, -332000, -1000, 697000, 0, 0],
            702000,
            [22000, 6000, -1000, 30000, 0, 0],
        ),
    ]:
        month = realization.months[-1].model_dump(mode="json")
        month["corrects_source_id"] = None
        for key, values, total in [
            ("observed", amounts, ebitda),
            ("counterfactual", [1000000, -340000, 0, 660000, 0, 0], 660000),
        ]:
            book = month[key]
            book.update(
                source_id=name + ("-counterfactual" if key == "counterfactual" else ""),
                start=start,
                end=end,
                locator="data/constructed/progress/execution.json#" + name + "/" + key,
            )
            for row, value in zip(book["rows"], values, strict=True):
                row["amount"] = str(value)
                book["controls"][row["component"]] = str(value)
            book["controls"]["ebitda"] = str(total)
        support = (
            "Constructed "
            + name
            + " support: authored renewal and vendor-cost comparison, implementation cost and operating settlement. No company records, observed intervention or validated counterfactual. Financial claims are not promoted by recording work acceptance."
        )
        month["evidence"] = [
            dict(
                evidence_id=name + "-support",
                classification="constructed_attribution_evidence",
                content=support,
                sha256=digest(support),
            )
        ]
        template = month["allocations"][0]
        month["allocations"] = [
            {
                **template,
                "row_id": row["row_id"],
                "initiative_id": "pricing-renewals" if row["component"] == "revenue" else "service-automation",
                "amount": str(value),
                "evidence_ids": [name + "-support"],
                "rationale": "Author-assigned signed contribution; delivery support must be assessed separately.",
            }
            for row, value in zip(month["observed"]["rows"], claims, strict=True)
            if value
        ]
        month["rationale"] = (
            "Extend the explicitly constructed accounting exercise through "
            + end
            + " without deriving benefits from acceptance receipts."
        )
        extensions.append(month)
    steps = []

    def add(key, label, day, payload, content, previous=None, error=None):
        text = (
            "Constructed exercise evidence. "
            + content
            + " No actual employee, reviewer or company result is represented."
        )
        steps.append(
            dict(
                step_id=key,
                label=label,
                effective_on=day,
                payload=payload,
                evidence=[
                    dict(
                        evidence_id=key + "-evidence",
                        classification="constructed_execution_evidence",
                        content=text,
                        sha256=digest(text),
                    )
                ],
                rationale=content,
                previous_step=previous,
                expected_error=error,
            )
        )

    for resource in ("finance", "data", "commercial", "service"):
        add(
            "assign-" + resource,
            "Nominate " + resource + " operator",
            "2026-10-01",
            dict(
                kind="assignment",
                resource_id=resource,
                status="assigned",
                operator_subject="simulated:" + resource + "-operator",
                sponsor_subject="simulated:operating-sponsor",
            ),
            "Nominate one accountable operator and a sponsor; actual capacity usage is not measured.",
        )
    for initiative in ("pricing-renewals", "service-automation", "collections-timing"):
        add(
            "go-" + initiative,
            "Proceed with " + initiative,
            "2026-10-01",
            dict(kind="steering", initiative_id=initiative, decision="proceed"),
            "Simulated direction to proceed within the exercise; this is neither delivery acceptance nor company authorization.",
        )
    packages = [
        (
            "foundation",
            "finance",
            "2026-10-01",
            "2026-10-14",
            [],
            "Scope, cohort definitions and source-to-control mapping authored and checked; missing private records explicitly listed.",
        ),
        (
            "collections-review",
            "finance",
            "2026-10-15",
            "2026-10-28",
            ["foundation"],
            "Aging cohort and payment timing reviewed; collections movement is cash-only and temporary.",
        ),
        (
            "collections-gate",
            "finance",
            "2026-10-29",
            "2026-11-11",
            ["collections-review"],
            "Cash collection and reversal dates checked; no EBITDA uplift represented.",
        ),
        (
            "pricing-review",
            "commercial",
            "2026-11-12",
            "2026-12-02",
            ["foundation"],
            "Authored contract cohort, caps, notice and retention thresholds reviewed; price and churn effects remain combined.",
        ),
        (
            "pricing-gate",
            "commercial",
            "2026-12-03",
            "2026-12-16",
            ["pricing-review"],
            "Constructed exact renewal cohort and monitoring/stop conditions accepted for the exercise.",
        ),
        (
            "service-trial",
            "service",
            "2026-11-12",
            "2026-12-09",
            ["foundation"],
            "Authored safe-resolution/recontact results and removable vendor-cost hypothesis reviewed separately from freed hours.",
        ),
    ]
    for task, resource, start, end, deps, content in packages:
        add(
            task + "-submit",
            "Submit " + task,
            end,
            dict(
                kind="delivery",
                task_id=task,
                assignment="assign-" + resource,
                state="completed",
                started_on=start,
                completed_on=end,
            ),
            content,
        )
        add(
            task + "-accept",
            "Accept " + task,
            end,
            dict(
                kind="acceptance",
                task_id=task,
                delivery=task + "-submit",
                decision="accept",
                prerequisite_acceptances=[d + "-accept" for d in deps],
            ),
            content + " Reviewer accepts this exact submission and prerequisite chain in simulation.",
        )
    add(
        "service-hold",
        "Hold service rollout",
        "2026-12-15",
        dict(kind="steering", initiative_id="service-automation", decision="hold"),
        "Hold rollout pending vendor terms and rollback evidence; technical review may continue.",
        previous="go-service-automation",
    )
    add(
        "service-gate-submit",
        "Submit initial service gate",
        "2026-12-30",
        dict(
            kind="delivery",
            task_id="service-gate",
            assignment="assign-service",
            state="completed",
            started_on="2026-12-10",
            completed_on="2026-12-30",
        ),
        "Operator reports completion; review still needs to assess the vendor and rollback conditions.",
    )
    add(
        "service-gate-changes",
        "Request missing vendor evidence",
        "2026-12-30",
        dict(kind="acceptance", task_id="service-gate", delivery="service-gate-submit", decision="request_changes"),
        "Request changes: vendor minimum-spend release and rollback-owner acknowledgement are absent.",
    )
    add(
        "service-gate-resubmit",
        "Submit corrected service package",
        "2027-01-03",
        dict(
            kind="delivery",
            task_id="service-gate",
            assignment="assign-service",
            state="completed",
            started_on="2026-12-10",
            completed_on="2027-01-03",
        ),
        "Correct completion after authored vendor-release and rollback evidence arrives; retain the earlier submission.",
        previous="service-gate-submit",
    )
    add(
        "service-gate-accept",
        "Accept corrected service gate",
        "2027-01-03",
        dict(
            kind="acceptance",
            task_id="service-gate",
            delivery="service-gate-resubmit",
            decision="accept",
            prerequisite_acceptances=["service-trial-accept"],
        ),
        "Accept exact corrected submission; technical readiness does not itself lift the steering hold.",
        previous="service-gate-changes",
    )
    add(
        "service-resume",
        "Resume service exercise",
        "2027-01-04",
        dict(kind="steering", initiative_id="service-automation", decision="proceed"),
        "Explicitly resume after acceptance; no retroactive January full-month credit.",
        previous="service-hold",
    )
    add(
        "link-january-service",
        "Reject partial-month January support",
        "2027-01-31",
        dict(
            kind="claim_link",
            attribution_source_id="jan-close",
            row_id="operating_expense",
            initiative_id="service-automation",
            acceptance="service-gate-accept",
        ),
        "The gate was accepted on January 3; a monthly source cannot establish full-month support.",
        error="whole-month support requires gate acceptance",
    )
    add(
        "link-october-collections",
        "Reject October cash credit from a later gate",
        "2026-11-30",
        dict(
            kind="claim_link",
            attribution_source_id="oct-close",
            row_id="working_capital_cash",
            initiative_id="collections-timing",
            acceptance="collections-gate-accept",
        ),
        "The October collections claim predates the November gate; financial records remain unchanged.",
        error="whole-month support requires gate acceptance",
    )
    for month, day in [("jan", "2027-01-31"), ("feb", "2027-02-28")]:
        add(
            "link-" + month + "-pricing",
            "Link " + {"jan": "January", "feb": "February"}[month] + " pricing claim",
            day,
            dict(
                kind="claim_link",
                attribution_source_id=month + "-close",
                row_id="revenue",
                initiative_id="pricing-renewals",
                acceptance="pricing-gate-accept",
            ),
            "Delivery timing supports this whole-month claim; volume, mix and counterfactual quality still require attribution challenge.",
        )
    add(
        "link-feb-service",
        "Link February service claim",
        "2027-02-28",
        dict(
            kind="claim_link",
            attribution_source_id="feb-close",
            row_id="operating_expense",
            initiative_id="service-automation",
            acceptance="service-gate-accept",
        ),
        "Gate acceptance and proceed authority cover February; this does not prove incremental causal savings.",
    )
    add(
        "service-march-hold",
        "Hold service after February",
        "2027-03-01",
        dict(kind="steering", initiative_id="service-automation", decision="hold"),
        "Hold future activity after a vendor evidence challenge. A March hold does not erase February authority.",
        previous="service-resume",
    )
    add(
        "service-acceptance-withdraw",
        "Withdraw unsupported vendor acceptance",
        "2027-03-02",
        dict(kind="acceptance", task_id="service-gate", delivery="service-gate-resubmit", decision="withdraw"),
        "Withdraw acceptance: the authored vendor release did not cover the asserted minimum-spend removal. The linked February claim loses delivery support; source accounting and claimed amounts are preserved.",
        previous="service-gate-accept",
    )
    add(
        "link-stale-service",
        "Reject the withdrawn service acceptance",
        "2027-03-02",
        dict(
            kind="claim_link",
            attribution_source_id="feb-close",
            row_id="operating_expense",
            initiative_id="service-automation",
            acceptance="service-gate-accept",
        ),
        "An old acceptance cannot be reused after the reviewer withdraws it; the earlier link stays recorded but invalidated.",
        previous="link-feb-service",
        error="supporting execution receipt has been superseded",
    )
    steps.sort(key=lambda step: step["effective_on"])
    return ExecutionExercise.model_validate(
        dict(
            classification="constructed_operating_exercise",
            realization_sha256=fingerprint(realization),
            exercise_as_of="2027-03-02",
            observation_extensions=extensions,
            steps=steps,
        )
    )


if __name__ == "__main__":
    base = Path("data/constructed/progress")
    result = example(RealizationExercise.model_validate_json((base / "realization.json").read_bytes()))
    (base / "execution.json").write_text(json.dumps(result.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
