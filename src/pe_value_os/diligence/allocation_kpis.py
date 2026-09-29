"""Explicit KPI measurement scopes for shared economic pools.

Shares describe the measured population; they never scale an observation. A
reading must already contain the numerator and denominator for its exact scope.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .lineage_kpis import LineageKpiBook, LineageKpiDefinition, kpi_report
from .models import Record


class KpiAllocationScope(Record):
    pool_id: str = Field(min_length=1)
    mode: Literal["partition", "exclusive"]
    population_share: Decimal = Field(gt=0, le=1)

    @model_validator(mode="after")
    def exclusive(self) -> Self:
        if self.mode == "exclusive" and self.population_share != 1:
            raise ValueError("exclusive KPI scope requires the complete pool")
        return self


class AllocatedKpiDefinition(LineageKpiDefinition):
    allocation_scope: KpiAllocationScope


class AllocatedKpiBook(LineageKpiBook):
    definitions: tuple[AllocatedKpiDefinition, ...] = ()

    @model_validator(mode="after")
    def allocation_history(self) -> Self:
        definitions = {d.definition_id: d for d in self.definitions}
        for definition in self.definitions:
            if definition.revision_kind == "target_change":
                prior = definitions[definition.supersedes_definition_id or ""]
                if prior.allocation_scope != definition.allocation_scope:
                    raise ValueError("changing KPI allocation scope requires an explicit scope correction")
        return self


def validate_aggregate_population(members: list[LineageKpiDefinition]) -> None:
    """Accept shared records only within one explicit, non-overlapping pool."""
    scopes: dict[tuple[str, str], list[tuple[str, str, str, Decimal]]] = {}
    for definition in members:
        if not isinstance(definition, AllocatedKpiDefinition):
            raise ValueError("allocated KPI aggregation requires explicit scopes")
        scope = definition.allocation_scope
        for record in definition.population:
            scopes.setdefault((record.kind, record.record_id), []).append(
                (scope.pool_id, scope.mode, record.record_sha256, scope.population_share)
            )
    for entries in scopes.values():
        if len({row[:3] for row in entries}) != 1:
            raise ValueError("shared KPI records must bind the same pool, mode and evidence hash")
        if sum((row[3] for row in entries), Decimal(0)) > 1:
            raise ValueError("selected KPI populations cannot exceed the complete pool")


def allocated_kpi_report(book: AllocatedKpiBook, selected: set[str]) -> dict[str, Any]:
    result = kpi_report(book, selected, population_validator=validate_aggregate_population)
    result["version"] = "allocated-kpi-history/1"
    result["selected_initiatives"] = sorted(selected)
    observed = {o.definition_id for o in book.observations}
    result["unmeasured_current_definition_ids"] = sorted(set(result["active_definition_ids"]) - observed)
    result["authority"] = (
        "Constructed measurements for exact allocated populations. Only selected current scopes aggregate. "
        "Numerators and denominators are authored scoped observations, never multiplied by allocation shares. "
        "Earlier readings retain their exact definitions; no child actuals or financial attribution are inferred."
    )
    return result
