"""Author the disclosed realization fixture; never load private accounting data."""

import json
from pathlib import Path

from pe_value_os.diligence.cases import digest
from pe_value_os.diligence.realization import COMPONENTS
from pe_value_os.diligence.realization_render import RealizationExercise
from pe_value_os.diligence.scheduling import OperatingPlan, fingerprint
from pe_value_os.diligence.underwriting import UnderwritingCase


def example(case: UnderwritingCase, plan: OperatingPlan) -> RealizationExercise:
    months = []
    # Independent authored controls below deliberately retain a November posting
    # correction as its own snapshot. These are not audited company controls.
    specifications = [
        (
            "oct-close",
            "2026-10-01",
            "2026-10-31",
            [1005000, -338000, -50000, 570000, 180000, -5000],
            617000,
            None,
            [3000, 2000, -50000, -90000, 180000, -5000],
        ),
        (
            "nov-close-v1",
            "2026-11-01",
            "2026-11-30",
            [1020000, -344000, -16000, 673000, 0, -1000],
            660000,
            None,
            [14000, -4000, -16000, 10000, 0, -1000],
        ),
        (
            "nov-close-v2",
            "2026-11-01",
            "2026-11-30",
            [1018000, -344000, -16000, 673000, 0, -1000],
            658000,
            "nov-close-v1",
            [12000, -4000, -16000, 10000, 0, -1000],
        ),
        (
            "dec-close",
            "2026-12-01",
            "2026-12-31",
            [1026000, -334000, -3000, 681000, 0, 0],
            689000,
            None,
            [20000, 4000, -3000, 18000, 0, 0],
        ),
    ]
    for identity, start, end, observed, ebitda, previous, claims in specifications:
        scope = "Same three first-wave initiatives as the frozen forecast: monthly renewal revenue pool of USD 1,000,000; scoped variable servicing/vendor expense pool of USD 340,000; separately identified implementation expense, collections timing and capex. Not consolidated company accounts."

        def book(kind, values, control_ebitda, identity=identity, start=start, end=end, scope=scope):
            return dict(
                classification="constructed_operating_records",
                kind=kind,
                source_id=identity + ("-counterfactual" if kind != "observed" else ""),
                locator="data/constructed/progress/realization.json#" + identity + "/" + kind,
                case_id=case.case_id,
                currency=case.currency,
                unit_scale=1,
                start=start,
                end=end,
                scope_explanation=scope,
                method_and_limits="Analyst-authored monthly scoped records and flat no-intervention counterfactual; no seasonality, inflation, acquisition or mix estimate is validated. The sourcebook difference is not a causal estimate. No Progress contracts, ledger, invoices or staff records were used.",
                rows=[
                    dict(row_id=c, label=c.replace("_", " ").capitalize(), component=c, amount=str(v))
                    for c, v in zip(COMPONENTS, values, strict=True)
                ],
                controls={**dict(zip(COMPONENTS, map(str, values), strict=True)), "ebitda": str(control_ebitda)},
            )

        content = "Constructed exercise support: a matched renewal-cohort note attributes part of revenue to pricing after concessions; a vendor scope note assigns selected signed expense changes; implementation/capex invoices assign costs; a receivable aging note assigns USD 180,000 October collections timing with no earnings effect. None of these notes are company evidence or independent causal validation. Volume, mix, settlement timing and shifted work remain alternatives."
        evidence = dict(
            evidence_id=identity + "-support",
            classification="constructed_attribution_evidence",
            content=content,
            sha256=digest(content),
        )
        allocations = []
        for component, value in zip(COMPONENTS, claims, strict=True):
            if value == 0:
                continue
            initiative = (
                "collections-timing"
                if component == "working_capital_cash"
                else "pricing-renewals"
                if component == "revenue"
                else "service-automation"
            )
            allocations.append(
                dict(
                    row_id=component,
                    initiative_id=initiative,
                    amount=str(value),
                    evidence_ids=[evidence["evidence_id"]],
                    rationale="Authored claim assigns this signed source difference to the named initiative; costs are retained with their direction and residuals remain unassigned.",
                    confidence="limited",
                    alternative_explanation="Volume/mix, supplier timing, shifted work or ordinary collections may explain part or all of the difference.",
                )
            )
        months.append(
            dict(
                observed=book("observed", observed, ebitda),
                counterfactual=book("no_intervention_counterfactual", [1000000, -340000, 0, 660000, 0, 0], 660000),
                corrects_source_id=previous,
                evidence=[evidence],
                allocations=allocations,
                rationale="Correct November revenue posting by USD 2,000 and reconsider attribution."
                if previous
                else "Import authored month-end scoped accounting comparison and explicit simulated claims.",
            )
        )
    return RealizationExercise.model_validate(
        dict(
            classification="constructed_operating_exercise",
            underwriting_sha256=fingerprint(case),
            operating_plan_sha256=fingerprint(plan),
            months=months,
            current_forecast_capture="0.50",
            current_forecast_rationale="Separate authored ownership-review challenge lowers base-case pricing capture to 50%; retained costs and capacity schedule remain explicit. This is not an estimate learned from three constructed accounting observations.",
        )
    )


if __name__ == "__main__":
    base = Path("data/constructed/progress")
    result = example(
        UnderwritingCase.model_validate_json((base / "underwriting.json").read_bytes()),
        OperatingPlan.model_validate_json((base / "operating-plan.json").read_bytes()),
    )
    (base / "realization.json").write_text(
        json.dumps(result.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
