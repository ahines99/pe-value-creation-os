"""In-memory view of one company's source data, as loaded by an adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .source_models import CompanyProfile, Dataset, DatasetKind, RowError


@dataclass
class CompanyData:
    profile: CompanyProfile
    profile_evidence_id: str
    reference_date: date
    datasets: dict[DatasetKind, Dataset] = field(default_factory=dict)

    @property
    def company_id(self) -> str:
        return self.profile.company_id

    def has(self, kind: DatasetKind) -> bool:
        return kind in self.datasets and bool(self.datasets[kind].records)

    def records(self, kind: DatasetKind) -> list[Any]:
        ds = self.datasets.get(kind)
        return list(ds.records) if ds else []

    def evidence(self, *kinds: DatasetKind) -> list[str]:
        return [self.datasets[k].evidence_id for k in kinds if k in self.datasets]

    def row_errors(self) -> list[RowError]:
        return [e for ds in self.datasets.values() for e in ds.row_errors]

    def inventory(self) -> list[dict[str, Any]]:
        return [
            {
                "kind": kind.value,
                "rows": len(ds.records),
                "row_errors": len(ds.row_errors),
                "as_of": ds.as_of.isoformat(),
                "evidence_id": ds.evidence_id,
                "source_uri": ds.source_uri,
            }
            for kind, ds in sorted(self.datasets.items())
        ]
