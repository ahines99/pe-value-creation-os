# Three-minute demo script (PVC-152)

For whoever records or presents the demo to a deal team or operating partner. The demo covers one success path and one controlled failure. Every company is fictional.

## Before recording

```bash
uv sync --extra dev
uv run pvc demo --quiet        # warm-up run; confirms all five scenarios pass (exit code 0)
```

Open two panes: a terminal, and `var/demo-report.md` in a Markdown preview. Use a large font. Don't show environment variables or tokens.

## Script

| Time | Screen | Say |
|---|---|---|
| 0:00 to 0:20 | README, "Why this is not just a chatbot" | "This turns a portfolio company's operating data into a sized, evidence-backed 100-day plan. The model makes judgment calls. Every number comes from tested code, and a human approves the plan." |
| 0:20 to 0:35 | Terminal: `uv run pvc demo` | "One command runs five scenarios on fictional companies, in process, with no database or API key." |
| 0:35 to 1:15 | Section 1 of the output | "Beacon has a pricing leak. The run found discount governance, unenforced renewal uplifts and legacy price books, plus two smaller levers, and sized each one low, base and high. The AI support idea has a negative low case, and the system shows that instead of hiding it. Each figure cites evidence ids and a calculator version. The run then built a 100-day plan and stopped: nothing proceeds without a human." |
| 1:15 to 1:45 | Section 2 | "An unauthenticated approval is refused with 401. The approver's token works, and the decision and rationale are audited. The worker resumes the run, and KPIs for the plan are now monitored." |
| 1:45 to 2:25 | Section 3 (the controlled failure) | "Delta's data is broken. Instead of guessing, the run pauses at 'needs evidence' and names each gap by dataset. Delta's files also contain planted prompt-injection text. It was recorded as suspicious content and never followed." |
| 2:25 to 2:50 | Sections 4 and 5 | "A failing diagnostic branch becomes a recorded gap, and the other branches still finish. A failed step can be resumed without redoing completed work, and the audit trail shows every step." |
| 2:50 to 3:00 | `docs/architecture.md` diagram | "Company scope is enforced on every call and in the database. No model-callable tool can approve. That is what makes this safe to point at real portfolio data." |

## If something goes wrong on camera

- **Non-zero exit or a missing section.** Stop recording and run `uv run pytest -q tests/test_demo.py`. The demo and its test cover the same scenarios.
- **Numbers differ from a previous take.** They shouldn't: fixtures and ids are deterministic. A difference means the policy file or calculator version changed. Check `pvc eval --gate` before re-recording.
