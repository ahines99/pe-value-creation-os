"""Zendesk support adapter (PVC-115): tickets with category, tier, handle time and CSAT.

Read-only API token (email/token basic auth). Uses the cursor-based incremental ticket export and the
organizations list (for entity resolution by domain).

Configuration (`ZendeskConfig`): which custom field holds the category and handle minutes, and which group ids
are tier 1. CSAT: satisfaction_rating.score "good" -> 5, "bad" -> 2, otherwise empty. Tickets without an
organization are excluded (they cannot be attributed to a customer) and counted in the dataset's row errors.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..domain.entity_resolution import ForeignEntity
from ..domain.source_models import Dataset, DatasetKind, RowError
from .base import EvidenceSink
from .sources import ApiClient, dataset_from_records


@dataclass
class ZendeskConfig:
    category_field_id: int
    handle_minutes_field_id: int
    tier1_group_ids: set[int] = field(default_factory=set)


class ZendeskSupportAdapter:
    name = "zendesk"
    provides = frozenset({DatasetKind.SUPPORT})

    def __init__(
        self,
        subdomain: str,
        email: str,
        token: str,
        config: ZendeskConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        base_url: str | None = None,
    ):
        auth = base64.b64encode(f"{email}/token:{token}".encode()).decode()
        self.api = ApiClient(
            base_url or f"https://{subdomain}.zendesk.com", {"Authorization": f"Basic {auth}"}, transport=transport
        )
        self.config = config

    def organizations(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page = self.api.get("/api/v2/organizations.json")
        while True:
            out += page.get("organizations", [])
            nxt = page.get("next_page")
            if not nxt:
                return out
            page = self.api.get(nxt.replace(self.api.base_url, ""))

    def foreign_entities(self) -> list[ForeignEntity]:
        return [
            ForeignEntity("zendesk", str(o["id"]), o.get("name"), (o.get("domain_names") or [None])[0])
            for o in self.organizations()
        ]

    def load_datasets(self, company_id: str, sink: EvidenceSink | None) -> dict[DatasetKind, Dataset]:
        tickets: list[dict[str, Any]] = []
        pages: list[Any] = []
        params: dict[str, Any] = {"start_time": 0}
        while True:
            page = self.api.get("/api/v2/incremental/tickets/cursor.json", params)
            pages.append(page)
            tickets += page.get("tickets", [])
            if page.get("end_of_stream") or not page.get("after_cursor"):
                break
            params = {"cursor": page["after_cursor"]}
        rows, skipped = [], 0
        for t in tickets:
            if not t.get("organization_id"):
                skipped += 1
                continue
            fields = {f["id"]: f.get("value") for f in t.get("custom_fields", [])}
            score = (t.get("satisfaction_rating") or {}).get("score")
            rows.append(
                {
                    "ticket_id": str(t["id"]),
                    "customer_id": str(t["organization_id"]),
                    "created_at": t["created_at"].replace("Z", ""),
                    "category": fields.get(self.config.category_field_id),
                    "severity": {"urgent": "high", "high": "high", "normal": "medium"}.get(
                        t.get("priority") or "", "low"
                    ),
                    "tier": "tier1" if t.get("group_id") in self.config.tier1_group_ids else "tier2",
                    "handle_minutes": fields.get(self.config.handle_minutes_field_id),
                    "csat": {"good": 5, "bad": 2}.get(score or ""),
                }
            )
        ds = dataset_from_records(
            DatasetKind.SUPPORT,
            company_id,
            rows,
            source_uri="zendesk://api/v2/incremental/tickets",
            as_of=None,
            sink=sink,
            raw_payload=pages,
        )
        if skipped:
            ds.row_errors.append(
                RowError(
                    source="zendesk tickets",
                    row=0,
                    field="organization_id",
                    message=f"{skipped} tickets without an organization were excluded",
                )
            )
        return {DatasetKind.SUPPORT: ds}
