"""Composite adapter: one company's datasets from several systems, with entity resolution (PVC-110, PVC-117).

Configuration (TOML, path in PVC_SOURCES_CONFIG; see docs/sources.example.toml):

    [companies.<company_id>]
    base = "csv" | "warehouse"          # adapter for datasets not overridden (and the profile)
    [companies.<company_id>.sources]    # dataset -> vendor adapter name
    invoices = "stripe"
    customers = "hubspot"
    [companies.<company_id>.id_systems] # id space of customer-keyed datasets from the base
    arr = "stripe"
    [companies.<company_id>.stripe]     # credentials come from environment variables named here
    api_key_env = "STRIPE_KEY_ACME"
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from ..domain import entity_resolution as er
from ..domain.dataset import CompanyData
from ..domain.source_models import DatasetKind
from .base import EvidenceSink, SourceAdapter, SourceError
from .sources import DatasetSource


@dataclass
class CompanySources:
    base: SourceAdapter
    sources: dict[DatasetKind, DatasetSource] = field(default_factory=dict)
    id_systems: dict[DatasetKind, str] = field(default_factory=dict)
    resolver: er.Resolver = field(default_factory=er.Resolver)


class CompositeAdapter:
    name = "composite"

    def __init__(self, companies: dict[str, CompanySources]):
        self.companies = companies

    def list_companies(self) -> list[str]:
        return sorted(self.companies)

    def _cfg(self, company_id: str) -> CompanySources:
        if company_id not in self.companies:
            raise SourceError(f"No source configuration for {company_id!r}")
        return self.companies[company_id]

    def reference_date(self, company_id: str) -> date:
        return self._cfg(company_id).base.reference_date(company_id)

    def load(self, company_id: str, sink: EvidenceSink | None = None) -> CompanyData:
        cfg = self._cfg(company_id)
        data = cfg.base.load(company_id, sink)
        loaded: set[int] = set()
        for src in cfg.sources.values():
            if id(src) in loaded:
                continue
            loaded.add(id(src))
            for k, ds in src.load_datasets(company_id, sink).items():
                if cfg.sources.get(k) is src:
                    data.datasets[k] = ds
        foreign: list[er.ForeignEntity] = []
        for src in {id(s): s for s in cfg.sources.values()}.values():
            fe = getattr(src, "foreign_entities", None)
            if fe:
                foreign += fe()
        systems = {k: v for k, v in cfg.id_systems.items()}
        for kind, src in cfg.sources.items():
            if kind in er.CUSTOMER_KEYED and kind not in systems and getattr(src, "name", "") in ("stripe", "zendesk"):
                systems[kind] = src.name
        resolution = cfg.resolver.resolve(data.records(DatasetKind.CUSTOMERS), foreign)
        report = er.apply(data, resolution, systems)
        report["review_items"] = [r.model_dump() for r in resolution.review_queue[:50]]
        data.entity_resolution = report
        return data

    @classmethod
    def from_env(cls) -> CompositeAdapter:
        path = os.environ.get("PVC_SOURCES_CONFIG")
        if not path:
            raise SourceError("PVC_SOURCES_CONFIG is not set")
        return cls.from_file(Path(path))

    @classmethod
    def from_file(cls, path: Path) -> CompositeAdapter:
        cfg = tomllib.loads(path.read_text(encoding="utf-8"))
        return cls({cid: _build(cid, c) for cid, c in cfg.get("companies", {}).items()})


def _env(section: dict[str, Any], key: str) -> str:
    name = section.get(key)
    if not name or not os.environ.get(name):
        raise SourceError(f"Environment variable {name!r} for {key} is not set")
    return os.environ[name]


def _build(company_id: str, c: dict[str, Any]) -> CompanySources:
    base_kind = c.get("base", "csv")
    if base_kind == "csv":
        from .csv_export import CsvExportAdapter

        base: SourceAdapter = CsvExportAdapter(Path(c.get("csv_root") or os.environ["PVC_CSV_ROOT"]))
    elif base_kind == "warehouse":
        from .warehouse import WarehouseAdapter

        base = WarehouseAdapter(_env(c.get("warehouse", {}), "url_env"), c.get("warehouse", {}).get("schema", "pvc"))
    else:
        raise SourceError(f"Unknown base adapter {base_kind!r} for {company_id}")
    vendors: dict[str, Any] = {}
    for vendor in c.get("sources", {}).values():
        if vendor not in vendors:
            vendors[vendor] = _vendor(vendor, c.get(vendor, {}))
    return CompanySources(
        base=base,
        sources={DatasetKind(k): vendors[v] for k, v in c.get("sources", {}).items()},
        id_systems={DatasetKind(k): v for k, v in c.get("id_systems", {}).items()},
        resolver=er.Resolver(overrides=c.get("entity_overrides", {}),
                             accept_name_matches=bool(c.get("accept_name_matches", False))),
    )


def _vendor(name: str, section: dict[str, Any]) -> Any:
    if name == "stripe":
        from .stripe_billing import StripeBillingAdapter

        return StripeBillingAdapter(_env(section, "api_key_env"))
    if name == "hubspot":
        from .hubspot_crm import HubSpotCrmAdapter

        return HubSpotCrmAdapter(_env(section, "token_env"))
    if name == "zendesk":
        from .zendesk_support import ZendeskConfig, ZendeskSupportAdapter

        return ZendeskSupportAdapter(
            section["subdomain"], section["email"], _env(section, "token_env"),
            ZendeskConfig(int(section["category_field_id"]), int(section["handle_minutes_field_id"]),
                          {int(g) for g in section.get("tier1_group_ids", [])}))
    raise SourceError(f"Unknown vendor adapter {name!r}")
