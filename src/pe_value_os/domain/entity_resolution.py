"""Deterministic customer entity resolution across source systems (PVC-117).

Canonical customers come from the `customers` dataset (usually the CRM). Foreign identifiers (billing customer
ids, support organisation ids, product account ids) are matched to canonical ids by, in order:

1. an explicit override table (`overrides`: foreign id -> canonical id), set by a human reviewer;
2. normalized domain equality with exactly one canonical candidate;
3. normalized name equality with exactly one candidate, only when `accept_name_matches` is on (off by default:
   name-only matches go to the review queue).

Ambiguous or unmatched identifiers go to the review queue and are never guessed. Canonical customers sharing a
domain are reported as duplicates and merged onto the lowest id.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from .dataset import CompanyData
from .source_models import Customer, DatasetKind

SUFFIXES = re.compile(r"\b(inc|llc|ltd|limited|corp|corporation|co|company|gmbh|plc|sa|bv)\b\.?", re.I)


def norm_domain(d: str | None) -> str | None:
    if not d:
        return None
    d = d.strip().lower()
    d = d.split("@")[-1]
    d = re.sub(r"^https?://", "", d).split("/")[0]
    return d[4:] if d.startswith("www.") else d or None


def norm_name(n: str | None) -> str | None:
    if not n:
        return None
    n = SUFFIXES.sub("", n.lower())
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    return n or None


@dataclass(frozen=True)
class ForeignEntity:
    system: str
    foreign_id: str
    name: str | None = None
    domain: str | None = None


class ReviewItem(BaseModel):
    system: str
    foreign_id: str
    reason: str
    candidates: list[str]


class Resolution(BaseModel):
    mapping: dict[str, str]  # "system:foreign_id" -> canonical id
    duplicates: dict[str, str]  # duplicate canonical id -> surviving canonical id
    review_queue: list[ReviewItem]
    method_counts: dict[str, int]

    def resolve(self, system: str, foreign_id: str) -> str | None:
        return self.mapping.get(f"{system}:{foreign_id}")


@dataclass
class Resolver:
    overrides: dict[str, str] = field(default_factory=dict)  # "system:foreign_id" -> canonical id
    accept_name_matches: bool = False

    def resolve(self, customers: list[Customer], foreign: list[ForeignEntity]) -> Resolution:
        by_domain: dict[str, list[str]] = defaultdict(list)
        by_name: dict[str, list[str]] = defaultdict(list)
        for c in sorted(customers, key=lambda c: c.customer_id):
            if (d := norm_domain(c.domain)):
                by_domain[d].append(c.customer_id)
            if (n := norm_name(c.name)):
                by_name[n].append(c.customer_id)
        duplicates = {dup: ids[0] for ids in by_domain.values() if len(ids) > 1 for dup in ids[1:]}
        canonical = {c.customer_id for c in customers}
        mapping: dict[str, str] = {}
        review: list[ReviewItem] = []
        counts: dict[str, int] = defaultdict(int)
        for fe in foreign:
            key = f"{fe.system}:{fe.foreign_id}"
            if key in self.overrides:
                mapping[key] = self.overrides[key]
                counts["override"] += 1
                continue
            if fe.foreign_id in canonical:
                mapping[key] = duplicates.get(fe.foreign_id, fe.foreign_id)
                counts["same_id"] += 1
                continue
            d = norm_domain(fe.domain)
            cands = sorted({duplicates.get(i, i) for i in by_domain.get(d, [])}) if d else []
            if len(cands) == 1:
                mapping[key] = cands[0]
                counts["domain"] += 1
                continue
            if len(cands) > 1:
                review.append(ReviewItem(system=fe.system, foreign_id=fe.foreign_id, reason="ambiguous_domain",
                                         candidates=cands))
                continue
            n = norm_name(fe.name)
            ncands = sorted({duplicates.get(i, i) for i in by_name.get(n, [])}) if n else []
            if len(ncands) == 1 and self.accept_name_matches:
                mapping[key] = ncands[0]
                counts["name"] += 1
            elif ncands:
                review.append(ReviewItem(system=fe.system, foreign_id=fe.foreign_id,
                                         reason="name_match_needs_review" if len(ncands) == 1 else "ambiguous_name",
                                         candidates=ncands))
            else:
                review.append(ReviewItem(system=fe.system, foreign_id=fe.foreign_id, reason="no_match",
                                         candidates=[]))
        counts["duplicates"] = len(duplicates)
        return Resolution(mapping=mapping, duplicates=duplicates, review_queue=review, method_counts=dict(counts))


CUSTOMER_KEYED = (DatasetKind.ARR, DatasetKind.CHURN, DatasetKind.INVOICES, DatasetKind.CONCESSIONS,
                  DatasetKind.CONTRACTS, DatasetKind.SUPPORT, DatasetKind.USAGE, DatasetKind.CRM_OPPORTUNITIES)


def apply(data: CompanyData, resolution: Resolution, systems: dict[DatasetKind, str]) -> dict[str, Any]:
    """Rewrite customer ids in place: foreign ids -> canonical, duplicates -> survivor.

    `systems` names the id space of each dataset (e.g. {ARR: "stripe"}); datasets keyed by canonical ids use
    "canonical". Unresolved rows keep their foreign id (and so appear as segment "unknown") and are counted.
    """
    unresolved: dict[str, int] = defaultdict(int)
    for kind in CUSTOMER_KEYED:
        ds = data.datasets.get(kind)
        if not ds:
            continue
        system = systems.get(kind, "canonical")
        out = []
        for r in ds.records:
            cid = r.customer_id
            if cid == "prospect":
                out.append(r)
                continue
            target = resolution.resolve(system, cid) if system != "canonical" else cid
            if target is None:
                unresolved[kind.value] += 1
                target = cid
            target = resolution.duplicates.get(target, target)
            out.append(r if target == cid else r.model_copy(update={"customer_id": target}))
        ds.records = out
    cust = data.datasets.get(DatasetKind.CUSTOMERS)
    if cust:
        cust.records = [c for c in cust.records if c.customer_id not in resolution.duplicates]
    return {"unresolved_rows": dict(unresolved), "duplicates_merged": len(resolution.duplicates),
            "review_queue": len(resolution.review_queue), "methods": resolution.method_counts}
