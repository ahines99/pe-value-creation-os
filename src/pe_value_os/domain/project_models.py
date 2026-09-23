"""Value-creation contracts: opportunities, value cases, priorities, and plans.

Rates are fractions in [0, 1] (0.05 means 5%). Money is Decimal (ADR 0003).
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .models import Confidence


class Lever(StrEnum):
    PRICING = "pricing"
    RETENTION = "retention"
    SALES_EFFICIENCY = "sales_efficiency"
    GROSS_MARGIN = "gross_margin"
    AI_AUTOMATION = "ai_automation"


class ScenarioInputs(BaseModel):
    improvement_rate: Decimal = Field(ge=0, le=1, description="Fraction of baseline improved, 0.05 = 5%")
    realization_rate: Decimal = Field(ge=0, le=1, description="Fraction of the improvement actually captured")

    @property
    def effective_rate(self) -> Decimal:
        return self.improvement_rate * self.realization_rate


class OpportunityProposal(BaseModel):
    """What a proposer (rules or model) may supply. Baseline and flow-through are deliberately absent:
    the server derives them from company data (PVC-028)."""

    model_config = {"extra": "forbid"}

    lever: Lever
    baseline_metric: str
    title: str
    low: ScenarioInputs
    base: ScenarioInputs
    high: ScenarioInputs
    confidence: Confidence
    rationale: str
    evidence_ids: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    annual_run_cost: Decimal = Field(default=Decimal(0), ge=0)
    one_time_cost: Decimal = Field(default=Decimal(0), ge=0)
    metric_params: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def scenarios_ordered(self) -> OpportunityProposal:
        _check_order(self.low, self.base, self.high)
        return self


class Opportunity(BaseModel):
    opportunity_id: str
    run_id: str
    company_id: str
    lever: Lever
    title: str
    baseline_metric: str
    baseline_value: Decimal = Field(ge=0)
    ebitda_flow_through: Decimal = Field(gt=0, le=1)
    low: ScenarioInputs
    base: ScenarioInputs
    high: ScenarioInputs
    annual_run_cost: Decimal = Field(default=Decimal(0), ge=0)
    one_time_cost: Decimal = Field(default=Decimal(0), ge=0)
    confidence: Confidence
    rationale: str
    assumptions: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    metric_params: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def scenarios_ordered(self) -> Opportunity:
        _check_order(self.low, self.base, self.high)
        return self


def _check_order(low: ScenarioInputs, base: ScenarioInputs, high: ScenarioInputs) -> None:
    if not (low.effective_rate <= base.effective_rate <= high.effective_rate):
        raise ValueError("Scenario effective rates must satisfy low <= base <= high")


class ValueCase(BaseModel):
    opportunity_id: str
    annual_ebitda_low: Decimal
    annual_ebitda_base: Decimal
    annual_ebitda_high: Decimal
    one_time_cost: Decimal
    ev_multiple: Decimal | None = Field(default=None, gt=0)
    ev_impact_base: Decimal | None = None
    calc_version: str
    inputs_hash: str


class PriorityScore(BaseModel):
    opportunity_id: str
    rank: int
    score: Decimal
    components: dict[str, Decimal]
    run_rate_ebitda_base: Decimal
    in_year_ebitda_base: Decimal
    start_month: int


class InitiativeClass(StrEnum):
    QUICK_WIN = "quick_win"
    STRUCTURAL = "structural"
    ENABLER = "enabler"


class PlanKpi(BaseModel):
    kpi_id: str
    metric: str
    description: str
    baseline: Decimal
    day_100_target: Decimal
    run_rate_target: Decimal
    direction: str = Field(pattern="^(increase|decrease)$")
    cadence_days: int = Field(gt=0)
    source: str
    evidence_ids: list[str]
    monitorable: bool
    metric_params: dict[str, str] = Field(default_factory=dict)


class Initiative(BaseModel):
    opportunity_id: str
    title: str
    classification: InitiativeClass
    run_rate_ebitda_base: Decimal
    in_year_ebitda_base: Decimal
    requires_approval_reasons: list[str] = Field(default_factory=list)


class Workstream(BaseModel):
    workstream_id: str
    name: str
    lever: Lever
    owner_role: str
    initiatives: list[Initiative]
    milestones: dict[str, list[str]]
    kpis: list[PlanKpi]
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    plan_id: str
    run_id: str
    company_id: str
    workstreams: list[Workstream]
    total_run_rate_ebitda_base: Decimal
    total_in_year_ebitda_base: Decimal
    excluded_opportunities: list[dict[str, Any]] = Field(default_factory=list)
    decisions_requiring_approval: list[str] = Field(default_factory=list)
    governance: list[str] = Field(default_factory=list)
    narrative: str | None = None
