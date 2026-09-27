"""Typed numeric provenance and server-rendered claim references.

Only Python numeric fields from typed calculation results become references. IDs,
document text and JSON strings cannot authorize quantitative claims. A reference
renders its metric, unit, company, period and evidence together, so a value cannot
silently be moved to a different metric in model prose.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from .guardrails import unsupported_numbers

REFERENCE = re.compile(r"\{\{quantity:([\w.\[\]-]+)\}\}")


@dataclass(frozen=True)
class SourceQuantity:
    key: str
    metric: str
    value: Decimal
    unit: str
    company_id: str
    period: str
    evidence_ids: tuple[str, ...]

    def render(self) -> str:
        return (
            f"[{self.metric}: {self.value} {self.unit}; company={self.company_id}; "
            f"period={self.period}; evidence={','.join(self.evidence_ids)}]"
        )


def source_quantities(
    obj: Any, *, company_id: str, evidence_ids: list[str], period: str, prefix: str = "analysis"
) -> dict[str, SourceQuantity]:
    result: dict[str, SourceQuantity] = {}

    def walk(value: Any, path: str, context: dict[str, Any]) -> None:
        if isinstance(value, BaseModel):
            walk(value.model_dump(mode="python"), path, context)
        elif isinstance(value, dict):
            context = context | {
                k: v for k, v in value.items() if k in {"unit", "name", "period_start", "period_end", "evidence_ids"}
            }
            for key, child in value.items():
                walk(child, f"{path}.{key}", context)
        elif isinstance(value, list | tuple):
            for i, child in enumerate(value):
                walk(child, f"{path}[{i}]", context)
        elif isinstance(value, int | float | Decimal) and not isinstance(value, bool):
            numeric = Decimal(str(value))
            if not numeric.is_finite():
                return
            metric = f"{context['name']} ({path})" if context.get("name") else path
            unit = str(context.get("unit") or "source units")
            when = (
                f"{context.get('period_start', '')}..{context['period_end']}" if context.get("period_end") else period
            )
            result[path] = SourceQuantity(
                path, metric, numeric, unit, company_id, when, tuple(context.get("evidence_ids", evidence_ids))
            )

    walk(obj, prefix, {})
    return result


def catalog(quantities: dict[str, SourceQuantity]) -> list[dict[str, Any]]:
    return [asdict(q) | {"value": str(q.value)} for q in quantities.values()]


def render_claims(text: str, sources: dict[str, SourceQuantity]) -> str:
    """Reject unbound numbers and expand only exact, server-issued references."""
    keys = REFERENCE.findall(text)
    if any(key not in sources for key in keys):
        raise ValueError("unknown numeric source reference")
    bare = REFERENCE.sub("", text)
    for q in sources.values():
        bare = bare.replace(q.render(), "")
    if "{{quantity:" in bare:
        raise ValueError("malformed numeric source reference")
    bad = unsupported_numbers(bare, [])
    if bad:
        raise ValueError(f"introduces numbers not present in a bound tool output: {bad[:5]}")
    return REFERENCE.sub(lambda m: sources[m[1]].render(), text)
