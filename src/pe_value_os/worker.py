"""Background worker (PVC-134): executes queued and resumed runs, refreshes KPIs, escalates stale approvals.

Runs in its own process so MCP server restarts never interrupt workflows. Each job executes under a system
principal scoped to exactly one company.
"""

from __future__ import annotations

import json
import os
import socket
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import anyio

from . import kpi, notify
from .adapters.repositories import LeaseLost
from .domain.kpi_models import Notification
from .domain.models import AuditEvent
from .domain.runs import ApprovalRecord, Status
from .observability import get_logger, metrics
from .security import principal_scope, system_principal
from .workflows import primary
from .workflows.steps import RunContext

log = get_logger(__name__)

HEARTBEAT_S = 120.0  # lease renewal interval; the claim lease is 15 minutes


@dataclass
class WorkerReport:
    runs_executed: int = 0
    kpi_observations: int = 0
    digests_sent: int = 0
    approvals_escalated: int = 0
    stuck_runs: int = 0


class Worker:
    def __init__(
        self,
        ctx: RunContext,
        companies: frozenset[str],
        worker_id: str | None = None,
        notifier: notify.Notifier | None = None,
    ):
        self.ctx = ctx
        self.companies = companies
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self.notifier = notifier or notify.notifier_from_env()

    async def run_queue(self) -> int:
        # A sequential worker has one slot. Never reserve jobs that cannot be heartbeated yet.
        n = 0
        for _ in range(5):
            owner = f"{self.worker_id}:{uuid.uuid4()}"
            with principal_scope(system_principal(*self.companies, subject=f"system:worker:{self.worker_id}")):
                claimed = self.ctx.repo.claim_runnable(owner, limit=1)
            if not claimed:
                break
            rec = claimed[0]
            with principal_scope(system_principal(rec.company_id, subject=f"system:worker:{self.worker_id}")):
                try:
                    ctx = replace(self.ctx, repo=self.ctx.repo.fenced_run(rec.run_id, owner), _data={})
                    async with anyio.create_task_group() as tg:
                        tg.start_soon(self._heartbeat, rec.run_id, owner)
                        await primary.execute(ctx, rec.run_id)
                        tg.cancel_scope.cancel()
                    n += 1
                finally:
                    self.ctx.repo.release_run(rec.run_id, owner)
        return n

    async def _heartbeat(self, run_id: str, owner: str) -> None:
        """Lease loss raises into the task group, cancelling execution and tripping attempt guards."""
        while True:
            await anyio.sleep(HEARTBEAT_S)
            if not self.ctx.repo.renew_lease(run_id, owner):
                log.error("run_lease_lost", run_id=run_id, worker_id=self.worker_id)
                raise LeaseLost(run_id)

    def _deliver(self, n: Notification, approval: ApprovalRecord | None = None) -> bool:
        owner = str(uuid.uuid4())
        if not self.ctx.repo.claim_notification(n, owner):
            return False
        try:
            if approval is None:
                self.notifier.deliver(self.ctx.repo, n)
            else:
                self.notifier.escalate(self.ctx.repo, approval, self.ctx.policy.approval.escalation_contact)
        except Exception:
            self.ctx.repo.finish_notification(n.notification_id, owner, delivered=False)
            raise
        self.ctx.repo.finish_notification(n.notification_id, owner, delivered=True)
        return True

    def refresh_kpis(self, now: datetime | None = None) -> tuple[int, int]:
        obs = sent = 0
        for cid in sorted(self.companies):
            with principal_scope(system_principal(cid, subject="system:kpi")):
                try:
                    obs += len(kpi.refresh_company(self.ctx.repo, self.ctx.adapter, cid, self.ctx.policy, now=now))
                except Exception as exc:  # one company's failure must not stop the others
                    log.warning("kpi_refresh_failed", company_id=cid, error_type=type(exc).__name__)
                    continue
                digest = kpi.build_digest(
                    self.ctx.repo,
                    cid,
                    channel=self.notifier.channel,
                    base_url=os.environ.get("PVC_PUBLIC_URL", ""),
                    now=now,
                )
                if digest:
                    self.ctx.repo.add_notification(digest)
                # Retry persisted messages even if their original observation is no longer current.
                for n in self.ctx.repo.list_notifications(cid):
                    if n.status == "pending" and n.subject != "Plan approval overdue":
                        try:
                            sent += int(self._deliver(n))
                        except Exception as exc:
                            log.warning("digest_delivery_failed", company_id=cid, error_type=type(exc).__name__)
        return obs, sent

    def escalate_approvals(self, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        limit = timedelta(hours=self.ctx.policy.approval.expiry_hours)
        n = 0
        with principal_scope(system_principal(*self.companies, subject="system:escalation")):
            pending = self.ctx.repo.pending_approvals()
        for a in pending:
            if a.escalated_at is not None or now - a.requested_at < limit:
                continue
            with principal_scope(system_principal(a.company_id, subject="system:escalation")):
                notification = Notification(
                    notification_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"escalation:{a.approval_id}")),
                    company_id=a.company_id,
                    channel=self.notifier.channel,
                    subject="Plan approval overdue",
                    body=f"Approval {a.approval_id} overdue; contact {self.ctx.policy.approval.escalation_contact}",
                    created_at=now,
                )
                existing = {x.notification_id: x for x in self.ctx.repo.list_notifications(a.company_id)}
                delivered = existing.get(notification.notification_id)
                if not delivered or delivered.status != "delivered":
                    if not self._deliver(notification, a):
                        continue
                self.ctx.repo.mark_escalated(a.approval_id)
                self.ctx.repo.append_audit(
                    AuditEvent(
                        run_id=a.run_id,
                        company_id=a.company_id,
                        step="human_approval",
                        actor="system:escalation",
                        event_type="approval_escalated",
                        created_at=now,
                        payload={
                            "approval_id": a.approval_id,
                            "escalation_contact": self.ctx.policy.approval.escalation_contact,
                        },
                    )
                )
                n += 1
        return n

    def record_health(self, now: datetime | None = None, stuck_after: timedelta = timedelta(minutes=30)) -> int:
        """Gauges for alerting (PVC-103): stuck runs and the oldest pending approval."""
        now = now or datetime.now(UTC)
        with principal_scope(system_principal(*self.companies, subject="system:health")):
            running = self.ctx.repo.list_runs(status=Status.RUNNING)
            pending = self.ctx.repo.pending_approvals()
        stuck = sum(1 for r in running if r.params.get("mode") != "interactive" and now - r.updated_at > stuck_after)
        metrics().runs_stuck.set(stuck)
        oldest = max(((now - a.requested_at).total_seconds() / 3600 for a in pending), default=0.0)
        metrics().approvals_pending_oldest.set(round(oldest, 2))
        return stuck

    async def tick(self, now: datetime | None = None) -> WorkerReport:
        r = WorkerReport()
        r.runs_executed = await self.run_queue()
        r.kpi_observations, r.digests_sent = self.refresh_kpis(now)
        r.approvals_escalated = self.escalate_approvals(now)
        r.stuck_runs = self.record_health(now)
        log.info("worker_tick", worker_id=self.worker_id, count=r.runs_executed)
        return r

    async def _health_heartbeat(self) -> None:
        path = Path(os.environ.get("PVC_WORKER_HEARTBEAT_PATH", "var/worker-heartbeat"))
        path.parent.mkdir(parents=True, exist_ok=True)
        await anyio.to_thread.run_sync(lambda: path.unlink(missing_ok=True))
        while True:
            try:
                with principal_scope(system_principal(*self.companies, subject="system:health")):
                    self.ctx.repo.list_companies()
                temp = path.with_suffix(".tmp")
                temp.write_text(
                    json.dumps({"pid": os.getpid(), "updated_at": datetime.now(UTC).isoformat()}), encoding="utf-8"
                )
                temp.replace(path)
            except Exception as exc:
                log.warning("worker_health_probe_failed", error_type=type(exc).__name__)
            await anyio.sleep(30)

    async def forever(self, interval_s: float = 30.0) -> None:
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._health_heartbeat)
            while True:
                try:
                    await self.tick()
                except Exception as exc:
                    log.error("worker_tick_failed", error_type=type(exc).__name__)
                await anyio.sleep(interval_s)
