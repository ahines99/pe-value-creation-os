"""Data-sufficiency checks per analysis (PVC-024).

An analysis is INSUFFICIENT when a required dataset is missing or empty, has too little history, is stale
relative to the run's reference date, has gaps in a monthly series, or has a row-error rate above 2%.
Duplicate customer entities and small row-error counts are warnings: the analysis can run, but the gap is
carried into the output.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from ..policy import PolicyConfig
from .calc import add_months, month_of, month_range
from .dataset import CompanyData
from .source_models import Customer, DatasetKind

ANALYSES = ("unit_economics", "pricing", "retention", "ai_opportunity")
ROW_ERROR_RATE_MAX = 0.02

MONTHLY_SERIES = {DatasetKind.PNL, DatasetKind.ARR, DatasetKind.HEADCOUNT}
# Datasets expected to have data every month. A fresh extract whose latest month is old is still stale.
# Sparse event data (churn, concessions, CRM opportunities) can legitimately be quiet for weeks.
CONTINUOUS = MONTHLY_SERIES | {DatasetKind.INVOICES, DatasetKind.USAGE, DatasetKind.SUPPORT}


class SufficiencyStatus(StrEnum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class Gap(BaseModel):
    code: str
    dataset: str | None
    detail: str
    blocking: bool


class SufficiencyResult(BaseModel):
    analysis: str
    status: SufficiencyStatus
    gaps: list[Gap] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    @property
    def sufficient(self) -> bool:
        return self.status == SufficiencyStatus.SUFFICIENT


def _months_of(kind: DatasetKind, records: list[Any]) -> list[date]:
    months: set[date] = set()
    for r in records:
        if hasattr(r, "month"):
            months.add(r.month)
        elif hasattr(r, "invoice_date"):
            months.add(month_of(r.invoice_date))
        elif hasattr(r, "created_at"):
            months.add(month_of(r.created_at.date() if isinstance(r.created_at, datetime) else r.created_at))
        elif hasattr(r, "concession_date"):
            months.add(month_of(r.concession_date))
    return sorted(months)


def _duplicate_entities(customers: list[Customer]) -> list[list[str]]:
    by_domain: dict[str, list[str]] = defaultdict(list)
    for c in customers:
        if c.domain:
            by_domain[c.domain.lower()].append(c.customer_id)
    return [ids for ids in by_domain.values() if len(ids) > 1]


_TITLES = {"pnl": "P&L", "arr": "ARR", "crm_opportunities": "CRM opportunities"}


def _title(name: object) -> str:
    """Readable dataset name for gap text shown to reviewers."""
    key = str(getattr(name, "value", name))
    return _TITLES.get(key, key.replace("_", " ").capitalize())


def check(data: CompanyData, analysis: str, policy: PolicyConfig) -> SufficiencyResult:
    if analysis not in policy.sufficiency:
        raise ValueError(f"Unknown analysis {analysis!r}; valid: {sorted(policy.sufficiency)}")
    rule = policy.sufficiency[analysis]
    gaps: list[Gap] = []
    evidence: list[str] = []
    for name in rule.required + rule.optional:
        kind = DatasetKind(name)
        required = name in rule.required
        ds = data.datasets.get(kind)
        if ds is not None and not ds.records and ds.row_errors:
            gaps.append(
                Gap(
                    code="row_errors",
                    dataset=name,
                    blocking=required,
                    detail=f"{_title(name)} has no valid rows ({len(ds.row_errors)} invalid); first: {ds.row_errors[0]}",
                )
            )
            continue
        if ds is None or not ds.records:
            gaps.append(
                Gap(
                    code="missing_dataset",
                    dataset=name,
                    blocking=required,
                    detail=f"{_title(name)} dataset is {'missing' if ds is None else 'empty'}",
                )
            )
            continue
        evidence.append(ds.evidence_id)
        age = (data.reference_date - ds.as_of.date()).days
        if age > policy.freshness.max_age_days:
            gaps.append(
                Gap(
                    code="stale_dataset",
                    dataset=name,
                    blocking=required,
                    detail=f"{_title(name)} extract dated {ds.as_of.date()} is {age} days old "
                    f"(limit {policy.freshness.max_age_days})",
                )
            )
        months = _months_of(kind, ds.records)
        if kind in CONTINUOUS and months:
            lag = (data.reference_date - add_months(months[-1], 1)).days  # days since the latest month ended
            if lag > policy.freshness.max_age_days:
                gaps.append(
                    Gap(
                        code="stale_series",
                        dataset=name,
                        blocking=required,
                        detail=f"{_title(name)} latest data month is {months[-1].isoformat()}, which ended {lag} days before "
                        f"the reference date (limit {policy.freshness.max_age_days})",
                    )
                )
        span = len(month_range(months[0], months[-1])) if months else 0
        if span < rule.min_months and kind not in {
            DatasetKind.CUSTOMERS,
            DatasetKind.PRICE_BOOKS,
            DatasetKind.CONTRACTS,
            DatasetKind.DOCUMENTS,
        }:
            gaps.append(
                Gap(
                    code="insufficient_history",
                    dataset=name,
                    blocking=required,
                    detail=f"{_title(name)} spans {span} months; {rule.min_months} required",
                )
            )
        if kind in MONTHLY_SERIES and months:
            missing = [m for m in month_range(months[0], months[-1]) if m not in set(months)]
            if missing:
                gaps.append(
                    Gap(
                        code="month_gaps",
                        dataset=name,
                        blocking=required,
                        detail=f"{_title(name)} is missing months: {', '.join(m.isoformat() for m in missing)}",
                    )
                )
        foreign = sorted({c for r in ds.records if (c := getattr(r, "currency", None)) and c != data.profile.currency})
        if foreign:
            n_foreign = sum(getattr(r, "currency", None) in foreign for r in ds.records)
            gaps.append(
                Gap(
                    code="currency_mismatch",
                    dataset=name,
                    blocking=required,
                    detail=f"{_title(name)} has {n_foreign} rows in {', '.join(foreign)}; company currency is "
                    f"{data.profile.currency}. Amounts are never converted or summed across currencies.",
                )
            )
        n_err = len(ds.row_errors)
        if n_err:
            rate = n_err / (n_err + len(ds.records))
            gaps.append(
                Gap(
                    code="row_errors",
                    dataset=name,
                    blocking=required and rate > ROW_ERROR_RATE_MAX,
                    detail=f"{_title(name)} has {n_err} invalid rows ({rate:.2%}); first: {ds.row_errors[0]}",
                )
            )
        if kind == DatasetKind.CUSTOMERS:
            dups = _duplicate_entities(ds.records)
            if dups:
                gaps.append(
                    Gap(
                        code="duplicate_entities",
                        dataset=name,
                        blocking=False,
                        detail=f"{len(dups)} customer domains map to multiple customer ids "
                        f"(entity resolution needed), e.g. {dups[0]}",
                    )
                )
            er = data.entity_resolution or {}
            if er.get("review_queue") or er.get("unresolved_rows"):
                gaps.append(
                    Gap(
                        code="unresolved_entities",
                        dataset=name,
                        blocking=False,
                        detail=f"{er.get('review_queue', 0)} identifiers await review; unresolved rows "
                        f"{er.get('unresolved_rows', {})} are reported under segment 'unknown'",
                    )
                )
    status = SufficiencyStatus.INSUFFICIENT if any(g.blocking for g in gaps) else SufficiencyStatus.SUFFICIENT
    return SufficiencyResult(analysis=analysis, status=status, gaps=gaps, evidence_ids=evidence)


def check_all(data: CompanyData, policy: PolicyConfig) -> dict[str, SufficiencyResult]:
    return {a: check(data, a, policy) for a in ANALYSES}
