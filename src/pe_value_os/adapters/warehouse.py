"""Warehouse adapter (PVC-111, PVC-114; ADR 0008 warehouse-first).

Reads contract-shaped views from the portco's warehouse through SQLAlchemy (PostgreSQL, Snowflake, BigQuery or
any dialect installed). The portco (or a dbt package we provide) exposes one view per dataset:

    <schema>.pvc_<dataset>            columns exactly as in docs/data_contracts.md, including company_id
    <schema>.pvc_dataset_freshness    (company_id, dataset, as_of) - optional; defaults to load time
    <schema>.pvc_company_profile      (company_id, profile_json, reference_date) - optional

Access is read-only (use a warehouse role limited to these views). Queries always filter by company_id and
refuse rows for other companies.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, date, datetime
from typing import Any

from ..domain.dataset import CompanyData
from ..domain.source_models import CompanyProfile, DatasetKind
from .base import EvidenceSink, SourceError, TransientSourceError, make_evidence
from .sources import dataset_from_records

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class WarehouseAdapter:
    name = "warehouse"

    def __init__(self, url: str, schema: str = "pvc", datasets: list[DatasetKind] | None = None):
        if not IDENT.match(schema):
            raise ValueError(f"Invalid schema name {schema!r}")
        from sqlalchemy import create_engine

        self.engine = create_engine(url, pool_pre_ping=True)
        self.schema = schema
        self.datasets = datasets or list(DatasetKind)

    @classmethod
    def from_env(cls) -> WarehouseAdapter:
        url = os.environ.get("PVC_WAREHOUSE_URL")
        if not url:
            raise SourceError("PVC_WAREHOUSE_URL is not set")
        return cls(url, os.environ.get("PVC_WAREHOUSE_SCHEMA", "pvc"))

    def _query(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError, ProgrammingError

        try:
            with self.engine.connect() as conn:
                return [dict(r._mapping) for r in conn.execute(text(sql), params)]
        except ProgrammingError:
            raise
        except OperationalError as e:
            raise TransientSourceError(f"warehouse unavailable: {type(e).__name__}") from e

    def _exists(self, view: str) -> bool:
        from sqlalchemy import inspect

        insp = inspect(self.engine)
        return view in insp.get_view_names(schema=self.schema) or view in insp.get_table_names(schema=self.schema)

    def list_companies(self) -> list[str]:
        rows = self._query(f"select distinct company_id from {self.schema}.pvc_arr order by 1", {})
        return [r["company_id"] for r in rows]

    def _profile(self, company_id: str) -> tuple[CompanyProfile, bytes, date]:
        if self._exists("pvc_company_profile"):
            rows = self._query(f"select profile_json, reference_date from {self.schema}.pvc_company_profile "
                               "where company_id = :c", {"c": company_id})
            if rows:
                raw = rows[0]["profile_json"]
                raw_bytes = (raw if isinstance(raw, str) else json.dumps(raw)).encode()
                ref = rows[0]["reference_date"] or datetime.now(UTC).date()
                return CompanyProfile.model_validate_json(raw_bytes), raw_bytes, ref
        raise SourceError(f"No profile for {company_id!r} in {self.schema}.pvc_company_profile")

    def reference_date(self, company_id: str) -> date:
        return self._profile(company_id)[2]

    def load(self, company_id: str, sink: EvidenceSink | None = None) -> CompanyData:
        profile, raw, ref = self._profile(company_id)
        pev = make_evidence(company_id, f"warehouse://{self.schema}/pvc_company_profile/{company_id}",
                            "company_profile", raw, None)
        if sink:
            sink.add_evidence(pev)
        data = CompanyData(profile=profile, profile_evidence_id=pev.evidence_id, reference_date=ref)
        freshness: dict[str, datetime] = {}
        if self._exists("pvc_dataset_freshness"):
            for r in self._query(f"select dataset, as_of from {self.schema}.pvc_dataset_freshness "
                                 "where company_id = :c", {"c": company_id}):
                freshness[r["dataset"]] = r["as_of"]
        for kind in self.datasets:
            view = f"pvc_{kind.value}"
            if not self._exists(view):
                continue
            rows = self._query(f"select * from {self.schema}.{view} where company_id = :c", {"c": company_id})
            rows = [{k: _plain(v) for k, v in r.items()} for r in rows]
            as_of = freshness.get(kind.value)
            if as_of is not None and as_of.tzinfo is not None:
                as_of = as_of.astimezone(UTC).replace(tzinfo=None)
            data.datasets[kind] = dataset_from_records(
                kind, company_id, _sorted(rows), source_uri=f"warehouse://{self.schema}/{view}", as_of=as_of,
                sink=sink)
        return data


def _plain(v: Any) -> Any:
    return v.isoformat() if isinstance(v, datetime | date) else v


def _sorted(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, default=str))
