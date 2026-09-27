"""PVC-024/025/026/028: sufficiency, prioritization, policy and scope, baseline derivation."""

from decimal import Decimal

import pytest

from pe_value_os import security
from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.domain import baselines, sufficiency
from pe_value_os.domain.models import Confidence, Finding, FindingType
from pe_value_os.domain.policies import PolicyViolation, check_action, require_citations
from pe_value_os.domain.prioritization import in_year_factor, phase, prioritize
from pe_value_os.domain.project_models import Lever, Opportunity, ScenarioInputs, ValueCase
from pe_value_os.policy import get_policy

POLICY = get_policy()


# --- PVC-024 sufficiency -----------------------------------------------------------------------------------
def test_clean_companies_sufficient():
    for cid in ("acme-healthy", "beacon-pricing", "cedar-churn"):
        res = sufficiency.check_all(FixtureAdapter().load(cid), POLICY)
        assert all(r.sufficient for r in res.values()), {k: v.gaps for k, v in res.items()}


def test_broken_company_gaps():
    res = sufficiency.check_all(FixtureAdapter().load("delta-broken"), POLICY)
    codes = {(a, g.code, g.dataset) for a, r in res.items() for g in r.gaps}
    assert ("pricing", "missing_dataset", "contracts") in codes
    assert ("pricing", "stale_dataset", "invoices") in codes
    assert ("unit_economics", "month_gaps", "pnl") in codes
    assert ("retention", "duplicate_entities", "customers") in codes
    assert ("retention", "row_errors", "arr") in codes
    assert {a: r.sufficient for a, r in res.items()} == {
        "unit_economics": False,
        "pricing": False,
        "retention": True,
        "ai_opportunity": False,
    }
    stale = next(g for g in res["pricing"].gaps if g.code == "stale_dataset")
    assert "45" in stale.detail  # policy freshness window is named in the gap


def test_unknown_analysis_rejected():
    with pytest.raises(ValueError, match="Unknown analysis"):
        sufficiency.check(FixtureAdapter().load("acme-healthy"), "vibes", POLICY)


# --- PVC-025 prioritization --------------------------------------------------------------------------------
def s(i, r):
    return ScenarioInputs(improvement_rate=Decimal(i), realization_rate=Decimal(r))


def item(oid, lever="pricing", base="100", cost="0", conf="medium"):
    o = Opportunity(
        opportunity_id=oid,
        run_id="r",
        company_id="c",
        lever=lever,
        title=oid,
        baseline_metric="renewing_arr",
        baseline_value=Decimal(1),
        ebitda_flow_through=Decimal(1),
        low=s("0", "0"),
        base=s("0", "0"),
        high=s("0", "0"),
        one_time_cost=Decimal(cost),
        confidence=conf,
        rationale="r",
        evidence_ids=["e"],
    )
    vc = ValueCase(
        opportunity_id=oid,
        annual_ebitda_low=Decimal(0),
        annual_ebitda_base=Decimal(base),
        annual_ebitda_high=Decimal(base),
        one_time_cost=Decimal(cost),
        calc_version="v",
        inputs_hash="h",
    )
    return o, vc


def test_in_year_factor_hand_computed():
    # start month 3, ramp 6: months 1..10 active; captured = 1/6+2/6+...+6/6 + 4*1 = 3.5 + 4 = 7.5 -> 7.5/12
    assert in_year_factor(3, 6) == Decimal("7.5") / 12
    assert in_year_factor(1, 1) == 1
    assert in_year_factor(12, 1) == Decimal(1) / 12


def test_ties_break_on_id_and_ranking_is_deterministic():
    items = [item("b"), item("a"), item("c")]
    ranks = [p.opportunity_id for p in prioritize(items, POLICY)]
    assert ranks == ["a", "b", "c"]
    assert [p.rank for p in prioritize(items, POLICY)] == [1, 2, 3]


def test_weights_change_ranking_predictably():
    big_late = item("big", lever="ai_automation", base="1000", cost="100000", conf="low")
    # default: big = 0.5*1 + 0.2*0.3333 + 0.2*(7/12) - 0.1*1 = 0.5833; small = 0.5*0.6 + 0.2*1 + 0.2*(10/12) = 0.6667
    small_fast = item("small", lever="pricing", base="600", cost="0", conf="high")
    default = [p.opportunity_id for p in prioritize([big_late, small_fast], POLICY)]
    ebitda_only = POLICY.model_copy(deep=True)
    ebitda_only.prioritization.weights = {
        "ebitda": Decimal(1),
        "confidence": Decimal(0),
        "time_to_value": Decimal(0),
        "one_time_cost": Decimal(0),
    }
    assert [p.opportunity_id for p in prioritize([big_late, small_fast], ebitda_only)] == ["big", "small"]
    assert default == ["small", "big"]


def test_in_year_never_exceeds_run_rate_in_magnitude():
    for lever in Lever:
        for rr in (Decimal("123456.78"), Decimal("-5000"), Decimal(0)):
            iy, _ = phase(rr, lever, POLICY)
            assert abs(iy) <= abs(rr)


# --- PVC-026 policy and scope ------------------------------------------------------------------------------
def test_uncited_value_claim_rejected():
    f = Finding(
        finding_id="f",
        run_id="r",
        company_id="c",
        finding_type=FindingType.VALUE_CLAIM,
        title="t",
        statement="s",
        confidence=Confidence.HIGH,
    )
    with pytest.raises(PolicyViolation):
        require_citations(f)
    require_citations(f.model_copy(update={"evidence_ids": ["e1"]}))
    require_citations(f.model_copy(update={"finding_type": FindingType.OBSERVATION}))


def test_check_action():
    assert not check_action("raise prices", "high", has_approval=False).allowed
    assert check_action("raise prices", "high", has_approval=True).allowed
    assert check_action("read report", "low", has_approval=False).allowed


def test_scope_enforced(monkeypatch):
    monkeypatch.setenv("PVC_ENV", "prod")
    monkeypatch.delenv("PVC_ALLOWED_COMPANIES", raising=False)
    with pytest.raises(security.ScopeError, match="No authenticated principal"):
        security.require("acme-healthy")
    with security.principal_scope(security.system_principal("acme-healthy")):
        security.require("acme-healthy")
        with pytest.raises(security.ScopeError, match="may not access"):
            security.require("beacon-pricing")


def test_dev_env_allow_list(monkeypatch):
    monkeypatch.setenv("PVC_ENV", "dev")
    monkeypatch.setenv("PVC_ALLOWED_COMPANIES", "a, b")
    assert security.require("a").subject == "dev"
    with pytest.raises(security.ScopeError):
        security.require("c")


# --- PVC-028 baselines ---------------------------------------------------------------------------------------
def test_unknown_metric_lists_valid_names():
    with pytest.raises(baselines.MetricUnavailable, match=r"valid: .*renewing_arr"):
        baselines.compute_metric(FixtureAdapter().load("acme-healthy"), "made_up_metric")


def test_lever_metric_mismatch_rejected():
    with pytest.raises(baselines.MetricUnavailable, match="not a valid baseline for lever 'pricing'"):
        baselines.derive_baseline(FixtureAdapter().load("acme-healthy"), Lever.PRICING, "s_and_m_expense", {}, POLICY)


def test_derived_baseline_carries_evidence_and_flow_through():
    data = FixtureAdapter().load("cedar-churn")
    d = baselines.derive_baseline(data, Lever.RETENTION, "addressable_churned_arr", {"segment": "smb"}, POLICY)
    gm = baselines.compute_metric(data, "subscription_gross_margin").value
    assert d.ebitda_flow_through == gm
    assert set(d.baseline.evidence_ids) <= set(d.evidence_ids)
    assert data.evidence(baselines.DatasetKind.PNL)[0] in d.evidence_ids  # gross-margin evidence included
    p = baselines.derive_baseline(data, Lever.PRICING, "legacy_price_book_arr", None, POLICY)
    assert p.ebitda_flow_through == Decimal("0.95")


def test_unavailable_when_data_missing():
    data = FixtureAdapter().load("delta-broken")
    with pytest.raises(baselines.MetricUnavailable, match="Contract terms"):
        baselines.compute_metric(data, "renewing_arr")


def test_unexpected_params_rejected():
    with pytest.raises(baselines.MetricUnavailable, match="does not accept params"):
        baselines.compute_metric(FixtureAdapter().load("acme-healthy"), "s_and_m_expense", {"segment": "smb"})
