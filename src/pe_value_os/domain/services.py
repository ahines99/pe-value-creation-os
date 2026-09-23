"""Deterministic value-case sizing (PVC-020). Results are annual run-rate EBITDA."""

from __future__ import annotations

import hashlib
from decimal import Decimal

from .project_models import Opportunity, ScenarioInputs, ValueCase

CALC_VERSION = "value-case/1"


def _scenario_ebitda(opp: Opportunity, s: ScenarioInputs) -> Decimal:
    gross = opp.baseline_value * s.effective_rate * opp.ebitda_flow_through
    return gross - opp.annual_run_cost


def inputs_hash(opp: Opportunity) -> str:
    return hashlib.sha256(opp.model_dump_json().encode()).hexdigest()


def size_value_case(opp: Opportunity, ev_multiple: Decimal | None = None) -> ValueCase:
    base = _scenario_ebitda(opp, opp.base)
    return ValueCase(
        opportunity_id=opp.opportunity_id,
        annual_ebitda_low=_scenario_ebitda(opp, opp.low),
        annual_ebitda_base=base,
        annual_ebitda_high=_scenario_ebitda(opp, opp.high),
        one_time_cost=opp.one_time_cost,
        ev_multiple=ev_multiple,
        ev_impact_base=base * ev_multiple if ev_multiple is not None else None,
        calc_version=CALC_VERSION,
        inputs_hash=inputs_hash(opp),
    )
