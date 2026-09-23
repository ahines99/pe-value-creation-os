"""Benchmark tool (PVC-116). Returns anonymized peer distributions only."""

from __future__ import annotations

from mcp.server import MCPServer

from ..adapters.repositories import NotFound
from ..benchmarks import BenchmarkDistribution, get_benchmark
from ._runtime import governed


def register_benchmark(mcp: MCPServer) -> None:
    @mcp.tool()
    @governed("get_benchmarks")
    def get_benchmarks(metric: str, peer_set: str) -> BenchmarkDistribution:
        """Peer quartiles (p25/p50/p75) and peer count for a metric. Never returns any single company's value.
        Check `synthetic` and `licence` before citing."""
        try:
            return get_benchmark(metric, peer_set)
        except KeyError as e:
            raise NotFound(str(e)) from e
