"""Failure injection (PVC-046).

`FaultInjectingAdapter` wraps a source adapter and fails chosen calls (transient, permanent, or malformed data).
`inject` patches a diagnostic branch or a whole step to fail a fixed number of times, then clears, so tests can
verify partial-failure handling and resume after the fault is gone.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..adapters.base import EvidenceSink, SourceAdapter, SourceError, TransientSourceError
from ..domain.dataset import CompanyData
from ..domain.source_models import DatasetKind
from . import steps as S


@dataclass
class Fault:
    kind: str  # transient | error | timeout | malformed
    times: int = 1
    dataset: DatasetKind | None = None  # for malformed
    hits: int = 0

    def fire(self) -> bool:
        if self.hits < self.times:
            self.hits += 1
            return True
        return False

    def raise_(self, where: str) -> None:
        if self.kind == "transient":
            raise TransientSourceError(f"injected transient fault at {where}")
        if self.kind == "timeout":
            raise TimeoutError(f"injected timeout at {where}")
        raise SourceError(f"injected fault at {where}")


@dataclass
class FaultInjectingAdapter:
    inner: SourceAdapter
    load_fault: Fault | None = None
    name: str = "fault-injecting"
    calls: list[str] = field(default_factory=list)

    def list_companies(self) -> list[str]:
        return self.inner.list_companies()

    def reference_date(self, company_id: str) -> date:
        return self.inner.reference_date(company_id)

    def load(self, company_id: str, sink: EvidenceSink | None = None) -> CompanyData:
        self.calls.append(company_id)
        f = self.load_fault
        if f and f.kind != "malformed" and f.fire():
            f.raise_("adapter.load")
        data = self.inner.load(company_id, sink)
        if f and f.kind == "malformed" and f.dataset and f.fire():
            ds = data.datasets.get(f.dataset)
            if ds:
                ds.records = []  # the malformed payload parsed to nothing usable
        return data


@contextmanager
def inject(*, branch: str | None = None, step: str | None = None, fault: Fault) -> Iterator[Fault]:
    """Make a diagnostic branch or a step service fail `fault.times` times."""
    if branch:
        analyse, findings = S.BRANCH_ANALYSIS[branch]

        def failing(data: CompanyData, *a: Any, **k: Any) -> Any:
            if fault.fire():
                fault.raise_(f"branch:{branch}")
            return analyse(data, *a, **k)

        S.BRANCH_ANALYSIS[branch] = (failing, findings)
        try:
            yield fault
        finally:
            S.BRANCH_ANALYSIS[branch] = (analyse, findings)
        return
    if step:
        original = getattr(S, step)

        def failing_step(ctx: S.RunContext, state: Any) -> Any:
            if fault.fire():
                fault.raise_(f"step:{step}")
            return original(ctx, state)

        setattr(S, step, failing_step)
        try:
            yield fault
        finally:
            setattr(S, step, original)
        return
    raise ValueError("inject requires branch= or step=")
