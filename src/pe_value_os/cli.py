"""`pvc` command-line interface (PVC-045 and operational commands).

pvc fixtures generate            regenerate synthetic fixture companies
pvc db upgrade|downgrade|check   run migrations (PVC_MIGRATION_DATABASE_URL)
pvc db bootstrap-roles           create pvc_migrator / pvc_app / pvc_readonly roles
pvc run --company ID             create and execute a diagnostic run
pvc resume RUN_ID [--accept-gaps] resume a paused or failed run
pvc status RUN_ID                show run status
pvc worker [--once]              background worker (runs, KPI refresh, escalations)
pvc kpi refresh|digest --company KPI monitoring
pvc demo                         seeded end-to-end demo (success, needs-evidence, failure, approval, resume)
pvc eval [--suite S] [--gate]    evaluation harness
pvc recompute --run RUN_ID       recompute value cases after a calculation change (audited)
pvc offboard --company ID --confirm   delete a company's data per retention policy
pvc access-review                access-review report
pvc audit-export --company ID    export audit log as JSON lines
pvc onboard-check --company ID   read-only data readiness report for a new company
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import anyio


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _ctx_and_principal(actor: str | None = None):  # type: ignore[no-untyped-def]
    from .app import adapter_from_env, build_context, operator_principal

    adapter = adapter_from_env()
    principal = operator_principal(adapter)
    return build_context(adapter=adapter, actor=actor or principal.subject), principal


def cmd_fixtures(args: argparse.Namespace) -> int:
    from .fixtures.generator import generate_all

    out = Path(args.out)
    for d in generate_all(out):
        print(f"generated {d}")
    return 0


def cmd_db(args: argparse.Namespace) -> int:
    from .db import migrate

    if args.action == "upgrade":
        migrate.upgrade()
    elif args.action == "downgrade":
        if not args.revision:
            print(
                "Refusing to downgrade without --revision (use --revision base to drop the whole schema)",
                file=sys.stderr,
            )
            return 2
        migrate.downgrade(revision=args.revision)
    elif args.action == "check":
        from .db.migrate_check import main

        return main()
    elif args.action == "bootstrap-roles":
        url = os.environ["PVC_ADMIN_DATABASE_URL"]
        pw = {
            r: os.environ[v]
            for r, v in (
                ("pvc_app", "PVC_APP_DB_PASSWORD"),
                ("pvc_readonly", "PVC_RO_DB_PASSWORD"),
                ("pvc_migrator", "PVC_MIGRATOR_DB_PASSWORD"),
            )
            if os.environ.get(v)
        }
        migrate.bootstrap_roles(url, pw)
        print(f"db bootstrap-roles: ok ({len(pw)} role password(s) set)")
        return 0
    print(f"db {args.action}: ok (revision {migrate.current()})")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from .security import principal_scope
    from .workflows import primary

    ctx, principal = _ctx_and_principal()
    with principal_scope(principal):
        rec, created = primary.start(ctx, args.company, principal.subject, idempotency_key=args.idempotency_key)
        if args.no_execute:
            _print({"run_id": rec.run_id, "created": created, "status": rec.status.value})
            return 0
        with _run_lock(ctx, rec.run_id):
            anyio.run(primary.execute, ctx, rec.run_id)
        _print(primary.status(ctx, rec.run_id))
    return 0


@contextmanager
def _run_lock(ctx: Any, run_id: str) -> Iterator[None]:
    """Hold the same run lock the worker uses, so a CLI execution never overlaps a worker's."""
    import uuid

    holder = f"cli:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4()}"
    if not ctx.repo.acquire_run(run_id, holder):
        raise SystemExit(f"Run {run_id} is being executed by another worker; try again later or check `pvc status`.")
    repo = ctx.repo
    ctx.repo = repo.fenced_run(run_id, holder)
    try:
        yield
    finally:
        ctx.repo = repo
        repo.release_run(run_id, holder)


def cmd_resume(args: argparse.Namespace) -> int:
    from .security import principal_scope
    from .workflows import primary

    ctx, principal = _ctx_and_principal()
    if args.refresh_inputs:
        if not (args.reason or "").strip():
            raise SystemExit("--refresh-inputs requires --reason")
        with principal_scope(principal):
            fresh = primary.refresh_inputs(ctx, args.run_id, principal.subject, reason=args.reason)
            _print({**primary.status(ctx, fresh.run_id), "supersedes_run_id": args.run_id})
        return 0
    with principal_scope(principal), _run_lock(ctx, args.run_id):
        anyio.run(
            lambda: primary.resume(
                ctx, args.run_id, principal.subject, accept_gaps=args.accept_gaps, reason=args.reason
            )
        )
        _print(primary.status(ctx, args.run_id))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from .security import principal_scope
    from .workflows import primary

    ctx, principal = _ctx_and_principal()
    with principal_scope(principal):
        _print(primary.status(ctx, args.run_id))
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    from .app import adapter_from_env, build_context, companies_from_env
    from .observability import configure_telemetry
    from .worker import Worker

    configure_telemetry("pvc-worker")
    adapter = adapter_from_env()
    w = Worker(build_context(adapter=adapter), companies_from_env("PVC_WORKER_COMPANIES", adapter))
    if args.once:
        _print(anyio.run(w.tick).__dict__)
        return 0
    anyio.run(w.forever, args.interval)
    return 0


def cmd_kpi(args: argparse.Namespace) -> int:
    from . import kpi
    from .notify import notifier_from_env
    from .security import principal_scope

    ctx, principal = _ctx_and_principal()
    with principal_scope(principal):
        if args.action == "refresh":
            obs = kpi.refresh_company(ctx.repo, ctx.adapter, args.company, ctx.policy, force=args.force)
            _print([o.model_dump(mode="json") for o in obs])
        else:
            n = notifier_from_env()
            d = kpi.build_digest(ctx.repo, args.company, channel=n.channel)
            if d:
                n.deliver(ctx.repo, d)
            _print(d.model_dump(mode="json") if d else {"message": "all KPIs on track"})
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from .demo import run_demo

    return int(run_demo(verbose=not args.quiet))


def cmd_eval(args: argparse.Namespace) -> int:
    from .evals.harness import main as eval_main

    return int(
        eval_main(suite=args.suite, gate=args.gate, report=args.report, proposer=args.proposer, cases=args.cases)
    )


def cmd_recompute(args: argparse.Namespace) -> int:
    from .ops import recompute_run
    from .security import principal_scope

    ctx, principal = _ctx_and_principal()
    with principal_scope(principal):
        _print(recompute_run(ctx, args.run, principal.subject, reason=args.reason))
    return 0


def cmd_offboard(args: argparse.Namespace) -> int:
    from .ops import offboard_company
    from .security import principal_scope

    if not args.confirm:
        print("Refusing to delete without --confirm", file=sys.stderr)
        return 2
    ctx, principal = _ctx_and_principal()
    with principal_scope(principal):
        _print(offboard_company(ctx, args.company, principal.subject))
    return 0


def cmd_access_review(args: argparse.Namespace) -> int:
    from .ops import access_review

    _print(access_review(Path(args.grants) if args.grants else None))
    return 0


def cmd_audit_export(args: argparse.Namespace) -> int:
    from .ops import export_audit
    from .security import principal_scope

    ctx, principal = _ctx_and_principal()
    with principal_scope(principal):
        n = export_audit(ctx, args.company, Path(args.out))
    print(f"exported {n} events to {args.out}")
    return 0


def cmd_onboard_check(args: argparse.Namespace) -> int:
    from .app import adapter_from_env
    from .ops import onboarding_check
    from .policy import get_policy

    report = onboarding_check(adapter_from_env(), args.company, get_policy())
    _print(report)
    return 0 if report["ready"] else 2


def cmd_mcp_stdio(args: argparse.Namespace) -> int:
    """Serve the MCP server over stdio for local clients (Claude Code plugin, PVC-076). Dev scope only."""
    from .mcp_server import mcp

    anyio.run(mcp.run_stdio_async)
    return 0


def cmd_research_pilot(args: argparse.Namespace) -> int:
    from .research.pilot import build_report

    try:
        result = build_report(Path(args.input), args.name)
    except (ValueError, OSError) as exc:
        # Validation errors can contain licensed input values; keep the console minimal.
        print(
            f"Research pilot failed ({type(exc).__name__}); check input schema and private output name.",
            file=sys.stderr,
        )
        return 2
    print(f"Private research memo: {result}")
    return 0


def cmd_public_diligence(args: argparse.Namespace) -> int:
    from .diligence.render import build_public_report

    try:
        result = build_public_report(
            Path(args.input),
            Path(args.output),
            Path(args.growth) if args.growth else None,
            Path(args.peers) if args.peers else None,
        )
    except (ValueError, OSError) as exc:
        print(
            f"Public diligence failed ({type(exc).__name__}); inspect source classification and fact contracts.",
            file=sys.stderr,
        )
        return 2
    print(f"Public financial baseline: {result}")
    return 0


def cmd_underwriting(args: argparse.Namespace) -> int:
    from .diligence.underwriting_render import build_underwriting_report

    try:
        result = build_underwriting_report(Path(args.input), Path(args.output), frozenset(args.exclude))
    except (ValueError, OSError) as exc:
        print(
            f"Underwriting failed ({type(exc).__name__}); inspect model contracts and source policy.", file=sys.stderr
        )
        return 2
    print(f"Constructed underwriting report: {result}")
    return 0


def cmd_operating_plan(args: argparse.Namespace) -> int:
    from .diligence.scheduling_render import build_operating_report

    try:
        result = build_operating_report(Path(args.input), Path(args.underwriting), Path(args.output))
    except (ValueError, OSError) as exc:
        print(
            f"Operating plan failed ({type(exc).__name__}); inspect capacity, dependencies and exact-case binding.",
            file=sys.stderr,
        )
        return 2
    print(f"Constructed operating plan: {result}")
    return 0


def cmd_case_history_demo(args: argparse.Namespace) -> int:
    from .diligence.case_render import build_case_demo

    try:
        result = build_case_demo(Path(args.underwriting), Path(args.operating_plan), Path(args.output))
    except (ValueError, OSError) as exc:
        print(
            f"Case-history replay failed ({type(exc).__name__}); inspect source contracts and exact-case binding.",
            file=sys.stderr,
        )
        return 2
    print(f"Constructed case history (simulated reviews): {result}")
    return 0


def cmd_decision_memo(args: argparse.Namespace) -> int:
    from .diligence.memo_render import build_decision_memo

    try:
        result = build_decision_memo(
            Path(args.brief),
            Path(args.facts),
            Path(args.growth),
            Path(args.peers),
            Path(args.underwriting),
            Path(args.operating_plan),
            Path(args.balances),
            Path(args.valuation),
            Path(args.output),
        )
    except (ValueError, OSError) as exc:
        print(
            f"Decision memo failed ({type(exc).__name__}); inspect exact-input bindings and source contracts.",
            file=sys.stderr,
        )
        return 2
    print(f"Executive decision memo (public research / constructed alternatives): {result}")
    return 0


def cmd_historical_valuation(args: argparse.Namespace) -> int:
    from .diligence.valuation_render import build_valuation_report

    try:
        result = build_valuation_report(Path(args.facts), Path(args.balances), Path(args.spec), Path(args.output))
    except (ValueError, OSError) as exc:
        print(
            f"Historical valuation failed ({type(exc).__name__}); inspect source and assumption contracts.",
            file=sys.stderr,
        )
        return 2
    print(f"Historical company EV-to-equity sensitivity: {result}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pvc", description="PE Value Creation OS")
    sub = p.add_subparsers(dest="command", required=True)

    memo = sub.add_parser(
        "decision-memo", help="assemble a version-bound public research memo with constructed sequencing choices"
    )
    for flag in ("brief", "facts", "growth", "peers", "underwriting", "operating-plan", "balances", "valuation"):
        memo.add_argument(f"--{flag}", required=True)
    memo.add_argument("--output", default="var/executive-memo/decision-memo")
    memo.set_defaults(fn=cmd_decision_memo)

    valuation = sub.add_parser("historical-valuation", help="reconcile a dated public company EV-to-equity sensitivity")
    for flag in ("facts", "balances", "spec"):
        valuation.add_argument(f"--{flag}", required=True)
    valuation.add_argument("--output", default="var/equity-bridge/historical-valuation")
    valuation.set_defaults(fn=cmd_historical_valuation)

    case_demo = sub.add_parser(
        "case-history-demo", help="replay constructed revisions and simulated review receipts in isolated memory"
    )
    case_demo.add_argument("--underwriting", required=True)
    case_demo.add_argument("--operating-plan", required=True)
    case_demo.add_argument("--output", default="var/case-history/report")
    case_demo.set_defaults(fn=cmd_case_history_demo)

    operating = sub.add_parser("operating-plan", help="schedule a constructed 100-day plan and recalculate economics")
    operating.add_argument("--input", required=True, help="typed proposed operating plan JSON")
    operating.add_argument("--underwriting", required=True, help="exact underwriting case bound by the plan")
    operating.add_argument("--output", default="var/operating-plan/report", help="output stem for HTML and JSON")
    operating.set_defaults(fn=cmd_operating_plan)

    underwriting = sub.add_parser("underwriting", help="evaluate a constructed monthly EBITDA/cash/valuation exercise")
    underwriting.add_argument("--input", required=True, help="typed constructed operating case JSON")
    underwriting.add_argument("--output", default="var/underwriting/report", help="output stem for HTML and JSON")
    underwriting.add_argument(
        "--exclude", action="append", default=[], help="exclude an initiative; retain committed costs"
    )
    underwriting.set_defaults(fn=cmd_underwriting)

    public = sub.add_parser("public-diligence", help="reconcile public filing facts and render a sourced baseline")
    public.add_argument("--input", required=True, help="public fact bundle JSON (private sources rejected)")
    public.add_argument(
        "--growth", help="optional exact-bundle-bound acquisition, revenue mix and research context JSON"
    )
    public.add_argument("--peers", help="optional exact-bundle-bound metric-specific public peer context JSON")
    public.add_argument("--output", default="var/public-diligence/baseline", help="output stem for HTML and JSON")
    public.set_defaults(fn=cmd_public_diligence)

    pilot = sub.add_parser("research-pilot", help="build a private public-company research memo")
    pilot.add_argument("--input", required=True, help="normalized financial-statement bundle JSON")
    pilot.add_argument("--name", default="pilot", help="output name within var/research-pilot")
    pilot.set_defaults(fn=cmd_research_pilot)

    f = sub.add_parser("fixtures")
    f.add_argument("action", choices=["generate"])
    f.add_argument("--out", default="tests/fixtures/companies")
    f.set_defaults(fn=cmd_fixtures)

    d = sub.add_parser("db")
    d.add_argument("action", choices=["upgrade", "downgrade", "check", "bootstrap-roles"])
    d.add_argument("--revision")
    d.set_defaults(fn=cmd_db)

    r = sub.add_parser("run")
    r.add_argument("--company", required=True)
    r.add_argument("--idempotency-key")
    r.add_argument("--no-execute", action="store_true", help="queue for the worker instead of running now")
    r.set_defaults(fn=cmd_run)

    rs = sub.add_parser("resume")
    rs.add_argument("run_id")
    rs.add_argument(
        "--refresh-inputs",
        action="store_true",
        help="queue a new linked run using fresh data and policy (requires --reason)",
    )
    rs.add_argument("--accept-gaps", action="store_true", help="human decision to proceed despite data gaps")
    rs.add_argument("--reason")
    rs.set_defaults(fn=cmd_resume)

    st = sub.add_parser("status")
    st.add_argument("run_id")
    st.set_defaults(fn=cmd_status)

    w = sub.add_parser("worker")
    w.add_argument("--once", action="store_true")
    w.add_argument("--interval", type=float, default=30.0)
    w.set_defaults(fn=cmd_worker)

    k = sub.add_parser("kpi")
    k.add_argument("action", choices=["refresh", "digest"])
    k.add_argument("--company", required=True)
    k.add_argument("--force", action="store_true")
    k.set_defaults(fn=cmd_kpi)

    dm = sub.add_parser("demo")
    dm.add_argument("--quiet", action="store_true")
    dm.set_defaults(fn=cmd_demo)

    e = sub.add_parser("eval")
    e.add_argument("--suite", default="all", choices=["all", "golden", "adversarial"])
    e.add_argument("--gate", action="store_true", help="exit non-zero when scores fall below thresholds")
    e.add_argument("--report", default="var/eval-report.json")
    e.add_argument("--cases", help="comma-separated case ids to run (default: every case in the suites)")
    e.add_argument(
        "--proposer",
        default="rules",
        choices=["rules", "model"],
        help="model requires ANTHROPIC_API_KEY (live evaluation; not used by the CI gate)",
    )
    e.set_defaults(fn=cmd_eval)

    rc = sub.add_parser("recompute")
    rc.add_argument("--run", required=True)
    rc.add_argument("--reason", required=True)
    rc.set_defaults(fn=cmd_recompute)

    ob = sub.add_parser("offboard")
    ob.add_argument("--company", required=True)
    ob.add_argument("--confirm", action="store_true")
    ob.set_defaults(fn=cmd_offboard)

    ar = sub.add_parser("access-review")
    ar.add_argument("--grants", help="JSON file of principal grants exported from the identity provider")
    ar.set_defaults(fn=cmd_access_review)

    ae = sub.add_parser("audit-export")
    ae.add_argument("--company", required=True)
    ae.add_argument("--out", required=True)
    ae.set_defaults(fn=cmd_audit_export)

    oc = sub.add_parser("onboard-check", help="read-only data readiness report for a new company")
    oc.add_argument("--company", required=True)
    oc.set_defaults(fn=cmd_onboard_check)

    ms = sub.add_parser("mcp-stdio", help="serve MCP over stdio for local clients")
    ms.set_defaults(fn=cmd_mcp_stdio)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
