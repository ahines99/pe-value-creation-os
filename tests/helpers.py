"""Tiny hand-built datasets whose expected results are computed by hand in the tests."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pe_value_os.domain.dataset import CompanyData
from pe_value_os.domain.source_models import CompanyProfile, Dataset, DatasetKind

AS_OF = datetime(2026, 2, 1)


def make_data(company_id: str = "mini", reference: date = date(2026, 2, 10), **datasets: list[Any]) -> CompanyData:
    profile = CompanyProfile(
        company_id=company_id,
        name="Mini Co",
        business_model="SaaS",
        vertical="test",
        currency="USD",
        fiscal_year_start_month=1,
    )
    data = CompanyData(profile=profile, profile_evidence_id="ev-profile", reference_date=reference)
    for name, records in datasets.items():
        kind = DatasetKind(name)
        data.datasets[kind] = Dataset(
            kind=kind, records=records, evidence_id=f"ev-{name}", as_of=AS_OF, source_uri=f"test://{name}"
        )
    return data


def D(x: str | int) -> Decimal:
    return Decimal(str(x))
