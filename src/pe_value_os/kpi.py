"""KPI monitoring (PVC-120, PVC-121, PVC-122, PVC-123).

- `activate_plan` persists an approved plan's KPIs. Unmonitorable KPIs are rejected at approval time.
- `refresh_company` recomputes due KPIs from freshly loaded data using the same metric registry that set
  their baselines, and records observations with evidence.
- Variance rules are deterministic: *threshold* (actual misses the interpolated target by more than the policy
  tolerance) and *trend* (N consecutive observations moving the wrong way). Alerts are audited.
- `build_digest` produces a read-only summary; delivery is by a human-configured channel (notify.py).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Any

from . import freshness
from .adapters.base import SourceAdapter
from .adapters.repositories import Repository
from .domain.baselines import REGISTRY, compute_metric
from .domain.calc import MetricUnavailable, add_months, q_ratio
from .domain.kpi_models import KpiAlert, KpiDefinition, KpiObservation, Notification
from .domain.models import AuditEvent
from .domain.runs import PlanRecord
from .observability import get_logger, metrics
from .policy import PolicyConfig

log = get_logger(__name__)


class UnmonitorableKpi(ValueError):
    pass


def _audit(
    repo: Repository, company_id: str, event_type: str, actor: str, run_id: str | None = None, **payload: Any
) -> None:
    repo.append_audit(
        AuditEvent(
            run_id=run_id,
            company_id=company_id,
            step="kpi_monitoring",
            actor=actor,
            event_type=event_type,
            created_at=datetime.now(UTC),
            payload=payload,
        )
    )


def plan_kpis(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [k for ws in plan.get("workstreams", []) for k in ws.get("kpis", [])]


def check_monitorable(plan: dict[str, Any]) -> None:
    bad = [k["metric"] for k in plan_kpis(plan) if k["metric"] not in REGISTRY or not k.get("monitorable", True)]
    covered = {
        k.get("opportunity_id")
        for k in plan_kpis(plan)
        if k.get("metric") in REGISTRY and k.get("monitorable", True) and k.get("evidence_ids")
    }
    missing = [
        i["opportunity_id"]
        for ws in plan.get("workstreams", [])
        for i in ws.get("initiatives", [])
        if i["opportunity_id"] not in covered
    ]
    if missing:
        raise UnmonitorableKpi(f"Initiatives have no computable, evidence-backed KPI: {sorted(missing)}")
    if bad:
        raise UnmonitorableKpi(f"KPIs cannot be monitored (no registered metric): {sorted(set(bad))}")


def activate_plan(
    repo: Repository, plan: PlanRecord, approved_plan: dict[str, Any], start: date, actor: str
) -> list[KpiDefinition]:
    check_monitorable(approved_plan)
    now = datetime.now(UTC)
    defs = [
        KpiDefinition(
            kpi_id=k["kpi_id"],
            company_id=plan.company_id,
            plan_id=plan.plan_id,
            run_id=plan.run_id,
            metric=k["metric"],
            metric_params=k.get("metric_params", {}),
            description=k["description"],
            baseline=Decimal(str(k["baseline"])),
            day_100_target=Decimal(str(k["day_100_target"])),
            run_rate_target=Decimal(str(k["run_rate_target"])),
            direction=k["direction"],
            cadence_days=int(k["cadence_days"]),
            source=k["source"],
            evidence_ids=k.get("evidence_ids", []),
            start_date=start,
            created_at=now,
        )
        for k in plan_kpis(approved_plan)
    ]
    repo.save_kpi_definitions(defs)
    _audit(repo, plan.company_id, "kpis_activated", actor, plan.run_id, plan_id=plan.plan_id, count=len(defs))
    return defs


def target_on(d: KpiDefinition, on: date) -> Decimal:
    """Linear path: baseline at start, day-100 target at +100 days, run-rate target at +365 days."""
    days = (on - d.start_date).days
    if days <= 0:
        return d.baseline
    if days <= 100:
        return d.baseline + (d.day_100_target - d.baseline) * Decimal(days) / 100
    if days <= 365:
        return d.day_100_target + (d.run_rate_target - d.day_100_target) * Decimal(days - 100) / 265
    return d.run_rate_target


def _off_track(d: KpiDefinition, actual: Decimal, target: Decimal, tolerance: Decimal) -> tuple[bool, Decimal]:
    """Variance is signed so that positive means better than target. Tolerance is relative to |target|."""
    variance = actual - target if d.direction == "increase" else target - actual
    allowed = abs(target) * tolerance
    return variance < -allowed, q_ratio(variance)


def _due(d: KpiDefinition, last: KpiObservation | None, now: datetime) -> bool:
    return last is None or now - last.observed_at >= timedelta(days=d.cadence_days)


def refresh_company(
    repo: Repository,
    adapter: SourceAdapter,
    company_id: str,
    policy: PolicyConfig,
    *,
    now: datetime | None = None,
    force: bool = False,
    actor: str = "system:kpi",
) -> list[KpiObservation]:
    now = now or datetime.now(UTC)
    defs = repo.list_kpi_definitions(company_id)
    if not defs:
        return []
    data = adapter.load(company_id, sink=repo)
    freshness.record(data, policy.freshness.max_age_days)
    out: list[KpiObservation] = []
    for d in defs:
        history = repo.list_kpi_observations(company_id, d.kpi_id)
        if not force and not _due(d, history[-1] if history else None, now):
            continue
        try:
            value = compute_metric(data, d.metric, d.metric_params)
        except MetricUnavailable as exc:
            _audit(repo, company_id, "kpi_unavailable", actor, d.run_id, kpi_id=d.kpi_id, reason_code=str(exc)[:80])
            continue
        # Compare like with like: the target for the end of the month the data covers, not for today (sources lag).
        as_of = now.date()
        if value.period_end is not None:
            as_of = min(as_of, add_months(value.period_end, 1) - timedelta(days=1))
        target = q_ratio(target_on(d, as_of))
        off, variance = _off_track(d, value.value, target, policy.kpi.off_track_tolerance)
        obs = KpiObservation(
            observation_id=str(uuid.uuid4()),
            kpi_id=d.kpi_id,
            company_id=company_id,
            observed_at=now,
            period_end=value.period_end,
            value=value.value,
            target=target,
            status="off_track" if off else "on_track",
            variance=variance,
            evidence_ids=value.evidence_ids,
        )
        repo.add_kpi_observation(obs)
        out.append(obs)
        _audit(repo, company_id, "kpi_observed", actor, d.run_id, kpi_id=d.kpi_id, status=obs.status)
        for alert in detect_variance(d, [*history, obs], policy):
            repo.add_kpi_alert(alert)
            metrics().kpi_off_track.add(1, {"rule": alert.rule})
            _audit(repo, company_id, "kpi_alert", actor, d.run_id, kpi_id=d.kpi_id, reason_code=alert.rule)
    return out


def covers_plan_period(d: KpiDefinition, o: KpiObservation) -> bool:
    """True when the reading covers a month ending after the plan started. Earlier readings are baselines,
    so they cannot show a plan as on or off track. A reading without a source period counts from the start date."""
    if o.period_end is None:
        return o.observed_at.date() >= d.start_date
    return add_months(o.period_end, 1) - timedelta(days=1) > d.start_date


def detect_variance(d: KpiDefinition, history: list[KpiObservation], policy: PolicyConfig) -> list[KpiAlert]:
    """Alerts for the latest observation. Threshold: the KPI has just gone off track (a KPI that stays off track is
    reported in every digest but alerts once). Trend: N consecutive wrong-way moves. Pre-plan readings are ignored."""
    history = [o for o in history if covers_plan_period(d, o)]
    if not history:
        return []
    last = history[-1]
    alerts: list[KpiAlert] = []
    now = datetime.now(UTC)
    newly_off = last.status == "off_track" and (len(history) < 2 or history[-2].status != "off_track")
    if newly_off:
        alerts.append(
            KpiAlert(
                alert_id=str(uuid.uuid4()),
                kpi_id=d.kpi_id,
                company_id=d.company_id,
                observation_id=last.observation_id,
                rule="threshold",
                created_at=now,
                detail=f"{d.metric} {last.value} vs target {last.target} (variance {last.variance})",
            )
        )
    n = policy.kpi.trend_decline_periods
    if len(history) > n:
        window = [o.value for o in history[-(n + 1) :]]
        pairs = list(pairwise(window))
        worse = all((b < a) if d.direction == "increase" else (b > a) for a, b in pairs)
        if worse:
            alerts.append(
                KpiAlert(
                    alert_id=str(uuid.uuid4()),
                    kpi_id=d.kpi_id,
                    company_id=d.company_id,
                    observation_id=last.observation_id,
                    rule="trend",
                    created_at=now,
                    detail=f"{d.metric} moved the wrong way for {n} consecutive observations",
                )
            )
    return alerts


def build_digest(
    repo: Repository, company_id: str, *, channel: str, base_url: str = "", now: datetime | None = None
) -> Notification | None:
    """Read-only digest of off-track KPIs. Returns None when everything is on track."""
    defs = {d.kpi_id: d for d in repo.list_kpi_definitions(company_id)}
    latest: dict[str, KpiObservation] = {}
    for o in repo.list_kpi_observations(company_id):
        latest[o.kpi_id] = o
    off = [
        (defs[k], o)
        for k, o in latest.items()
        if k in defs and o.status == "off_track" and covers_plan_period(defs[k], o)
    ]
    if not off:
        return None
    lines = [f"- {d.description}: {o.value} vs target {o.target} (as of {o.period_end})" for d, o in off]
    link = f"{base_url.rstrip('/')}/companies/{company_id}/kpis" if base_url else f"/companies/{company_id}/kpis"
    now = now or datetime.now(UTC)
    body = "\n".join([*lines, "", f"Details: {link}"])
    # At most one unchanged summary per UTC day, shared by every worker replica.
    key = f"digest:{company_id}:{channel}:{now.date()}:{hashlib.sha256(body.encode()).hexdigest()}"
    n = Notification(
        notification_id=str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
        company_id=company_id,
        channel=channel,
        subject=f"{len(off)} KPI(s) off track",
        body=body,
        created_at=now,
    )
    repo.add_notification(n)
    return n
