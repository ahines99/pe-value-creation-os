"""Application wiring from environment configuration.

Environment variables (see .env.example):
- DATABASE_URL: PostgreSQL (pvc_app role). Unset -> in-memory repository (dev/tests only).
- PVC_SOURCE_ADAPTER: fixtures (default) | csv | warehouse | composite
- PVC_PROPOSER: rules (default) | model
- PVC_OPERATOR_COMPANIES / PVC_WORKER_COMPANIES: companies the CLI operator / worker may act on.
"""

from __future__ import annotations

import os
from pathlib import Path

from .adapters.base import SourceAdapter
from .adapters.repositories import Repository, get_repository
from .policy import get_policy
from .security import Principal
from .workflows.proposals import Proposer
from .workflows.steps import RunContext


def adapter_from_env() -> SourceAdapter:
    kind = os.environ.get("PVC_SOURCE_ADAPTER", "fixtures")
    if kind == "fixtures":
        from .adapters.fixtures import FixtureAdapter

        return FixtureAdapter(os.environ.get("PVC_FIXTURE_ROOT") or None)
    if kind == "csv":
        from .adapters.csv_export import CsvExportAdapter

        csv_adapter: SourceAdapter = CsvExportAdapter(Path(os.environ["PVC_CSV_ROOT"]))
        return csv_adapter
    if kind == "warehouse":
        from .adapters.warehouse import WarehouseAdapter

        wh: SourceAdapter = WarehouseAdapter.from_env()
        return wh
    if kind == "composite":
        from .adapters.composite import CompositeAdapter

        comp: SourceAdapter = CompositeAdapter.from_env()
        return comp
    raise ValueError(f"Unknown PVC_SOURCE_ADAPTER {kind!r}")


def proposer_from_env() -> Proposer:
    kind = os.environ.get("PVC_PROPOSER", "rules")
    if kind == "rules":
        from .workflows.proposals import RuleBasedProposer

        return RuleBasedProposer()
    if kind == "model":
        from .llm.proposer import ModelProposer

        model: Proposer = ModelProposer.from_env()
        return model
    raise ValueError(f"Unknown PVC_PROPOSER {kind!r}")


def build_context(
    repo: Repository | None = None, adapter: SourceAdapter | None = None, actor: str = "system:workflow"
) -> RunContext:
    narrator = None
    if os.environ.get("PVC_PROPOSER") == "model":
        from .llm.narrator import ModelNarrator

        narrator = ModelNarrator.from_env()
    return RunContext(
        repo=repo or get_repository(),
        adapter=adapter or adapter_from_env(),
        policy=get_policy(),
        proposer=proposer_from_env(),
        narrator=narrator,
        actor=actor,
    )


def companies_from_env(var: str, adapter: SourceAdapter) -> frozenset[str]:
    raw = os.environ.get(var)
    if raw:
        return frozenset(c.strip() for c in raw.split(",") if c.strip())
    if os.environ.get("PVC_ENV", "prod") == "dev":
        return frozenset(adapter.list_companies())
    return frozenset()


def operator_principal(adapter: SourceAdapter) -> Principal:
    user = os.environ.get("PVC_OPERATOR") or os.environ.get("USERNAME") or os.environ.get("USER") or "operator"
    return Principal(
        subject=f"human:{user}",
        companies=companies_from_env("PVC_OPERATOR_COMPANIES", adapter),
        roles=frozenset({"operator"}),
        principal_type="human",
    )
