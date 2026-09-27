"""Workflow run state and persisted records shared by the workflow engine and repositories."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Status(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    NEEDS_EVIDENCE = "needs_evidence"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETE = "complete"
    REJECTED = "rejected"
    FAILED = "failed"


PAUSED = frozenset({Status.NEEDS_EVIDENCE, Status.AWAITING_APPROVAL})
TERMINAL = frozenset({Status.COMPLETE, Status.REJECTED})


@dataclass
class RunState:
    run_id: str
    company_id: str
    status: Status = Status.PENDING
    current_step: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    pause_reason: dict[str, Any] | None = None
    reference_date: date | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["reference_date"] = self.reference_date.isoformat() if self.reference_date else None
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> RunState:
        d = dict(d)
        d["status"] = Status(d["status"])
        if d.get("reference_date"):
            d["reference_date"] = date.fromisoformat(d["reference_date"])
        return cls(**d)


class RunRecord(BaseModel):
    run_id: str
    company_id: str
    project_type: str
    status: Status
    current_step: str | None
    completed_steps: list[str]
    state: dict[str, Any]
    idempotency_key: str | None
    requested_by: str
    reference_date: date | None
    params: dict[str, Any] = Field(default_factory=dict)
    resume_requested_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    def run_state(self) -> RunState:
        if self.state:
            return RunState.from_json(self.state)
        return RunState(
            run_id=self.run_id,
            company_id=self.company_id,
            status=self.status,
            reference_date=self.reference_date,
            params=self.params,
        )


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class ApprovalRecord(BaseModel):
    approval_id: str
    run_id: str
    company_id: str
    artifact_type: str
    artifact_id: str
    decision: ApprovalDecision | None = None
    decided_by: str | None = None
    rationale: str | None = None
    edits: dict[str, Any] = Field(default_factory=dict)
    diff: dict[str, Any] = Field(default_factory=dict)
    requested_at: datetime
    decided_at: datetime | None = None
    escalated_at: datetime | None = None


class PlanRecord(BaseModel):
    plan_id: str
    run_id: str
    company_id: str
    status: str  # proposed | approved | rejected | superseded
    plan: dict[str, Any]
    approved_plan: dict[str, Any] | None = None
    created_at: datetime
    approved_at: datetime | None = None
