# Three-minute demo script (PVC-152)

For PE operating partners, investment professionals and portfolio-company executives, with technical diligence alongside the business case. This storyboard covers an actual browser review and a controlled failure, with the reproducible CLI report as a fallback. Every company is fictional. This is a recording plan, not evidence that a recording or human acceptance session has occurred.

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
| 0:00 to 0:20 | Portfolio landing page, then local portfolio overview | "An operating partner needs a defensible answer to three questions: where is the opportunity, what must be true, and who owns the next action? This workspace connects those questions using fictional portfolio-company data." |
| 0:20 to 0:45 | Beacon investment memo; headline and contribution view | "Beacon's modeled opportunity is 1,148,309 in annual run-rate EBITDA and 739,200 in-year. Pricing execution dominates the case. These are synthetic opportunities, not realized returns." |
| 0:45 to 1:15 | Open a value case, then a cited source in the evidence room | "Every case exposes its assumptions and supporting evidence. Support automation is only 9,552 in the base case and minus 31,020 in the low case. The downside stays visible; deterministic code calculates the amounts." |
| 1:15 to 1:45 | Submit a scoped Beacon decision with a rationale; refresh and open the run-context KPI view | "I decide which scope proceeds. The decision is recorded, the worker resumes, and the approved KPI definitions activate. Targets and seeded observations are distinct; approval alone proves no financial result." |
| 1:45 to 2:10 | Delta evidence pause | "Delta has missing financial periods, stale invoices and incomplete contracts. The process identifies the gaps and pauses. Suspicious source instructions remain data, not operating authority." |
| 2:10 to 2:40 | Architecture and current linked evidence index | "Typed tools own facts and calculations; optional models propose ideas. Human approval has a separate authority boundary. Durable checkpoints, company isolation and artifact-specific checks make the controls inspectable." |
| 2:40 to 3:00 | CLI report or quickstart and acceptance links | "The same repository includes a reproducible five-scenario demonstration and versioned verification evidence. The next step for a real company is source reconciliation, policy and domain review, and operational acceptance." |

If the public landing page is available, use it for the opening and architecture scenes. Use the actual local application for decisions. Captured HTML cannot submit a decision; never splice a static capture into the recording as if it did.

## Capture and review checklist

Capture these actual application views after inspecting the rendered result. Record the commit, viewport and capture date with the assets; do not label the existing HTML captures as screenshots.

| Asset | Required content | Suggested caption |
|---|---|---|
| Portfolio overview | Latest company states, decision queue and readable hierarchy | An operating review organized around the next decision. |
| Investment memo and evidence room | Value contribution, low/base/high assumptions, negative support case and cited source | A value thesis connected to its assumptions and evidence. |
| Decision and run-context KPIs | Recorded decision, completed run, activated definitions and observation state | Human approval resumes execution; targets are not realized returns. |
| Delta pause | Named missing/stale datasets | Insufficient evidence stops the workflow with actionable gaps. |

Inspect desktop (around 1440 pixels), tablet (768 pixels) and narrow mobile (375 pixels) views. Check that navigation, evidence and decision controls remain usable; tables must remain readable or scroll within their container. Use only the keyboard to follow links, enter a rationale and reach the decision button, checking visible focus and logical order. Exercise recoverable form validation on a fresh synthetic run without claiming a rejected submission became a recorded decision. Record actual results and any fixes in [portfolio acceptance](../portfolio/acceptance.md).

If the worker is still processing, wait and reload rather than narrating a completion that is not visible. If browser recording is unavailable, show the [read-only captured review](../portfolio/examples/beacon-pricing.html) and [generated CLI report](../portfolio/demo-report.md), explicitly labeling them as captured/scripted output. This fallback does not close human or rendered-browser acceptance.

## If something goes wrong on camera

- **Non-zero exit or a missing section.** Stop recording and run `uv run pytest -q tests/test_demo.py`. The demo and its test cover the same scenarios.
- **Numbers differ from a previous take.** They shouldn't: fixtures and ids are deterministic. A difference means the policy file or calculator version changed. Check `pvc eval --gate` before re-recording.
