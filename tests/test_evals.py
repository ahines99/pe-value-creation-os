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


def test_value_ranges_fail_when_sizing_drifts():
    obs = {
        "opportunities": [{"lever": "pricing", "metric": "legacy_price_book_arr", "params": {}, "base_ebitda": 120.0}],
        "plan_total_base": 120.0,
    }
    ok = harness._check(
        {"value_ranges": {"legacy_price_book_arr": [100, 150]}, "plan_total_range": [100, 150]}, obs, None, None
    )
    drift = harness._check(
        {"value_ranges": {"legacy_price_book_arr": [0, 50]}, "plan_total_range": [0, 50]}, obs, None, None
    )
    assert all(c["ok"] for c in ok) and not any(c["ok"] for c in drift)
    golden = [c for c in harness.load_suite("golden") if "value_ranges" in c["expect"]]
    assert len(golden) >= 25  # PVC-081: cases carry expected value ranges


def test_model_scores_and_gate():
    cases = {"G1": {"expect": {"levers_include": ["pricing", "retention"]}}}
    base = {
        "case": "G1",
        "opportunities": [{"lever": "pricing"}],
        "accepted": 3,
        "rejected": [{"reason": "overlap: x"}],
        "model_cost_usd": 0.3,
        "evidence_fidelity": True,
        "calculation_fidelity": True,
        "permission_fidelity": True,
    }
    ms = harness.model_scores([base], cases)
    assert ms["planted_lever_recall"] == 0.5 and ms["rejection_rate"] == 0.25 and ms["rejection_reasons"] == ["overlap"]
    thresholds = {
        "model": {
            "planted_lever_recall": 0.8,
            "citation_validity": 1.0,
            "max_rejection_rate": 0.3,
            "max_cost_usd_per_run": 2.0,
        }
    }
    assert harness.model_gate(ms, thresholds) == ["model.planted_lever_recall = 0.5 < 0.8"]
    leaky = harness.model_scores([base | {"permission_fidelity": False}], cases)
    assert "model.permission_fidelity = 0.0 < 1.0" in harness.model_gate(leaky, thresholds)
