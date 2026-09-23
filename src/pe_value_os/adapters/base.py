"""Source adapter contract (PVC-110). Adapters are read-only and register everything they read as evidence."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol

from ..domain.dataset import CompanyData

EVIDENCE_NAMESPACE = uuid.UUID("6f1d7c2e-8a53-4b8e-9f0a-3c5d2b1e4a77")


class SourceError(Exception):
    """A source could not be read. Not retried."""


class TransientSourceError(SourceError):
    """A source failed in a way that may succeed on retry (timeouts, 5xx, rate limits)."""


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    company_id: str
    source_uri: str
    source_type: str
    as_of: datetime | None
    content_hash: str
    content: bytes = field(repr=False)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def evidence_id_for(company_id: str, digest: str) -> str:
    """Deterministic evidence id: the same bytes for the same company always get the same id."""
    return str(uuid.uuid5(EVIDENCE_NAMESPACE, f"{company_id}:{digest}"))


def make_evidence(
    company_id: str,
    source_uri: str,
    source_type: str,
    content: bytes,
    as_of: datetime | None,
    metadata: dict[str, Any] | None = None,
) -> EvidenceRecord:
    digest = content_hash(content)
    return EvidenceRecord(
        evidence_id=evidence_id_for(company_id, digest),
        company_id=company_id,
        source_uri=source_uri,
        source_type=source_type,
        as_of=as_of,
        content_hash=digest,
        content=content,
        metadata=metadata or {},
    )


class EvidenceSink(Protocol):
    def add_evidence(self, record: EvidenceRecord) -> str: ...


class SourceAdapter(Protocol):
    """Loads one company's data. Implementations must be deterministic for identical source content."""

    name: str

    def list_companies(self) -> list[str]: ...

    def load(self, company_id: str, sink: EvidenceSink | None = None) -> CompanyData: ...

    def reference_date(self, company_id: str) -> date: ...
