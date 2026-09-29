"""Worked population budgets, exclusivity, rounding and retained commitments."""

import json
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from pe_value_os.diligence.interactions import InteractionCase
from pe_value_os.diligence.underwriting import UnderwritingCase, evaluate, ledger

from .test_underwriting import simplified


def paired(kind="pricing", mode="partition", shares=("0.4", "0.3"), **assumptions):
    raw = simplified(**assumptions).model_dump(mode="json")
    original = next(d for d in raw["scenarios"][0]["drivers"] if d["kind"] == kind)
    parent, alternative = original["initiative_id"], original["initiative_id"] + "-alternative"
    for scenario in raw["scenarios"]:
        driver = next(d for d in scenario["drivers"] if d["kind"] == kind)
        scenario["drivers"].append({**driver, "initiative_id": alternative, "title": "Alternative intervention"})
    drivers = raw["scenarios"][0]["drivers"]
    basis = {
        "rationale": "Constructed population budget; no observed impact asserted.",
        "owner": "Authored finance reviewer",
        "invalidated_by": "Overlapping population or unsupported intervention",
        "evidence_ids": [next(e["evidence_id"] for e in raw["evidence"] if e["classification"] == "constructed")],
    }
    pools = []
    for pool in dict.fromkeys(d["benefit_pool"] for d in drivers):
        ids = [d["initiative_id"] for d in drivers if d["benefit_pool"] == pool]
        pool_mode = mode if len(ids) > 1 else "exclusive"
        pools.append(
            {
                **basis,
                "pool_id": pool,
                "mode": pool_mode,
                "initiative_ids": ids,
                "shares": [{"initiative_id": i, "share": s} for i, s in zip(ids, shares, strict=True)]
                if pool_mode == "partition"
                else [],
            }
        )
    raw.update(
        schema_version=2,
        interaction_policy={
            "classification": "constructed_allocation_policy",
            "selected_initiatives": [
                d["initiative_id"] for d in drivers if mode != "exclusive" or d["initiative_id"] != alternative
            ],
            "selection_rationale": "Authored choice for worked tests",
            "pools": pools,
            "cost_allocations": [],
        },
    )
    return raw, parent, alternative, basis


def base(case, selected=None, **kwargs):
    return next(s for s in evaluate(case, selected, **kwargs)["scenarios"] if s["scenario_id"] == "base")


def test_rates_apply_to_allocated_population_before_churn_and_costs():
    raw, parent, alternative, _ = paired()
    for scenario in raw["scenarios"]:
        original = next(a for a in scenario["assumptions"] if a["assumption_id"] == "uplift")
        scenario["assumptions"].append({**original, "assumption_id": "alternative-uplift", "value": ".20"})
        next(d for d in scenario["drivers"] if d["initiative_id"] == alternative)["uplift"] = "alternative-uplift"
    case = InteractionCase.model_validate(raw)
    report = evaluate(case)
    assert report["calculation_version"] == "monthly-underwriting/3"
    result = base(case)
    october = result["monthly"][0]
    # A: 1,240 exposure -> 117.8 gross - 62 lost revenue - 11.16 cost = 44.64.
    # B: 930 exposure -> 176.7 gross - 46.5 lost revenue - 26.04 cost = 104.16.
    assert october["gross_price_benefit"] == Decimal("294.50")
    assert october["revenue_leakage"] == Decimal("-108.50")
    assert october["variable_cost"] == Decimal("-37.20")
    assert october["incremental_ebitda"] == Decimal("148.80")
    assert october["pre_tax_cash_proxy"] == Decimal("-37.20")
    assert result["monthly"][1]["pre_tax_cash_proxy"] == Decimal("148.80")
    assert result["interaction"]["pools"][0]["unselected_or_unassigned_share"] == Decimal("0.3")
    assert result["interaction"]["financial_attribution"] is None
    selected = frozenset(report["selected_initiatives"]) - {alternative}
    reduced = base(case, selected)
    assert reduced["monthly"][0]["incremental_ebitda"] == Decimal("44.64")
    assert reduced["interaction"]["pools"][0]["unselected_or_unassigned_share"] == Decimal("0.6")
    blocked = base(case, benefit_blocks={"base": frozenset({alternative})})
    assert blocked["monthly"][0]["incremental_ebitda"] == Decimal("44.64")
    assert blocked["interaction"]["pools"][0]["blocked_members"] == [alternative]
    assert parent in report["selected_initiatives"]


def test_exclusive_choice_uses_one_population_and_changes_provenance():
    raw, parent, alternative, _ = paired(mode="exclusive")
    case = InteractionCase.model_validate(raw)
    original = evaluate(case)
    alternate = evaluate(case, frozenset(original["selected_initiatives"]) - {parent} | {alternative})
    assert original["input_sha256"] == alternate["input_sha256"]
    assert original["calculation_sha256"] != alternate["calculation_sha256"]
    assert base(case)["monthly"][0]["incremental_ebitda"] == Decimal("111.60")
    with pytest.raises(ValueError, match="mutually exclusive"):
        evaluate(case, frozenset({parent, alternative}))


def test_allocation_valuation_multiples_do_not_change_operating_or_cash_results():
    raw, _, _, _ = paired()
    before = evaluate(InteractionCase.model_validate(raw))
    raw["multiples"] = ["3", "7", "11"]
    after = evaluate(InteractionCase.model_validate(raw))
    for old, new in zip(before["scenarios"], after["scenarios"], strict=True):
        assert {k: v for k, v in old.items() if k != "valuation"} == {k: v for k, v in new.items() if k != "valuation"}
        assert new["valuation"][1]["incremental_ev_sensitivity"] == new["year_two"]["recurring_contribution"] * 7
    assert before["calculation_sha256"] != after["calculation_sha256"]


@pytest.mark.parametrize(
    "churn,uplift,component,expected",
    [("0", ".1", "gross_price_benefit", ".01"), (".1", "0", "revenue_leakage", "-.01")],
)
def test_population_rounds_once_and_retains_sign_and_settlement(churn, uplift, component, expected):
    raw, _, _, _ = paired(shares=(".5", ".5"), **{"eligible-revenue": ".10", "uplift": uplift, "churn": churn})
    for scenario in raw["scenarios"]:
        refs = {d["variable_cost_rate"] for d in scenario["drivers"] if d["kind"] == "pricing"}
        for assumption in scenario["assumptions"]:
            if assumption["assumption_id"] in refs:
                assumption["value"] = "0"
    case = InteractionCase.model_validate(raw)
    result = base(case)
    assert result["monthly"][0][component] == Decimal(expected)
    assert result["monthly"][1]["pre_tax_cash_proxy"] == Decimal(expected)
    assert result["cash_settlement_after_horizon"] == Decimal(expected)
    scenario = next(s for s in case.scenarios if s.scenario_id == "base")
    entries = ledger(case, scenario, frozenset(case.interaction_policy.selected_initiatives))
    assert all(e.amount >= 0 if Decimal(expected) > 0 else e.amount <= 0 for e in entries if e.component == component)
    for scenario in raw["scenarios"]:
        scenario["drivers"].reverse()
    assert base(InteractionCase.model_validate(raw))["monthly"] == result["monthly"]


def test_service_partition_caps_spend_and_cost_action_without_reallocation():
    raw, parent, alternative, _ = paired(
        "service",
        shares=(".6", ".4"),
        uplift="0",
        churn="0",
        contacts="20000",
        **{"cost-action": "50000", "addressable-spend": "12000"},
    )
    case = InteractionCase.model_validate(raw)
    result = base(case)
    assert result["monthly"][0]["cost_removed"] == 12000
    assert result["monthly"][0]["capacity_hours"] == 840
    selected = frozenset(case.interaction_policy.selected_initiatives) - {alternative}
    partial = base(case, selected)
    assert partial["monthly"][0]["cost_removed"] == 7200
    assert partial["monthly"][0]["capacity_hours"] == 504
    assert parent in selected


def test_collection_allocations_reverse_on_their_own_dates():
    raw, parent, alternative, _ = paired("collections", uplift="0", churn="0", receivables="1000", accelerated=".20")
    for scenario in raw["scenarios"]:
        a = next(d for d in scenario["drivers"] if d["initiative_id"] == parent)
        b = next(d for d in scenario["drivers"] if d["initiative_id"] == alternative)
        a.update(effective_on="2026-10-05", counterfactual_collection_on="2026-12-05")
        b.update(effective_on="2026-11-05", counterfactual_collection_on="2027-01-05")
    case = InteractionCase.model_validate(raw)
    result = base(case)
    assert [p["working_capital_cash"] for p in result["monthly"][:4]] == [80, 60, -80, -60]
    assert result["total"]["incremental_ebitda"] == result["total"]["pre_tax_cash_proxy"] == 0
    assert all(v["incremental_ev_sensitivity"] == 0 for v in result["valuation"])
    with pytest.raises(ValueError, match="reversals cannot be truncated"):
        ledger(
            case,
            case.scenarios[0],
            frozenset(case.interaction_policy.selected_initiatives),
            benefit_end_dates={parent: date(2026, 11, 1)},
        )


def test_cost_explanation_conserves_postings_and_keeps_excluded_commitments():
    raw, parent, alternative, basis = paired(setup="100", capex="50")
    for scenario in raw["scenarios"]:
        scenario["costs"] = [
            {
                "cost_id": "shared-setup",
                "initiative_ids": [parent, alternative],
                "kind": "implementation",
                "amount": "setup",
                "recognized_on": "2026-10-10",
                "paid_on": "2026-11-10",
                "retained_if_excluded": True,
            },
            {
                "cost_id": "optional-capex",
                "initiative_ids": [alternative],
                "kind": "capex",
                "amount": "capex",
                "recognized_on": "2026-10-10",
                "paid_on": "2026-10-10",
                "retained_if_excluded": False,
            },
        ]
    raw["interaction_policy"]["cost_allocations"] = [
        {
            **basis,
            "cost_id": "shared-setup",
            "shares": [{"initiative_id": parent, "share": ".25"}, {"initiative_id": alternative, "share": ".5"}],
        }
    ]
    case = InteractionCase.model_validate(raw)
    full = base(case)
    assert full["total"]["implementation_expense"] == -100
    assert full["total"]["capex_cash"] == -50
    excluded = base(case, frozenset())
    assert excluded["total"]["incremental_ebitda"] == excluded["total"]["pre_tax_cash_proxy"] == -100
    assert excluded["total"]["capex_cash"] == 0
    explained = excluded["interaction"]["cost_allocation_entries"]
    assert len(explained) == 6
    for component in ("implementation_expense", "operating_cash"):
        values = {r["initiative_id"]: Decimal(r["amount"]) for r in explained if r["component"] == component}
        assert values == {parent: Decimal(-25), alternative: Decimal(-50), "shared": Decimal(-25)}
    changed = deepcopy(raw)
    changed["interaction_policy"]["cost_allocations"][0]["shares"] = [{"initiative_id": parent, "share": "1"}]
    assert base(InteractionCase.model_validate(changed))["monthly"] == full["monthly"]
    assert (
        evaluate(case)["calculation_sha256"] != evaluate(InteractionCase.model_validate(changed))["calculation_sha256"]
    )


@pytest.mark.parametrize(
    "change,pattern",
    [
        ("overbudget", "cannot exceed"),
        ("missing_share", "exactly once"),
        ("missing_pool", "every economic pool"),
        ("population", "same complete population"),
        ("private", "rejects private"),
        ("unknown_selection", "unknown initiative"),
        ("exclusive_shares", "do not have additive"),
        ("unknown_evidence", "registered constructed"),
    ],
)
def test_ambiguous_or_unsupported_pool_rules_fail(change, pattern):
    raw, _, alternative, _ = paired()
    rule = raw["interaction_policy"]["pools"][0]
    if change == "overbudget":
        rule["shares"][0]["share"] = ".9"
    elif change == "missing_share":
        rule["shares"].pop()
    elif change == "missing_pool":
        raw["interaction_policy"]["pools"].pop()
    elif change == "population":
        for scenario in raw["scenarios"]:
            a = next(a for a in scenario["assumptions"] if a["assumption_id"] == "eligible-revenue")
            scenario["assumptions"].append({**a, "assumption_id": "different-population", "value": "10"})
            next(d for d in scenario["drivers"] if d["initiative_id"] == alternative)["monthly_eligible_revenue"] = (
                "different-population"
            )
    elif change == "private":
        raw["evidence"].append(
            {"evidence_id": "private", "classification": "licensed_private", "locator": "private source"}
        )
    elif change == "unknown_selection":
        raw["interaction_policy"]["selected_initiatives"].append("outsider")
    elif change == "exclusive_shares":
        rule["mode"] = "exclusive"
    else:
        rule["evidence_ids"] = ["absent"]
    with pytest.raises(ValueError, match=pattern):
        evaluate(InteractionCase.model_validate(raw))


def test_legacy_snapshot_and_pool_rejection_remain_unchanged():
    case = UnderwritingCase.model_validate_json(Path("data/constructed/progress/underwriting.json").read_bytes())
    assert json.loads(json.dumps(evaluate(case), default=str)) == json.loads(
        Path("docs/portfolio/underwriting.json").read_bytes()
    )
    raw, _, _, _ = paired()
    raw.pop("interaction_policy")
    raw["schema_version"] = 1
    with pytest.raises(ValueError, match="overlapping benefit pools"):
        UnderwritingCase.model_validate(raw)
