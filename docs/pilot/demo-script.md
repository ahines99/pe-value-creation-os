# Three-minute demo script (PVC-152)

For technical hiring managers and applied-AI leaders. This storyboard covers an actual browser review and a controlled failure, with the reproducible CLI report as a fallback. Every company is fictional. This is a recording plan, not evidence that a recording or human acceptance session has occurred.

## Before recording

```bash
uv sync --frozen --extra dev
uv run pvc demo --quiet
python scripts/showcase.py up  # Docker Desktop with Linux containers must be running
```

Open `http://localhost:18081/` and sign in before recording using the token printed by setup. Prepare a fresh Beacon run and a Delta run; `python scripts/showcase.py seed` adds another pair without deleting existing evidence. Keep `var/demo-report.md` open in a Markdown preview as the fallback. Use a large font and show only the project window. Do not include the setup terminal, token, settings file or unrelated browser tabs in a recording.

The CLI report and Docker workspace have separate runs. The CLI simulates an approver and records five fixture-derived KPI observations. Browser approval activates KPI definitions; it does not by itself collect observations or establish realized business performance. The default showcase uses deterministic rules, with no paid model call.

## Script

| Time | Screen | Say |
|---|---|---|
| 0:00 to 0:20 | Portfolio homepage, then local workspace | "This project turns fictional operating data into evidence-backed value cases and a human-reviewed plan. This demo uses rules; optional model components propose ideas, while typed tools own facts and calculations." |
| 0:20 to 0:45 | Beacon review; open one evidence link, then return | "Beacon's pricing case traces back to invoices and contracts. The reviewer can inspect the evidence behind an opportunity instead of relying on a plausible summary." |
| 0:45 to 1:15 | Beacon value cases and plan | "The modeled base case is 1,148,309 in annual run-rate EBITDA and 739,200 in-year across three workstreams. These are synthetic opportunities, not realized results. The support idea retains a negative low case: minus 31,020. Sizing is deterministic and versioned." |
| 1:15 to 1:45 | Submit Beacon approval with a rationale; reload workspace; open KPIs | "The draft pauses for a human decision. My approval is recorded, the worker resumes, and KPI definitions activate. Observations require a later monitoring run; approval alone proves no business outcome." |
| 1:45 to 2:15 | Delta review and named evidence gaps | "Delta has missing financial periods, stale invoices and missing contracts. The workflow pauses at needs evidence. Planted instruction text is recorded as suspicious content, not followed." |
| 2:15 to 2:40 | CLI report, sections 2, 4 and 5 | "The repeatable CLI demo separately simulates approval and records fixture-based KPI observations. It also demonstrates refusal of unauthenticated approval, partial diagnostic failure, and recovery without repeating completed steps." |
| 2:40 to 3:00 | Portfolio architecture and linked CI evidence | "The engineering evidence includes 453 tests per supported Python version and 39 deterministic evaluation cases. Company scope and human approval have explicit controls. Real-company deployment still requires domain, security and operational acceptance." |

## Capture and review checklist

Capture these actual application views after inspecting the rendered result. Record the commit, viewport and capture date with the assets; do not label the existing HTML captures as screenshots.

| Asset | Required content | Suggested caption |
|---|---|---|
| Workspace | Beacon and Delta with readable statuses | Two synthetic companies, two different workflow outcomes. |
| Beacon sizing/evidence | Low/base/high values, negative support case and evidence link | Deterministic sizing with inspectable source evidence. |
| Decision and KPIs | Recorded decision, completed run and activated definitions | Human approval resumes execution; definitions are not realized impact. |
| Delta pause | Named missing/stale datasets | Insufficient evidence stops the workflow with actionable gaps. |

Inspect the desktop view and a narrow viewport around 375 pixels wide. Check that navigation, evidence and decision controls remain usable; tables must remain readable or scroll within their container. Use only the keyboard to follow links, enter a rationale and reach the decision button, checking visible focus and logical order. Record actual results and any fixes in [portfolio acceptance](../portfolio/acceptance.md).

If the worker is still processing, wait and reload rather than narrating a completion that is not visible. If browser recording is unavailable, show the [read-only captured review](../portfolio/examples/beacon-pricing.html) and [generated CLI report](../portfolio/demo-report.md), explicitly labeling them as captured/scripted output. This fallback does not close human or rendered-browser acceptance.

## If something goes wrong on camera

- **Non-zero exit or a missing section.** Stop recording and run `uv run pytest -q tests/test_demo.py`. The demo and its test cover the same scenarios.
- **Numbers differ from a previous take.** They shouldn't: fixtures and ids are deterministic. A difference means the policy file or calculator version changed. Check `pvc eval --gate` before re-recording.
