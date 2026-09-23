"""Core contracts shared by every layer. Field names mirror the PostgreSQL schema."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FindingType(StrEnum):
    VALUE_CLAIM = "value_claim"
    OPPORTUNITY = "opportunity"
    OBSERVATION = "observation"
    HYPOTHESIS = "hypothesis"
    DATA_GAP = "data_gap"
    SUSPICIOUS_CONTENT = "suspicious_content"


class EvidenceRelation(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT = "context"


class EvidenceRef(BaseModel):
    evidence_id: str
    company_id: str
    source_uri: str
    source_type: str
    retrieved_at: datetime
    as_of: datetime | None = None
    content_hash: str
    run_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    finding_id: str
    run_id: str
    company_id: str
    finding_type: FindingType
    title: str
    statement: str
    confidence: Confidence
    evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEvent(BaseModel):
    run_id: str | None
    company_id: str
    step: str
    event_type: str
    actor: str
    created_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
