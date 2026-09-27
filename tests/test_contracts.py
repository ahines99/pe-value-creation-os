"""PVC-010/011: domain contracts."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pe_value_os.domain.models import AuditEvent, Confidence, EvidenceRef, Finding, FindingType
from pe_value_os.domain.project_models import Opportunity, OpportunityProposal, ScenarioInputs, ValueCase


def s(i: str, r: str) -> ScenarioInputs:
    return ScenarioInputs(improvement_rate=Decimal(i), realization_rate=Decimal(r))


def opp(**kw):
    base = dict(
        opportunity_id="o1",
        run_id="r1",
        company_id="c1",
        lever="pricing",
        title="t",
        baseline_metric="renewing_arr",
        baseline_value=Decimal("1000000"),
        ebitda_flow_through=Decimal("0.9"),
        low=s("0.01", "0.5"),
        base=s("0.03", "0.6"),
        high=s("0.05", "0.8"),
        confidence="medium",
        rationale="r",
        evidence_ids=["e1"],
    )
    base.update(kw)
    return Opportunity(**base)


@pytest.mark.parametrize(
    "field,value", [("improvement_rate", "1.01"), ("improvement_rate", "-0.01"), ("realization_rate", "1.5")]
)
def test_rates_bounded(field, value):
    kw = {"improvement_rate": "0.1", "realization_rate": "0.5", field: value}
    with pytest.raises(ValidationError):
        ScenarioInputs(**kw)


def test_scenario_order_enforced():
    with pytest.raises(ValidationError, match="low <= base <= high"):
        opp(low=s("0.2", "1"))


def test_evidence_required():
    with pytest.raises(ValidationError):
        opp(evidence_ids=[])


def test_proposal_rejects_server_owned_fields():
    with pytest.raises(ValidationError):
        OpportunityProposal(
            lever="pricing",
            baseline_metric="renewing_arr",
            title="t",
            low=s("0.01", "0.5"),
            base=s("0.02", "0.5"),
            high=s("0.03", "0.5"),
            confidence="low",
            rationale="r",
            evidence_ids=["e1"],
            baseline_value="999999999",
        )


def test_decimal_json_round_trip_preserves_precision():
    vc = ValueCase(
        opportunity_id="o",
        annual_ebitda_low=Decimal("0.1") + Decimal("0.2"),
        annual_ebitda_base=Decimal("12345678.901234"),
        annual_ebitda_high=Decimal("1e-7"),
        one_time_cost=Decimal(0),
        calc_version="v",
        inputs_hash="h",
    )
    back = ValueCase.model_validate_json(vc.model_dump_json())
    assert back == vc
    assert back.annual_ebitda_low == Decimal("0.3")


def test_core_models_validate():
    now = datetime.now(UTC)
    EvidenceRef(
        evidence_id="e",
        company_id="c",
        source_uri="file://x",
        source_type="csv",
        retrieved_at=now,
        content_hash="h",
    )
    f = Finding(
        finding_id="f",
        run_id="r",
        company_id="c",
        finding_type=FindingType.OBSERVATION,
        title="t",
        statement="s",
        confidence=Confidence.LOW,
    )
    assert f.evidence_ids == []
    AuditEvent(run_id=None, company_id="c", step="s", event_type="e", actor="a", created_at=now)
