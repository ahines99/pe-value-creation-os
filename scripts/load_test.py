"""Load test (PVC-143): concurrent workers draining a queue of runs against PostgreSQL.

Queues N runs across the fixture companies, starts W worker threads that each loop `claim_runnable` ->
execute -> release, and checks that every run executes exactly once (no double claims under
FOR UPDATE SKIP LOCKED), then reports throughput and latency percentiles.

    PVC_ADMIN_DATABASE_URL=postgresql://postgres@localhost:54329/postgres python scripts/load_test.py --runs 40 --workers 4
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import statistics
import sys
import tempfile
import threading
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import anyio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from restore_drill import create_test_role, db_url, drop_test_role  # noqa: E402

from pe_value_os import security  # noqa: E402
from pe_value_os.adapters.evidence_store import FileSystemEvidenceStore  # noqa: E402
from pe_value_os.adapters.fixtures import FixtureAdapter  # noqa: E402
from pe_value_os.adapters.postgres import PostgresRepository  # noqa: E402
from pe_value_os.db.migrate import upgrade  # noqa: E402
from pe_value_os.observability import configure_logging  # noqa: E402
from pe_value_os.policy import get_policy  # noqa: E402
from pe_value_os.workflows import primary  # noqa: E402
from pe_value_os.workflows.steps import RunContext  # noqa: E402

COMPANIES = ["acme-healthy", "beacon-pricing", "cedar-churn", "delta-broken"]
STEP_P95_TARGET_S = 5.0


def check_step_latency(durations_s: list[float], target_s: float = STEP_P95_TARGET_S) -> float:
    if not durations_s:
        raise AssertionError("no completed workflow steps recorded")
    ordered = sorted(durations_s)
    import math

    p95 = ordered[math.ceil(len(ordered) * 0.95) - 1]
    assert p95 <= target_s, f"step p95 {p95:.3f}s exceeds {target_s}s"
    return p95


def main() -> int:
    import psycopg

    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=40)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    if args.runs < 2 or args.workers < 1:
        ap.error("--runs must be at least 2 and --workers positive")
    configure_logging(stream=io.StringIO())
    admin = os.environ["PVC_ADMIN_DATABASE_URL"]
    db = f"pvc_load_{uuid.uuid4().hex[:6]}"
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'create database "{db}"')
    tmp = Path(tempfile.mkdtemp())
    role = None
    try:
        role, password = create_test_role(db_url(admin, db))
        upgrade(db_url(admin, db))
        repo = PostgresRepository(
            db_url(admin, db, role, password), FileSystemEvidenceStore(tmp / "ev"), max_size=args.workers + 2
        )
        seed = RunContext(repo=repo, adapter=FixtureAdapter(), policy=get_policy())
        ids = []
        for i in range(args.runs):
            cid = COMPANIES[i % len(COMPANIES)]
            with security.principal_scope(security.system_principal(cid)):
                ids.append(primary.start(seed, cid, "load")[0].run_id)
        executed: list[str] = []
        durations: list[float] = []
        lock = threading.Lock()

        def worker(n: int) -> None:
            while True:
                with security.principal_scope(security.system_principal(*COMPANIES, subject=f"w{n}")):
                    batch = repo.claim_runnable(f"w{n}", limit=1)
                if not batch:
                    return
                rec = batch[0]
                t0 = time.perf_counter()
                with security.principal_scope(security.system_principal(rec.company_id)):
                    fenced = RunContext(
                        repo=repo.fenced_run(rec.run_id, f"w{n}"), adapter=FixtureAdapter(), policy=get_policy()
                    )
                    anyio.run(lambda r=rec.run_id, context=fenced: primary.execute(context, r, backoff_s=0))
                    repo.release_run(rec.run_id, f"w{n}")
                with lock:
                    executed.append(rec.run_id)
                    durations.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        threads = [threading.Thread(target=worker, args=(n,)) for n in range(args.workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wall = time.perf_counter() - t0
        dupes = [r for r, c in Counter(executed).items() if c > 1]
        with security.principal_scope(security.system_principal(*COMPANIES)):
            statuses = Counter(repo.get_run(r).status.value for r in ids)
            step_times = [
                float(e.payload["duration_ms"]) / 1000
                for rid in ids
                for e in repo.list_audit(run_id=rid)
                if e.event_type in {"step_completed", "run_awaiting_approval", "run_needs_evidence"}
                and "duration_ms" in e.payload
            ]
        repo.close()
        assert not dupes, f"runs executed more than once: {dupes}"
        assert sorted(executed) == sorted(ids), "not every run executed"
        assert set(statuses) <= {"awaiting_approval", "needs_evidence", "complete"}, (
            f"unexpected run statuses: {statuses}"
        )
        step_p95 = check_step_latency(step_times)
        q = statistics.quantiles(durations, n=20)
        line = (
            f"| {datetime.now(UTC):%Y-%m-%d %H:%M} UTC | local PostgreSQL 18, {args.workers} workers | {args.runs} runs "
            f"| {args.runs / wall:.1f} runs/s | p50 {statistics.median(durations):.2f} s, p95 {q[18]:.2f} s "
            f"| no double claims; step p95 {step_p95:.3f} s <= {STEP_P95_TARGET_S:g} s; statuses {dict(statuses)} |"
        )
        log = ROOT / "docs" / "load_test.md"
        if not log.exists():
            log.write_text(
                "# Load test results (PVC-143)\n\nTarget: 4 concurrent workers sustain the automated "
                "workflow with step p95 inside the 5 s SLO and no run executed twice.\n\n| When | Setup | "
                "Load | Throughput | Run latency | Checks |\n|---|---|---|---|---|---|\n",
                encoding="utf-8",
            )
        with log.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        print(line)
        return 0
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(f'drop database if exists "{db}" with (force)')
        if role:
            drop_test_role(admin, role)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
