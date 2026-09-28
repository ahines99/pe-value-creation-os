"""Deterministic research calculations; never creates initiatives or approvals."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from .models import PilotBundle, Statement, revision_key

METRICS = {
    "revenue_growth": "Revenue growth (reported currency; includes acquisitions)",
    "gross_margin": "Standardized gross-margin proxy (SALE minus COGS) / SALE",
    "sga_intensity": "Standardized SG&A / revenue (may include R&D)",
    "operating_margin": "Standardized operating margin (OIADP / SALE)",
}


def select_statements(bundle: PilotBundle) -> tuple[list[Statement], dict[str, int]]:
    selected: dict[tuple[str, str, object], Statement] = {}
    excluded = {"future_period": 0, "future_vintage": 0, "future_availability": 0, "superseded": 0}
    for row in bundle.statements:
        if row.period_end > bundle.as_of.date():
            excluded["future_period"] += 1
            continue
        if row.vintage > bundle.as_of:
            excluded["future_vintage"] += 1
            continue
        if row.available_at and row.available_at > bundle.as_of:
            excluded["future_availability"] += 1
            continue
        key = row.entity_id, row.period, row.period_end
        previous = selected.get(key)
        if previous:
            excluded["superseded"] += 1
            fields = (
                "currency",
                "fiscal_year",
                "fiscal_quarter",
                "revenue",
                "cogs",
                "sga",
                "research_development",
                "operating_income",
            )
            if row.vintage == previous.vintage and any(getattr(row, f) != getattr(previous, f) for f in fields):
                raise ValueError("conflicting financial rows at the same vintage; reconcile source extracts first")
        if previous is None or revision_key(row) > revision_key(previous):
            selected[key] = row
    return sorted(selected.values(), key=lambda r: (r.ticker, r.period, r.period_end)), excluded


def metrics(row: Statement, rows: list[Statement]) -> dict[str, Decimal | None]:
    # Same fiscal quarter/year and a plausible year interval prevent growth over gaps/stubs.
    previous = [
        r
        for r in rows
        if r.entity_id == row.entity_id
        and r.period == row.period
        and r.currency == row.currency
        and r.fiscal_year == row.fiscal_year - 1
        and r.fiscal_quarter == row.fiscal_quarter
        and 330 <= (row.period_end - r.period_end).days <= 400
    ]
    prior = max(previous, key=lambda r: r.period_end) if previous else None
    return {
        "revenue_growth": row.revenue / prior.revenue - 1 if prior else None,
        "gross_margin": (row.revenue - row.cogs) / row.revenue if row.cogs is not None else None,
        "sga_intensity": row.sga / row.revenue if row.sga is not None else None,
        "operating_margin": row.operating_income / row.revenue if row.operating_income is not None else None,
    }


def analyze(bundle: PilotBundle) -> dict[str, Any]:
    rows, exclusions = select_statements(bundle)
    focal = next(
        (
            r
            for r in rows
            if r.ticker == bundle.focal_ticker and r.period == "annual" and r.period_end == bundle.anchor_period_end
        ),
        None,
    )
    if focal is None:
        raise ValueError("no eligible focal annual statement at the requested anchor date")
    cohort: list[dict[str, Any]] = []
    gaps = list(bundle.open_items)
    for peer in bundle.peers:
        candidates = [
            r
            for r in rows
            if r.ticker == peer.ticker
            and r.period == "annual"
            and r.currency == focal.currency
            and abs((r.period_end - focal.period_end).days) <= 183
        ]
        if not candidates:
            gaps.append(f"{peer.ticker}: no same-currency annual period within 183 days of the anchor")
            continue
        chosen = min(candidates, key=lambda r: (abs((r.period_end - focal.period_end).days), r.period_end))
        cohort.append(
            {
                "statement": chosen.model_dump(mode="json"),
                "metrics": metrics(chosen, rows),
                "rationale": peer.rationale,
                "limitation": peer.limitation,
                "alignment_days": (chosen.period_end - focal.period_end).days,
            }
        )
    benchmarks = {}
    for name in METRICS:
        values = [p["metrics"][name] for p in cohort if p["metrics"][name] is not None]
        benchmarks[name] = {"median": median(values) if len(values) >= 3 else None, "n": len(values)}
        if len(values) < 3:
            gaps.append(f"{name}: fewer than three usable peer observations; median withheld")
    focal_rows = [r for r in rows if r.ticker == bundle.focal_ticker]
    for year in range(bundle.first_year, focal.period_end.year + 1):
        if not any(r.period == "annual" and r.period_end.year == year for r in focal_rows):
            gaps.append(f"Focal annual history missing period ending in calendar {year}")
    reconciliations = []
    for check in bundle.reconciliations:
        row = next(
            (r for r in rows if r.ticker == check.ticker and r.period == "annual" and r.period_end == check.period_end),
            None,
        )
        actual = getattr(row, check.metric) if row else None
        expected = check.reported_millions + check.bridge_millions
        difference = actual - expected if actual is not None else None
        passed = difference is not None and abs(difference) <= Decimal("0.001")
        reconciliations.append(
            {
                **check.model_dump(mode="json"),
                "actual": actual,
                "difference": difference,
                "status": "matched" if passed else "unresolved",
            }
        )
    if not reconciliations:
        gaps.append("Independent source reconciliation has not been supplied")
    elif any(r["status"] != "matched" for r in reconciliations):
        gaps.append("One or more source reconciliations remain unresolved")
    if not any(r.period == "quarterly" for r in focal_rows):
        gaps.append("No quarterly focal-company statements available")
    focal_metrics = metrics(focal, rows)
    return {
        "schema_version": 1,
        "classification": bundle.classification,
        "research_mode": bundle.research_mode,
        "as_of": bundle.as_of.isoformat(),
        "focal": focal.model_dump(mode="json"),
        "focal_metrics": focal_metrics,
        "peers": cohort,
        "benchmarks": benchmarks,
        "exclusions": exclusions,
        "history": [
            {"statement": r.model_dump(mode="json"), "metrics": metrics(r, rows)}
            for r in focal_rows
            if r.period_end.year >= bundle.first_year
        ],
        "selected_statements": [r.model_dump(mode="json") for r in rows],
        "reconciliations": reconciliations,
        "gaps": gaps,
        "source_notes": bundle.source_notes,
        "sensitivity": [
            {"basis_points": bps, "gross_annual_effect_millions": focal.revenue * Decimal(bps) / 10000}
            for bps in (50, 100, 150)
        ],
        "human_acceptance": "pending",
        "operating_plan": "not_created",
    }


def private_destination(name: str) -> Path:
    """Keep licensed bundles out of docs, release assets and static showcase captures."""
    root = Path.cwd().resolve() / "var" / "research-pilot"
    if root.resolve() != root:
        raise ValueError("private research directory must not redirect through a symbolic link")
    destination = (root / name).resolve()
    if not destination.is_relative_to(root) or destination == root:
        raise ValueError("research outputs must stay inside var/research-pilot")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def build_report(source: Path, name: str = "pilot") -> Path:
    from .render import render_report

    raw = source.read_bytes()
    bundle = PilotBundle.model_validate_json(raw)
    report = analyze(bundle)
    report["input_sha256"] = hashlib.sha256(raw).hexdigest()
    html_path = private_destination(f"{name}.html")
    json_path = private_destination(f"{name}.json")
    if source.resolve() in {html_path, json_path}:
        raise ValueError("output must not overwrite the input bundle")
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    html_path.write_text(render_report(report), encoding="utf-8")
    return html_path
