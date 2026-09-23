"""Checkpointing workflow runner (PVC-040, PVC-041, PVC-042, PVC-044).

- State is saved after every step; completed steps are skipped on resume, so reruns are idempotent.
- A step pauses the run by setting `state.status` to NEEDS_EVIDENCE or AWAITING_APPROVAL.
- A step may raise `Rewind(to_step)` to re-open that step and everything after it (changes requested).
- Each step has a timeout and a bounded retry budget for transient errors only (timeouts and
  `TransientSourceError`); everything else fails the run immediately.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

import anyio

from ..adapters.base import SourceError, TransientSourceError
from ..domain.models import AuditEvent
from ..domain.runs import PAUSED, RunState, Status
from ..observability import get_logger, metrics, span, timed

log = get_logger(__name__)

TRANSIENT: tuple[type[BaseException], ...] = (TransientSourceError, TimeoutError)


class Rewind(Exception):
    def __init__(self, to_step: str, reason: str):
        super().__init__(reason)
        self.to_step = to_step
        self.reason = reason


class Step(Protocol):
    name: str
    timeout_s: float
    retries: int

    async def execute(self, state: RunState) -> RunState: ...


class StateStore(Protocol):
    def save_run_state(self, state: RunState) -> None: ...


class AuditSink(Protocol):
    def append_audit(self, event: AuditEvent) -> None: ...


StepFn = Callable[[RunState], Awaitable[Any]]


@dataclass
class FunctionalStep:
    name: str
    fn: StepFn
    timeout_s: float = 300.0
    retries: int = 2

    async def execute(self, state: RunState) -> RunState:
        state.artifacts[self.name] = await self.fn(state)
        return state


@dataclass
class ParallelStep:
    """Run branches concurrently. A failed branch is recorded as a gap; the step fails only if all fail."""

    name: str
    branches: dict[str, StepFn]
    timeout_s: float = 600.0
    retries: int = 1
    branch_timeout_s: float = 300.0

    async def execute(self, state: RunState) -> RunState:
        results: dict[str, Any] = {}
        failures: dict[str, str] = {}

        async def run(key: str, fn: StepFn) -> None:
            try:
                with span(f"branch:{key}", run_id=state.run_id, branch=key), anyio.fail_after(self.branch_timeout_s):
                    results[key] = await fn(state)
            except Exception as exc:  # recorded, not raised: partial results are allowed
                failures[key] = f"{type(exc).__name__}: {exc}"
                log.warning("branch_failed", run_id=state.run_id, branch=key, error_type=type(exc).__name__)

        async with anyio.create_task_group() as tg:
            for key, fn in self.branches.items():
                tg.start_soon(run, key, fn)

        if not results:
            raise RuntimeError(f"All {self.name} branches failed: {failures}")
        state.artifacts[self.name] = {"results": results, "failures": failures}
        state.errors.extend(f"{self.name}.{k}: {v}" for k, v in sorted(failures.items()))
        return state


@dataclass
class Runner:
    store: StateStore
    audit: AuditSink
    actor: str = "system:workflow"
    backoff_s: float = 0.5
    policy_version: str = ""
    _events: list[str] = field(default_factory=list)

    def emit(self, state: RunState, event_type: str, **payload: Any) -> None:
        self.audit.append_audit(
            AuditEvent(
                run_id=state.run_id,
                company_id=state.company_id,
                step=state.current_step or "run",
                actor=self.actor,
                event_type=event_type,
                created_at=datetime.now(UTC),
                payload={**payload, "policy_version": self.policy_version} if self.policy_version else payload,
            )
        )
        log.info(
            event_type,
            run_id=state.run_id,
            company_id=state.company_id,
            step=state.current_step,
            status=state.status.value,
        )

    async def _attempt(self, step: Step, state: RunState) -> RunState:
        attempt = 0
        while True:
            attempt += 1
            try:
                with anyio.fail_after(step.timeout_s):
                    return await step.execute(state)
            except TRANSIENT as exc:
                if attempt > step.retries:
                    raise
                self.emit(state, "step_retry", attempt=attempt, error_type=type(exc).__name__)
                await anyio.sleep(self.backoff_s * (2 ** (attempt - 1)))

    async def run(self, state: RunState, steps: list[Step]) -> RunState:
        """Run or resume. Returns the state after completion, a pause, a rejection, or a failure."""
        names = [s.name for s in steps]
        state.status = Status.RUNNING
        state.pause_reason = None
        self.store.save_run_state(state)
        with span("run", run_id=state.run_id, company_id=state.company_id):
            i = 0
            while i < len(steps):
                step = steps[i]
                i += 1
                if step.name in state.completed_steps:
                    continue
                state.current_step = step.name
                self.emit(state, "step_started")
                with span(f"step:{step.name}", run_id=state.run_id, step=step.name), timed() as t:
                    try:
                        state = await self._attempt(step, state)
                    except Rewind as rw:
                        idx = names.index(rw.to_step)
                        state.completed_steps = [s for s in state.completed_steps if s not in names[idx:]]
                        self.emit(state, "run_rewound", to_step=rw.to_step, reason_code="changes_requested")
                        self.store.save_run_state(state)
                        i = 0
                        continue
                    except Exception as exc:
                        if isinstance(exc, SourceError | TimeoutError):
                            metrics().adapter_errors.add(1, {"step": step.name, "error_type": type(exc).__name__})
                        state.errors.append(f"{step.name}: {type(exc).__name__}: {exc}")
                        state.status = Status.FAILED
                        self.store.save_run_state(state)
                        self.emit(state, "step_failed", error_type=type(exc).__name__)
                        metrics().step_duration.record(t["ms"], {"step": step.name, "status": "failed"})
                        metrics().runs.add(1, {"status": Status.FAILED.value})
                        return state
                metrics().step_duration.record(t["ms"], {"step": step.name, "status": state.status.value})
                if state.status in PAUSED or state.status == Status.REJECTED:
                    self.store.save_run_state(state)
                    self.emit(state, f"run_{state.status.value}", duration_ms=t["ms"])
                    metrics().runs.add(1, {"status": state.status.value})
                    return state
                state.completed_steps.append(step.name)
                self.store.save_run_state(state)
                self.emit(state, "step_completed", duration_ms=t["ms"])
            state.status = Status.COMPLETE
            state.current_step = None
            self.store.save_run_state(state)
            self.emit(state, "run_completed")
            metrics().runs.add(1, {"status": Status.COMPLETE.value})
            return state
