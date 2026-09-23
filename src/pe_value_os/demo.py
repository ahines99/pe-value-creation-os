"""One-command seeded demo (PVC-150): `pvc demo`.

Runs entirely in process on fictional fixture companies:
1. Success path: Beacon (pricing leak) -> sized opportunities -> 100-day plan -> paused for approval.
2. Human approval through the approval API (dev human token), the worker resumes the run, KPIs activate and a
   first KPI observation is recorded.
3. NEEDS_EVIDENCE: Delta (broken data) pauses at data sufficiency with explicit gaps and suspicious content.
4. Injected failure the run survives: Cedar with the pricing diagnostic failing; the run continues.
5. Injected failure that fails cleanly, then resumes: Cedar's value modeling fails once; operator resumes.
A markdown report is written to var/demo-report.md.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import anyio

from . import kpi, security
from .adapters.evidence_store import FileSystemEvidenceStore
from .adapters.fixtures import FixtureAdapter
from .adapters.repositories import InMemoryRepository
from .domain.runs import Status
from .observability import configure_logging
from .policy import get_policy
from .worker import Worker
from .workflows import faults, primary
from .workflows.steps import RunContext

APPROVER_TOKEN = "demo-approver"  # noqa: S105 - dev-only opaque token, honoured only when PVC_ENV=dev


def _money(x: Any) -> str:
    return f"{float(x):,.0f}"


def run_demo(verbose: bool = True, report_path: Path | None = None) -> int:
    configure_logging(stream=io.StringIO())
    os.environ.setdefault("PVC_ENV", "dev")
    if os.environ["PVC_ENV"] != "dev":
        raise SystemExit("pvc demo only runs with PVC_ENV=dev")
    tmp = Path(tempfile.mkdtemp(prefix="pvc-demo-"))
    ctx = RunContext(
        repo=InMemoryRepository(FileSystemEvidenceStore(tmp / "evidence")),
        adapter=FixtureAdapter(),
        policy=get_policy(),
        actor="system:demo",
    )
    out: list[str] = [
        "# PE Value Creation OS - demo report",
        "",
        "All companies are fictional fixtures. Every number comes from deterministic tools.",
        "",
    ]

    def say(line: str = "") -> None:
        out.append(line)
        if verbose:
            print(line)

    def scope(cid: str) -> Any:
        return security.principal_scope(security.system_principal(cid, subject="system:demo"))

    # 1. success path ---------------------------------------------------------------------------------------------
    say("## 1. Success path: Beacon Scheduling Systems (pricing leak)")
    with scope("beacon-pricing"):
        rec, _ = primary.start(ctx, "beacon-pricing", "human:demo-analyst", idempotency_key="demo-beacon")
        st = anyio.run(lambda: primary.execute(ctx, rec.run_id, backoff_s=0))
        say(f"- Run `{rec.run_id[:8]}` finished at **{st.status.value}** (step `{st.current_step}`).")
        for o in ctx.repo.list_opportunities(rec.run_id):
            vc = ctx.repo.get_value_case("beacon-pricing", o.opportunity_id)
            say(
                f"  - {o.title}: base-case run-rate EBITDA {_money(vc.annual_ebitda_base)} "
                f"(low {_money(vc.annual_ebitda_low)}, high {_money(vc.annual_ebitda_high)}); "
                f"{len(o.evidence_ids)} evidence items; calc `{vc.calc_version}`"
            )
        plan = ctx.repo.latest_plan(rec.run_id)
        assert plan is not None
        say(
            f"- 100-day plan: {len(plan.plan['workstreams'])} workstreams, total base-case run-rate "
            f"{_money(plan.plan['total_run_rate_ebitda_base'])} (in-year {_money(plan.plan['total_in_year_ebitda_base'])})."
        )
    beacon_run = rec.run_id

    # 2. approval through the API, worker resume, KPIs --------------------------------------------------------------
    say("")
    say("## 2. Human approval through the approval API, worker resumes")
    from fastapi.testclient import TestClient

    from .api import app as api

    os.environ["PVC_DEV_TOKENS"] = json.dumps(
        {
            APPROVER_TOKEN: {
                "sub": "human:demo-approver",
                "pvc_companies": ["beacon-pricing"],
                "pvc_roles": ["approver"],
                "pvc_principal_type": "human",
            }
        }
    )
    api.set_ctx(ctx)
    api.reset_auth()
    client = TestClient(api.app)
    denied = client.post(f"/runs/{beacon_run}/approvals", json={"decision": "approved"})
    say(f"- Unauthenticated approval attempt: HTTP {denied.status_code}.")
    resp = client.post(
        f"/runs/{beacon_run}/approvals",
        headers={"Authorization": f"Bearer {APPROVER_TOKEN}"},
        json={"decision": "approved", "rationale": "Proceed; hold discount changes until Q2 planning"},
    )
    say(f"- Approver decision recorded: HTTP {resp.status_code}, decided_by `{resp.json().get('decided_by')}`.")
    worker = Worker(ctx, frozenset({"beacon-pricing", "cedar-churn", "delta-broken"}), worker_id="demo-worker")
    report = anyio.run(worker.tick)
    with scope("beacon-pricing"):
        st = ctx.repo.get_run(beacon_run).run_state()
        defs = ctx.repo.list_kpi_definitions("beacon-pricing")
        obs = kpi.refresh_company(ctx.repo, ctx.adapter, "beacon-pricing", ctx.policy, force=True)
    say(
        f"- Worker tick resumed {report.runs_executed} run(s); run is **{st.status.value}**; "
        f"{len(defs)} KPIs activated; {len(obs)} KPI observations recorded "
        f"({sum(o.status == 'on_track' for o in obs)} on track)."
    )
    api.set_ctx(None)

    # 3. needs evidence ----------------------------------------------------------------------------------------------
    say("")
    say("## 3. Controlled pause: Delta Ledger Tools (broken data)")
    with scope("delta-broken"):
        rec, _ = primary.start(ctx, "delta-broken", "human:demo-analyst")
        st = anyio.run(lambda: primary.execute(ctx, rec.run_id, backoff_s=0))
        pause = st.pause_reason or {}
        say(f"- Run paused at **{st.status.value}** in `{st.current_step}`: {pause.get('detail')}.")
        for g in pause.get("gaps", [])[:5]:
            say(f"  - {g['analysis']}: {g['detail']}")
        sus = [f for f in ctx.repo.list_findings(rec.run_id) if f.finding_type.value == "suspicious_content"]
        say(f"- {len(sus)} suspicious-content findings recorded (prompt-injection text treated as data, not followed).")

    # 4. injected branch failure ---------------------------------------------------------------------------------
    say("")
    say("## 4. Injected failure the run survives: pricing diagnostic fails for Cedar Field Analytics")
    with scope("cedar-churn"), faults.inject(branch="pricing", fault=faults.Fault("error", times=99)):
        rec, _ = primary.start(ctx, "cedar-churn", "human:demo-analyst", idempotency_key="demo-cedar-1")
        st = anyio.run(lambda: primary.execute(ctx, rec.run_id, backoff_s=0))
        levers = sorted({o.lever.value for o in ctx.repo.list_opportunities(rec.run_id)})
    say(f"- Run reached **{st.status.value}** with levers {levers}; recorded gap: {st.errors[0]}.")

    # 5. fail cleanly then resume ----------------------------------------------------------------------------------
    say("")
    say("## 5. Injected failure that fails cleanly, then resumes")
    with scope("cedar-churn"):
        with faults.inject(step="value_modeling", fault=faults.Fault("error", times=1)):
            rec, _ = primary.start(ctx, "cedar-churn", "human:demo-analyst", idempotency_key="demo-cedar-2")
            st = anyio.run(lambda: primary.execute(ctx, rec.run_id, backoff_s=0))
        say(f"- First attempt: **{st.status.value}** at `{st.current_step}` ({st.errors[-1][:80]}).")
        st = anyio.run(lambda: primary.resume(ctx, rec.run_id, "human:demo-operator", reason="fault cleared"))
        say(f"- After `pvc resume`: **{st.status.value}**; completed steps were not re-executed.")
        events = ctx.repo.list_audit(run_id=rec.run_id)
    say(
        f"- Audit trail for this run: {len(events)} events, e.g. {', '.join(sorted({e.event_type for e in events})[:6])}."
    )

    ok = st.status == Status.AWAITING_APPROVAL
    path = report_path or Path("var/demo-report.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    if verbose:
        print(f"\nReport written to {path}")
    return 0 if ok else 1
