"""Peer benchmark data (PVC-116).

Only distributions (quartiles and peer count) are stored and returned; no portfolio-company-level values.
Peer sets with fewer than MIN_PEERS companies are refused to preserve anonymity. The bundled file is a
SYNTHETIC placeholder; production points PVC_BENCHMARK_PATH at a licensed dataset whose provenance is recorded
in the same columns.
"""

from __future__ import annotations

import csv
import hashlib
import os
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

MIN_PEERS = 5
DEFAULT_PATH = Path(__file__).with_name("peer_benchmarks.csv")


class BenchmarkDistribution(BaseModel):
    metric: str
    peer_set: str
    n: int
    p25: Decimal
    p50: Decimal
    p75: Decimal
    source: str
    licence: str
    as_of: date
    dataset_sha256: str
    synthetic: bool


class InsufficientPeers(ValueError):
    pass


@lru_cache(maxsize=4)
def _load(path: str) -> tuple[str, list[dict[str, str]]]:
    raw = Path(path).read_bytes()
    return hashlib.sha256(raw).hexdigest(), list(csv.DictReader(raw.decode("utf-8").splitlines()))


def get_benchmark(metric: str, peer_set: str, path: str | None = None) -> BenchmarkDistribution:
    digest, rows = _load(path or os.environ.get("PVC_BENCHMARK_PATH", str(DEFAULT_PATH)))
    for r in rows:
        if r["metric"] == metric and r["peer_set"] == peer_set:
            n = int(r["n"])
            if n < MIN_PEERS:
                raise InsufficientPeers(f"Peer set {peer_set!r} has {n} companies for {metric!r}; minimum is "
                                        f"{MIN_PEERS} to preserve anonymity")
            return BenchmarkDistribution(
                metric=metric, peer_set=peer_set, n=n, p25=Decimal(r["p25"]), p50=Decimal(r["p50"]),
                p75=Decimal(r["p75"]), source=r["source"], licence=r["licence"],
                as_of=date.fromisoformat(r["as_of"]), dataset_sha256=digest,
                synthetic=r["source"].upper().startswith("SYNTHETIC"))
    available = sorted({(r["metric"], r["peer_set"]) for r in rows})
    raise KeyError(f"No benchmark for {metric!r} in {peer_set!r}; available: {available}")
