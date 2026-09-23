"""PVC-080/083/084: harness runs cases, scores dimensions, and the gate fails below thresholds."""

from pe_value_os.evals import harness


def case(cid):
    return next(c for s in ("golden", "adversarial") for c in harness.load_suite(s) if c["id"] == cid)


def test_suites_meet_minimum_size():
    assert len(harness.load_suite("golden")) >= 25
    assert len(harness.load_suite("adversarial")) >= 6


def test_sample_cases_pass_and_report_dimensions():
    results = [harness.run_case(case(c)) for c in ("G01", "G23", "A02")]
    assert all(r["passed"] for r in results), [c for r in results for c in r["checks"] if not c["ok"]]
    s = harness.score(results, "golden")
    for dim in harness.DIMENSIONS:
        assert s[dim] == 1.0, dim
    assert s["p95_run_ms"] > 0 and "model_cost_usd" in s
    a02 = results[2]
    assert a02["model_tokens"] > 0  # scripted model usage is tracked (PVC-084)
    assert sum(u["tokens"] for u in a02["branch_model_usage"].values()) == a02["model_tokens"]
    assert {"intake", "diagnostics", "value_modeling"} <= set(results[0]["step_ms"])  # per-step latency
    assert set(s["step_p95_ms"]) >= {"intake", "diagnostics"}


def test_gate_detects_regressions():
    scores = {"golden": {"case_pass_rate": 0.9, "tool_correctness": 1.0, "p95_run_ms": 100}}
    th = {"golden": {"case_pass_rate": 1.0, "tool_correctness": 1.0}, "latency": {"p95_run_ms": 50}}
    fails = harness.gate(scores, th)
    assert "golden.case_pass_rate = 0.9 < 1.0" in fails and any("p95_run_ms" in f for f in fails)
    assert harness.gate({"golden": {"case_pass_rate": 1.0, "p95_run_ms": 1}}, th) == []
