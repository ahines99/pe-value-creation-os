"""PVC-020: value-case sizing golden tests. Every expected value is computed by hand in the comment."""

from decimal import Decimal

import pytest

from pe_value_os.domain.project_models import Opportunity, ScenarioInputs
from pe_value_os.domain.services import CALC_VERSION, size_value_case


def s(i, r):
    return ScenarioInputs(improvement_rate=Decimal(i), realization_rate=Decimal(r))


def opp(baseline="1000000", ft="1", low=("0.01", "0.5"), base=("0.02", "0.5"), high=("0.03", "0.5"), run="0", one="0"):
    return Opportunity(
        opportunity_id="o",
        run_id="r",
        company_id="c",
        lever="pricing",
        title="t",
        baseline_metric="renewing_arr",
        baseline_value=Decimal(baseline),
        ebitda_flow_through=Decimal(ft),
        low=s(*low),
        base=s(*base),
        high=s(*high),
        annual_run_cost=Decimal(run),
        one_time_cost=Decimal(one),
        confidence="medium",
        rationale="r",
        evidence_ids=["e"],
    )


GOLDEN = [
    # (opportunity kwargs, ev_multiple, (low, base, high), ev_impact_base)
    # 1: 1,000,000 x 0.02 x 0.5 x 1 = 10,000 base; low 5,000; high 15,000
    (dict(), None, ("5000", "10000", "15000"), None),
    # 2: flow-through 0.9: base 1,000,000 x 0.01 x 0.9 = 9,000
    (dict(ft="0.9"), None, ("4500", "9000", "13500"), None),
    # 3: run cost 12,000 subtracted from every scenario
    (dict(run="12000"), None, ("-7000", "-2000", "3000"), None),
    # 4: zero realization everywhere -> only the run cost remains
    (dict(low=("0.1", "0"), base=("0.1", "0"), high=("0.1", "0")), None, ("0", "0", "0"), None),
    # 5: zero realization with run cost -> negative EBITDA equal to run cost
    (dict(low=("0.1", "0"), base=("0.1", "0"), high=("0.1", "0"), run="500"), None, ("-500", "-500", "-500"), None),
    # 6: EV multiple 12 on base 10,000 -> 120,000
    (dict(), Decimal("12"), ("5000", "10000", "15000"), "120000"),
    # 7: zero baseline -> zero value regardless of rates
    (dict(baseline="0"), Decimal("10"), ("0", "0", "0"), "0"),
    # 8: full improvement and realization: 250,000 x 1 x 1 x 0.95 = 237,500 (all scenarios)
    (
        dict(baseline="250000", ft="0.95", low=("1", "1"), base=("1", "1"), high=("1", "1")),
        None,
        ("237500", "237500", "237500"),
        None,
    ),
    # 9: fractional cents: 333.33 x 0.03 x 0.7 = 6.99993 base (no rounding in the service)
    (
        dict(baseline="333.33", low=("0.03", "0.5"), base=("0.03", "0.7"), high=("0.03", "0.9")),
        None,
        ("4.99995", "6.99993", "8.99991"),
        None,
    ),
    # 10: retention-style: 1,005,001.70 x (0.2 x 0.6) x 0.7941 - 180,000 = 95,768.6219964 - 180,000
    (
        dict(
            baseline="1005001.70",
            ft="0.7941",
            low=("0.1", "0.5"),
            base=("0.2", "0.6"),
            high=("0.3", "0.7"),
            run="180000",
        ),
        Decimal("8"),
        ("-140096.40750150", "-84231.37800360", "-12404.91150630"),
        "-673851.02402880",
    ),
    # 11: run cost exceeds benefit in every scenario but EV still reported
    (dict(run="1000000"), Decimal("5"), ("-995000", "-990000", "-985000"), "-4950000"),
]


@pytest.mark.parametrize("kw,ev,expected,ev_base", GOLDEN)
def test_golden_cases(kw, ev, expected, ev_base):
    vc = size_value_case(opp(**kw), ev)
    assert (vc.annual_ebitda_low, vc.annual_ebitda_base, vc.annual_ebitda_high) == tuple(Decimal(x) for x in expected)
    assert vc.ev_impact_base == (Decimal(ev_base) if ev_base is not None else None)
    assert vc.calc_version == CALC_VERSION


def test_inputs_hash_stable_and_sensitive():
    a, b = size_value_case(opp()), size_value_case(opp())
    assert a.inputs_hash == b.inputs_hash and len(a.inputs_hash) == 64
    assert size_value_case(opp(baseline="1000001")).inputs_hash != a.inputs_hash


def test_one_time_cost_reported_not_subtracted():
    vc = size_value_case(opp(one="75000"))
    assert vc.one_time_cost == Decimal("75000") and vc.annual_ebitda_base == Decimal("10000")
