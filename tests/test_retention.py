"""PVC-022: retention analysis recovers the planted churn pattern."""

import json
from decimal import Decimal
from pathlib import Path

from pe_value_os.adapters.fixtures import FixtureAdapter
from pe_value_os.domain.retention import analyse_retention

FIXTURES = Path(__file__).parent / "fixtures" / "companies"


def truth(cid):
    return json.loads((FIXTURES / cid / "planted.json").read_text())


def test_churn_company_worst_segment_is_planted_segment():
    ra = analyse_retention(FixtureAdapter().load("cedar-churn"))
    assert ra.worst_segment().value == truth("cedar-churn")["planted"]["worst_segment"]


def test_involuntary_share_matches_ground_truth_exactly():
    for cid in ("acme-healthy", "cedar-churn"):
        ra = analyse_retention(FixtureAdapter().load(cid))
        expected = Decimal(truth(cid)["ground_truth"]["t12m_involuntary_payment_share"])
        assert (ra.involuntary_payment_share or Decimal(0)) == expected
    cedar = analyse_retention(FixtureAdapter().load("cedar-churn"))
    assert cedar.involuntary_payment_share >= Decimal(
        str(truth("cedar-churn")["planted"]["involuntary_payment_share_min"])
    )


def test_churned_arr_by_type_matches_ground_truth():
    ra = analyse_retention(FixtureAdapter().load("cedar-churn"))
    gt = truth("cedar-churn")["ground_truth"]["t12m_churned_arr_by_type"]
    assert {k: str(v) for k, v in ra.churned_arr_by_type.items()} == gt


def test_front_loaded_churn_detected_only_where_planted():
    a = FixtureAdapter()
    cedar = analyse_retention(a.load("cedar-churn")).early_life_churn_overrepresentation
    healthy = analyse_retention(a.load("acme-healthy")).early_life_churn_overrepresentation
    assert cedar > 1 > healthy


def test_leading_indicators_present_for_churn_company():
    ra = analyse_retention(FixtureAdapter().load("cedar-churn"))
    signals = {li.name: li.signal for li in ra.leading_indicators}
    assert signals == {"core_seat_utilisation": True, "support_tickets_per_customer_month": True}
    assert all(li.evidence_ids for li in ra.leading_indicators)


def test_grr_bounded_and_not_above_nrr():
    a = FixtureAdapter()
    for cid in a.list_companies():
        ra = analyse_retention(a.load(cid))
        assert ra.grr <= 1 and ra.grr <= ra.nrr
        for seg in ra.segments:
            if seg.grr is not None:
                assert seg.grr <= 1 and seg.grr <= seg.nrr


def test_cohort_curves_have_bounded_logo_retention():
    ra = analyse_retention(FixtureAdapter().load("acme-healthy"))
    assert ra.cohorts
    for c in ra.cohorts:
        for v in c.logo_retention.values():
            assert v is None or Decimal(0) <= v <= 1
