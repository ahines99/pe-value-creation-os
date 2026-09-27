"""Source freshness monitoring (PVC-118).

Every time company data is loaded (run intake, KPI refresh), the age of each dataset's `as_of` relative to
the reference date is recorded as the gauge `pvc.source.age_days{company_id, dataset}`. The alert
`PvcSourceStale` fires when any source is older than the policy freshness window; sufficiency checks already
block analyses that depend on stale data.
"""

from __future__ import annotations

from .domain.dataset import CompanyData
from .observability import metrics


def source_ages(data: CompanyData) -> dict[str, int]:
    return {k.value: (data.reference_date - ds.as_of.date()).days for k, ds in data.datasets.items()}


def record(data: CompanyData, max_age_days: int) -> list[str]:
    """Record ages; return the datasets older than the window."""
    ages = source_ages(data)
    for dataset, age in ages.items():
        metrics().source_age.set(age, {"company_id": data.company_id, "dataset": dataset})
    return sorted(d for d, a in ages.items() if a > max_age_days)
