# A 10-minute evidence-to-decision walkthrough

**Presenter guide · constructed exercise · no practitioner session recorded**

Use the published pages or serve `docs/` locally. No token, model key or vendor
account is needed for this read-only demonstration. The live Beacon application
has its own [quickstart](quickstart.md) and [historical storyboard](../pilot/demo-script.md).

| Time | Open / show | Say and challenge | Expected evidence |
|---|---|---|---|
| 0:00–1:00 | [Memo](decision-memo.html), headline and evidence update | “Latest evidence makes every tested first wave adverse. This is a public reference case plus constructed operating records.” | Reopened preference; no authorized intervention |
| 1:00–2:00 | [Public baseline](progress-baseline.html), definitions and sources | Trace FY2025 calculated EBITDA of $304.202m. Why is this not normalized EBITDA? | Public components, locators, retained expenses and unresolved accounting differences |
| 2:00–3:00 | [Operating proposal](operating-plan.html), capacity and dates | Identify a delayed package and its resource conflict. | Seven packages, four budgets; proposed rather than actual staffing |
| 3:00–5:00 | [Source review](source-review.html), corrections | Trace 50% capture, source constraints and removal of vendor release. Why does sequencing not repair the case? | Base first-year EBITDA −$163,165 and cash −$181,890; original and frozen close survive |
| 5:00–6:30 | [Exit lifecycle](exit-review.html), history; [execution](execution.html), claims | Compare the same five recorded periods, not a partial period with a full-year forecast. Inspect a claim's withdrawn support. | $61k EBITDA difference = $18k claims + $43k residual; $185k cash = $166k + $19k; all constructed |
| 6:30–8:00 | [Exit matrix and EV bridge](exit-review.html) | Select 0.9x earnings / 6x multiple. Why is the change not entirely operating value? | −$790.9252m EV change: −$243.3616m earnings, −$608.404m multiple, +$60.8404m interaction; no proceeds |
| 8:00–9:00 | [Disclosure history](disclosure-history.html) | Show provisional/final allocations. What was publicly available at a historical instant? | Measurement-period adjustment retained; SEC acceptance does not establish first publication; point-in-time claim withheld |
| 9:00–10:00 | [Pilot brief](../pilot/permissioned/sponsor-brief.md) | State what a sponsor must authorize. Invite stop, revise or further diligence. | One company, one lever, read-only scope; no pilot or promised impact |

HTML rounds some amounts to millions or whole dollars; JSON retains underlying
Decimal amounts. The exit example is an authored sensitivity, not a current
valuation, investment return or recommendation to transact.

## Reproduce the review checks

From a clean checkout with Python 3.12+ and `uv`:

```sh
uv sync --frozen --extra dev
uv run python scripts/check_progress_review.py
```

The check reads only the public and constructed Progress input directories and
linked portfolio artifacts. It does not read `.env`, contact LSEG/WRDS, start
services or use a model. Its receipt at `var/progress-review/checks.json` records
file hashes and the exact case revision. Resolve a failure before presenting the
affected exhibit. This uses the application calculators; it is not independent
finance review or a new source-document audit.

For a full artifact rebuild, follow the `pvc` commands in the repository's
[CI workflow](../../.github/workflows/ci.yml), “Check rendered portfolio across
desktop, tablet and phone widths,” in their listed order. The preceding application
capture steps and Docker browser checks are separate acceptance work. Each domain
command exposes `--help`. Public mappings are checked-in inputs; replay does not
redownload or independently reread the original filings.

Generate `exit-review.json` before rebuilding the memo with `--case-review` set
to that file. Demo IDs and recorded-at times change across runs. Compare source
fingerprints and economics across replays; within a single bundle, the memo and
exit export must share the exact revision hash.

## Respond to challenges

- **“Those are real savings.”** Show classification and the unavailable actual-company result.
- **“Hours freed equal payroll savings.”** Show corrected vendor evidence and zero supported cost release.
- **“Choose a different sequence.”** Open the recomputed alternatives; every tested base first-year result remains adverse.
- **“The multiple creates operating value.”** Separate earnings, multiple and interaction effects; keep proceeds unavailable.
- **“Tests prove commercial validity.”** Show [acceptance limits](progress-acceptance.md) and the [practitioner worksheet](practitioner-review.md).

Do not present simulated receipts as a human approval session. Record actual
questions and disagreement only if a person supplies them; no external score or
endorsement is prefilled.
