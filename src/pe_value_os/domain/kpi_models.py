"""KPI monitoring records (PVC-120..124)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class KpiDefinition(BaseModel):
    kpi_id: str
    company_id: str
    plan_id: str
    run_id: str
    metric: str
    metric_params: dict[str, str] = Field(default_factory=dict)
    description: str
    baseline: Decimal
    day_100_target: Decimal
    run_rate_target: Decimal
    direction: str = Field(pattern="^(increase|decrease)$")
    cadence_days: int = Field(gt=0)
    source: str
    evidence_ids: list[str] = Field(default_factory=list)
    start_date: date
    active: bool = True
    created_at: datetime


class KpiObservation(BaseModel):
    observation_id: str
    kpi_id: str
    company_id: str
    observed_at: datetime
    period_end: date | None
    value: Decimal
    target: Decimal
    status: str = Field(pattern="^(on_track|off_track)$")
    variance: Decimal
    evidence_ids: list[str] = Field(default_factory=list)


class KpiAlert(BaseModel):
    alert_id: str
    kpi_id: str
    company_id: str
    observation_id: str
    rule: str = Field(pattern="^(threshold|trend)$")
    detail: str
    created_at: datetime


class Notification(BaseModel):
    notification_id: str
    company_id: str
    channel: str
    subject: str
    body: str
    created_at: datetime
    delivered_at: datetime | None = None
    status: str = "pending"
