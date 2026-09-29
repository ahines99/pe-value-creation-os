"""Author a separate allocation exercise; no company segmentation or results are implied."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from pe_value_os.diligence.allocation_demo import bind_sources
from pe_value_os.diligence.interactions import InteractionCase
from pe_value_os.diligence.memo import DecisionBrief
from pe_value_os.diligence.operating_sources import OperatingSourceBook
from pe_value_os.diligence.realization_render import RealizationExercise
from pe_value_os.diligence.scheduling import OperatingPlan, fingerprint
from pe_value_os.diligence.underwriting import UnderwritingCase

ROOT = Path(__file__).resolve().parents[1] / "data/constructed/progress"
PRIMARY = "pricing-renewals"
ALTERNATIVE = "pricing-targeted"


def examples():
    raw = UnderwritingCase.model_validate_json((ROOT / "underwriting.json").read_bytes()).model_dump(mode="json")
    raw.update(schema_version=2, case_id="progress-constructed-allocation-v1")
    for scenario in raw["scenarios"]:
        driver = deepcopy(next(d for d in scenario["drivers"] if d["initiative_id"] == PRIMARY))
        driver.update(
            initiative_id=ALTERNATIVE, title="Test a higher renewal uplift on an explicitly allocated population"
        )
        uplift = deepcopy(next(a for a in scenario["assumptions"] if a["assumption_id"] == driver["uplift"]))
        uplift.update(
            assumption_id="targeted-uplift",
            value=str(Decimal(uplift["value"]) * 2),
            rationale="Authored higher-uplift alternative; contractual caps, retention and feasibility still constrain the case.",
        )
        driver["uplift"] = uplift["assumption_id"]
        scenario["assumptions"].append(uplift)
        scenario["drivers"].append(driver)
        for cost in scenario["costs"]:
            if PRIMARY in cost["initiative_ids"]:
                cost["initiative_ids"].append(ALTERNATIVE)
    drivers = raw["scenarios"][0]["drivers"]
    basis = {
        "rationale": "Authored population budget; customer identity and a company-approved split are unavailable.",
        "owner": "Proposed finance and commercial reviewers",
        "invalidated_by": "Overlapping customer populations, unsupported rights or an unapproved intervention design.",
        "evidence_ids": [next(e["evidence_id"] for e in raw["evidence"] if e["classification"] == "constructed")],
    }
    pools = []
    for pool in dict.fromkeys(d["benefit_pool"] for d in drivers):
        ids = [d["initiative_id"] for d in drivers if d["benefit_pool"] == pool]
        pools.append(
            {
                **basis,
                "pool_id": pool,
                "mode": "partition" if len(ids) == 2 else "exclusive",
                "initiative_ids": ids,
                "shares": [{"initiative_id": PRIMARY, "share": ".6"}, {"initiative_id": ALTERNATIVE, "share": ".4"}]
                if len(ids) == 2
                else [],
            }
        )
    shared = next(
        c for c in raw["scenarios"][0]["costs"] if len(c["initiative_ids"]) == 4 and c["retained_if_excluded"]
    )
    raw["interaction_policy"] = {
        "classification": "constructed_allocation_policy",
        "selected_initiatives": [d["initiative_id"] for d in drivers if d["initiative_id"] != ALTERNATIVE],
        "selection_rationale": "Retain the original resource budgets: model the first pricing policy on its fixed 60% share and defer the 40% alternative because both work packages do not fit. The deferred share is not reassigned. Service and collections remain separate economic mechanisms.",
        "pools": pools,
        "cost_allocations": [
            {
                **basis,
                "cost_id": shared["cost_id"],
                "rationale": "Equal explanatory cost shares across four candidates. The full committed posting survives exclusion; no causal attribution.",
                "shares": [{"initiative_id": i, "share": ".25"} for i in shared["initiative_ids"]],
            }
        ],
    }
    case = InteractionCase.model_validate(raw)
    raw_plan = OperatingPlan.model_validate_json((ROOT / "operating-plan.json").read_bytes()).model_dump(mode="json")
    raw_plan.update(
        underwriting_sha256=fingerprint(case),
        case_id=case.case_id,
        plan_id="allocation-first-wave",
        revision_id="allocation-partition-proposal",
        sequencing_rationale="Authored allocation stress test using the original resource budgets; extra pricing work must compete for real modeled hours.",
    )
    tasks = [t for t in raw_plan["tasks"] if t["initiative_id"] == PRIMARY]
    names = {t["task_id"] for t in tasks}
    for task in tasks:
        clone = deepcopy(task)
        clone.update(
            task_id=task["task_id"] + "-targeted",
            title="Alternative: " + task["title"],
            initiative_id=ALTERNATIVE,
            workstream_id="targeted-pricing",
        )
        clone["prerequisites"] = [p + "-targeted" if p in names else p for p in task["prerequisites"]]
        raw_plan["tasks"].append(clone)
        raw_plan["priority_order"].append(clone["task_id"])
    gate = next(g for g in raw_plan["benefit_gates"] if g["initiative_id"] == PRIMARY)
    raw_plan["benefit_gates"].append({"initiative_id": ALTERNATIVE, "task_id": gate["task_id"] + "-targeted"})
    plan = OperatingPlan.model_validate(raw_plan)
    book = bind_sources(
        OperatingSourceBook.model_validate_json((ROOT / "operating-sources.json").read_bytes()), case, plan
    )
    exercise_raw = RealizationExercise.model_validate_json((ROOT / "realization.json").read_bytes()).model_dump(
        mode="json"
    )
    exercise_raw.update(underwriting_sha256=fingerprint(case), operating_plan_sha256=fingerprint(plan))
    for month in exercise_raw["months"]:
        for key in ("observed", "counterfactual"):
            record = month[key]
            record.update(
                case_id=case.case_id,
                source_id="allocation-" + record["source_id"],
                locator="data/constructed/progress/allocation-realization.json#" + record["source_id"],
                scope_explanation="Separately authored allocation exercise: one renewal pool shared across two candidates, plus service and collections. Accounting amounts and claims illustrate the method; population shares do not distribute claims to either candidate.",
            )
        if month["corrects_source_id"]:
            month["corrects_source_id"] = "allocation-" + month["corrects_source_id"]
    exercise = RealizationExercise.model_validate(exercise_raw)
    brief_raw = DecisionBrief.model_validate_json((ROOT / "decision-brief.json").read_bytes()).model_dump(mode="json")
    brief_raw.update(underwriting_sha256=fingerprint(case), plan_sha256=fingerprint(plan))
    for option in brief_raw["options"]:
        option["priority_order"].extend(t["task_id"] for t in raw_plan["tasks"] if t["initiative_id"] == ALTERNATIVE)
    brief = DecisionBrief.model_validate(brief_raw)
    return {
        "allocation-underwriting": case,
        "allocation-plan": plan,
        "allocation-sources": book,
        "allocation-realization": exercise,
        "allocation-brief": brief,
    }


if __name__ == "__main__":
    for name, model in examples().items():
        destination = ROOT / (name + ".json")
        destination.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {destination.name}")
