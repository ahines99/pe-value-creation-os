"""PVC-150: the seeded demo runs end to end and covers every scenario."""

from __future__ import annotations

from pe_value_os.demo import run_demo


def test_demo_runs_all_scenarios(tmp_path, monkeypatch):
    monkeypatch.setenv("PVC_ENV", "dev")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PVC_DEV_TOKENS", raising=False)  # the demo sets it; monkeypatch restores it afterwards
    report = tmp_path / "demo.md"
    assert run_demo(verbose=False, report_path=report) == 0
    text = report.read_text(encoding="utf-8")
    for heading in (
        "## 1. Success path",
        "## 2. Human approval",
        "## 3. Controlled pause",
        "## 4. Injected failure the run survives",
        "## 5. Injected failure that fails cleanly",
    ):
        assert heading in text
    assert "Unauthenticated approval attempt: HTTP 401" in text
    assert "**awaiting_approval**" in text and "**needs_evidence**" in text and "**failed**" in text
