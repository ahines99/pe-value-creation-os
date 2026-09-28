"""Deterministic value-case sizing (PVC-020). Results are annual run-rate EBITDA."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from .project_models import Opportunity, ScenarioInputs, ValueCase

CALC_VERSION = "value-case/2"


def _scenario_ebitda(opp: Opportunity, s: ScenarioInputs) -> Decimal:
    gross = opp.baseline_value * s.effective_rate * opp.ebitda_flow_through
    return gross - opp.annual_run_cost


def inputs_hash(opp: Opportunity, ev_multiple: Decimal | None = None) -> str:
    """Fingerprint every supplied calculation input, including the optional valuation assumption.

    The opportunity itself is unchanged by valuation; stored v1 cases retain their
    original fingerprints and calculation version until explicitly recomputed.
    """
    if ev_multiple is not None and (not ev_multiple.is_finite() or ev_multiple <= 0):
        raise ValueError("EV multiple must be finite and positive")
    payload = {
        "opportunity": opp.model_dump(mode="json"),
        "ev_multiple": format(ev_multiple.normalize(), "f") if ev_multiple is not None else None,
        "calc_version": CALC_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def size_value_case(opp: Opportunity, ev_multiple: Decimal | None = None) -> ValueCase:
    fingerprint = inputs_hash(opp, ev_multiple)
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
        inputs_hash=fingerprint,
    )
