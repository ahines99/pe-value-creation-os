"""Constructed KPI definitions and observations retained in immutable case revisions.

A changed target or population never changes the definition attached to an older
observation. Ratios aggregate from their numerators and denominators, not an
unweighted average. These observations do not establish financial attribution.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .models import Record
from .source_revisions import OperatingRecordRef
from .underwriting import month_end

Metric = Literal["net_price_uplift", "service_quality_pass_rate", "collection_rate"]
METRIC_KIND = {"net_price_uplift": "pricing", "service_quality_pass_rate": "service", "collection_rate": "collections"}


class LineageKpiDefinition(Record):
    definition_id: str = Field(min_length=1)
    initiative_id: str = Field(min_length=1)
    metric: Metric
    unit: Literal["fraction"] = "fraction"
    classification: Literal["constructed_kpi_definition"] = "constructed_kpi_definition"
    population: tuple[OperatingRecordRef, ...] = Field(min_length=1)
    baseline_start: date
    baseline_end: date
    baseline_numerator: Decimal
    baseline_denominator: Decimal = Field(gt=0)
    target: Decimal
    target_on: date
    rationale: str = Field(min_length=1)
    revision_kind: Literal["initial", "target_change", "scope_correction"] = "initial"
    supersedes_definition_id: str | None = None
    predecessor_definition_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.baseline_start.day != 1 or self.baseline_end != month_end(self.baseline_start):
            raise ValueError("KPI baseline requires one complete calendar month")
        if self.target_on <= self.baseline_end:
            raise ValueError("KPI target must follow its baseline")
        if len({(r.kind, r.record_id) for r in self.population}) != len(self.population):
            raise ValueError("KPI population cannot repeat a source record")
        if len(set(self.predecessor_definition_ids)) != len(self.predecessor_definition_ids):
            raise ValueError("KPI predecessors must be unique")
        if self.supersedes_definition_id and self.predecessor_definition_ids:
            raise ValueError("KPI target correction and population lineage are distinct transitions")
        if bool(self.supersedes_definition_id) != (self.revision_kind != "initial"):
            raise ValueError("KPI correction must explicitly identify its revision kind and predecessor")
        if any(not v.is_finite() for v in (self.baseline_numerator, self.baseline_denominator, self.target)):
            raise ValueError("KPI values must be finite")
        if self.metric != "net_price_uplift" and (
            not 0 <= self.baseline_numerator <= self.baseline_denominator or not 0 <= self.target <= 1
        ):
            raise ValueError("quality and collection KPI fractions must be between zero and one")
        return self


class LineageKpiReading(Record):
    observation_id: str = Field(min_length=1)
    definition_id: str = Field(min_length=1)
    classification: Literal["constructed_kpi_observation"] = "constructed_kpi_observation"
    start: date
    end: date
    numerator: Decimal
    denominator: Decimal = Field(gt=0)
    evidence: str = Field(min_length=1)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    supersedes_observation_id: str | None = None

    @model_validator(mode="after")
    def source(self) -> Self:
        if self.start.day != 1 or self.end != month_end(self.start):
            raise ValueError("KPI reading requires one complete calendar month")
        if not self.numerator.is_finite() or not self.denominator.is_finite():
            raise ValueError("KPI reading must be finite")
        if hashlib.sha256(self.evidence.encode()).hexdigest() != self.evidence_sha256:
            raise ValueError("KPI reading evidence hash mismatch")
        return self


class LineageKpiBook(Record):
    definitions: tuple[LineageKpiDefinition, ...] = ()
    observations: tuple[LineageKpiReading, ...] = ()

    @model_validator(mode="after")
    def history(self) -> Self:
        definitions: dict[str, LineageKpiDefinition] = {}
        replaced: set[str] = set()
        for item in self.definitions:
            if item.definition_id in definitions:
                raise ValueError("KPI definition IDs are immutable and unique")
            if item.supersedes_definition_id:
                old = definitions.get(item.supersedes_definition_id)
                if old is None or old.definition_id in replaced:
                    raise ValueError("KPI target revision requires its latest predecessor")
                preserved: tuple[str, ...] = ("initiative_id", "metric", "unit")
                if item.revision_kind == "target_change":
                    preserved += (
                        "population",
                        "baseline_start",
                        "baseline_end",
                        "baseline_numerator",
                        "baseline_denominator",
                    )
                if any(getattr(old, k) != getattr(item, k) for k in preserved):
                    raise ValueError("target revision cannot silently change KPI population, metric or baseline")
                replaced.add(old.definition_id)
            for predecessor in item.predecessor_definition_ids:
                old = definitions.get(predecessor)
                if (
                    old is None
                    or old.metric != item.metric
                    or old.unit != item.unit
                    or old.initiative_id == item.initiative_id
                ):
                    raise ValueError(
                        "KPI population lineage requires prior comparable definitions on predecessor initiatives"
                    )
            definitions[item.definition_id] = item
        readings: dict[str, LineageKpiReading] = {}
        heads: dict[tuple[str, date], str] = {}
        for reading in self.observations:
            if reading.observation_id in readings or reading.definition_id not in definitions:
                raise ValueError("KPI reading requires a unique ID and registered exact definition")
            definition = definitions[reading.definition_id]
            if reading.start < definition.baseline_start:
                raise ValueError("KPI reading cannot precede its defined baseline period")
            if definition.metric != "net_price_uplift" and not 0 <= reading.numerator <= reading.denominator:
                raise ValueError("quality and collection KPI fractions must be between zero and one")
            key = (reading.definition_id, reading.start)
            if reading.supersedes_observation_id != heads.get(key):
                raise ValueError("KPI reading correction must bind the latest same-definition, same-period observation")
            heads[key] = reading.observation_id
            readings[reading.observation_id] = reading
        return self

    def retain(self, prior: LineageKpiBook) -> None:
        if (
            self.definitions[: len(prior.definitions)] != prior.definitions
            or self.observations[: len(prior.observations)] != prior.observations
        ):
            raise ValueError("KPI revisions must retain all prior definitions and observations unchanged")


def kpi_report(
    book: LineageKpiBook,
    current_initiatives: set[str],
    *,
    population_validator: Callable[[list[LineageKpiDefinition]], None] | None = None,
) -> dict[str, Any]:
    replaced = {d.supersedes_definition_id for d in book.definitions}
    active = [d for d in book.definitions if d.initiative_id in current_initiatives and d.definition_id not in replaced]
    corrected = {o.supersedes_observation_id for o in book.observations}
    observations = [o for o in book.observations if o.observation_id not in corrected]
    groups = []
    for metric in sorted({d.metric for d in active}):
        members = [d for d in active if d.metric == metric]
        populations = [(r.kind, r.record_id) for d in members for r in d.population]
        if population_validator is not None:
            population_validator(members)
        elif len(set(populations)) != len(populations):
            raise ValueError("KPI aggregation cannot overlap current populations")
        ids = {d.definition_id for d in members}
        periods = sorted({(o.start, o.end) for o in observations if o.definition_id in ids})
        for start, end in periods:
            readings = [o for o in observations if o.definition_id in ids and o.start == start and o.end == end]
            complete = {o.definition_id for o in readings} == ids
            numerator = sum((o.numerator for o in readings), Decimal(0)) if complete else None
            denominator = sum((o.denominator for o in readings), Decimal(0)) if complete else None
            groups.append(
                {
                    "metric": metric,
                    "start": start,
                    "end": end,
                    "definition_ids": sorted(ids),
                    "observation_ids": [o.observation_id for o in readings],
                    "status": "constructed_complete" if complete else "missing_current_population",
                    "numerator": numerator,
                    "denominator": denominator,
                    "value": numerator / denominator if numerator is not None and denominator is not None else None,
                }
            )
    return {
        "active_definition_ids": [d.definition_id for d in active],
        "definitions": [d.model_dump(mode="json") for d in book.definitions],
        "observations": [o.model_dump(mode="json") for o in book.observations],
        "current_population_observations": groups,
        "historical_child_actuals": None,
        "financial_attribution": None,
        "authority": "Constructed KPI history. Prior parent observations retain their original populations and targets; no historical child observations or financial benefits are inferred from a split.",
    }
