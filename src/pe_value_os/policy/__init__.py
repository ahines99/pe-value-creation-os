"""Versioned operating policy (PVC-055). Loaded once at startup; `version` is stamped on audit events."""

from __future__ import annotations

import os
import tomllib
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..domain.project_models import Lever, ScenarioInputs

DEFAULT_POLICY_PATH = Path(__file__).with_name("policy.toml")


class Freshness(BaseModel):
    max_age_days: int = Field(gt=0)


class Screening(BaseModel):
    cac_payback_months_max: Decimal
    grr_min: Decimal
    nrr_min: Decimal
    burn_multiple_max: Decimal
    magic_number_min: Decimal
    subscription_gross_margin_min: Decimal
    discount_sd_max: Decimal
    quarter_end_discount_gap_max: Decimal
    legacy_arr_share_max: Decimal
    renewal_uplift_realization_min: Decimal
    concession_leakage_max: Decimal
    segment_grr_gap_max: Decimal
    segment_min_arr_share: Decimal
    involuntary_churn_share_max: Decimal
    support_tier1_cost_share_min: Decimal


class SufficiencyRule(BaseModel):
    required: list[str]
    min_months: int = Field(gt=0)
    optional: list[str] = Field(default_factory=list)


class FlowThroughRule(BaseModel):
    type: Literal["constant", "metric"]
    value: Decimal | None = None
    metric: str | None = None


class Prioritization(BaseModel):
    weights: dict[str, Decimal]
    start_month: dict[Lever, int]
    ramp_months: dict[Lever, int]


class ScenarioDefaults(BaseModel):
    low: tuple[Decimal, Decimal]
    base: tuple[Decimal, Decimal]
    high: tuple[Decimal, Decimal]

    def scenarios(self) -> tuple[ScenarioInputs, ScenarioInputs, ScenarioInputs]:
        def mk(pair: tuple[Decimal, Decimal]) -> ScenarioInputs:
            return ScenarioInputs(improvement_rate=pair[0], realization_rate=pair[1])

        return mk(self.low), mk(self.base), mk(self.high)


class ProposalCost(BaseModel):
    one_time: Decimal
    annual_run: Decimal


class ApprovalPolicy(BaseModel):
    expiry_hours: int
    escalation_contact: str
    approver_role: str


class KpiPolicy(BaseModel):
    default_cadence_days: int
    off_track_tolerance: Decimal
    trend_decline_periods: int


class ModelPolicy(BaseModel):
    allowed_finding_types: list[str]
    on_unavailable: Literal["pause", "rules"]


class RunPolicy(BaseModel):
    min_sufficient_analyses: int = Field(ge=1)


class PolicyConfig(BaseModel):
    version: str
    rules: list[str]
    run: RunPolicy
    freshness: Freshness
    screening: Screening
    sufficiency: dict[str, SufficiencyRule]
    flow_through: dict[Lever, FlowThroughRule]
    prioritization: Prioritization
    proposal_defaults: dict[str, ScenarioDefaults]
    proposal_costs: dict[str, ProposalCost]
    approval: ApprovalPolicy
    kpi: KpiPolicy
    model: ModelPolicy

    def describe(self) -> str:
        lines = [f"Policy version {self.version}", "", "Rules:"]
        lines += [f"- {r}" for r in self.rules]
        lines += ["", f"Evidence freshness window: {self.freshness.max_age_days} days", "", "Screening thresholds:"]
        lines += [f"- {k}: {v}" for k, v in self.screening.model_dump().items()]
        return "\n".join(lines)


def load_policy_file(path: Path) -> PolicyConfig:
    with path.open("rb") as fh:
        return PolicyConfig.model_validate(tomllib.load(fh))


@lru_cache(maxsize=1)
def get_policy() -> PolicyConfig:
    return load_policy_file(Path(os.environ.get("PVC_POLICY_PATH", DEFAULT_POLICY_PATH)))
