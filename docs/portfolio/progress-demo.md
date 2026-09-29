# A 10-minute evidence-to-decision walkthrough

**Presenter guide · public research and constructed exercise · no practitioner session recorded**

Start at the [portfolio entry point](../index.html), then follow its six-stop
route. The decision is whether the proposed first wave merits further work after
the evidence changes. No login, model key or vendor account is needed to inspect
these pages. The separate fictional Beacon application has its own
[local quickstart](quickstart.md).

## Follow the primary case

| Time | Open | Explain and challenge | Evidence to leave visible |
|---|---|---|---|
| 0:00–1:00 | [Executive memo](decision-memo.html) | State the current decision: rework the constructed first wave; obtain evidence before a company-specific commitment. | Reopened preference, adverse alternatives and no operating authorization |
| 1:00–3:00 | [Public baseline](progress-baseline.html) | Trace the FY2025 $304.202m calculated EBITDA bridge. Explain why it is not normalized earnings and why peer gaps are not savings. | Filing rows, retained expenses, unresolved amortization scope and strict peer medians withheld |
| 3:00–4:00 | [Underwriting](underwriting.html) | Show the original constructed mechanism and distinguish earnings, cash timing, implementation spending and value assumptions. | Monthly schedules and downside; fictional uplift is never added to company earnings |
| 4:00–5:00 | [100-day proposal](operating-plan.html) | Identify a resource conflict and explain the delay. Capacity is assumed, not a commitment by Progress management. | Seven packages, four budgets, dependencies and dates tied to the same economics |
| 5:00–7:00 | [Source review](source-review.html), then [memo choices](decision-memo.html#choices) | Trace contract/service/invoice constraints and removal of unsupported vendor release. Ask why a different sequence cannot repair the case. | Base first-year EBITDA −$163,165 and pre-tax cash −$181,890; prior versions and the hypothetical close remain intact |
| 7:00–9:00 | [Ten-revision lifecycle](lineage-review.html) | Compare the same five recorded periods. Inspect a corrected KPI target/read and a claim whose supporting evidence was withdrawn. | $61k EBITDA difference = $18k claims + $43k residual; $185k cash = $166k claims + $19k residual; all constructed |
| 9:00–10:00 | [Sponsor brief](../pilot/permissioned/sponsor-brief.md) | State the next bounded data request and who must authorize it. Invite stop, revise or further diligence. | One company, one lever, named finance/operating reviewers; no sponsor or performed pilot yet |

Public-company facts, first-year forecasts and five-period accounting observations
have different scopes. Do not add successive revisions, compare a partial period
with a full-year forecast, or describe a claim as proven causal impact. HTML rounds
some figures; downloadable JSON preserves Decimal amounts.

## Keep deeper exhibits available

- **Earnings definitions:** the [financial review](../research/operating-partner/08-financial-definition-review.md)
  explains all four source-period exceptions and the derived-quarter limitation.
- **Company valuation:** the [historical equity bridge](historical-valuation.html)
  uses November 30, 2025 balances and explicit author assumptions. It is not current value.
- **Exit sensitivity:** the [exit review](exit-review.html) separates earnings,
  multiple and interaction effects; actual proceeds remain unavailable.
- **Historical information:** [acquisition disclosures](disclosure-history.html)
  and [accounting restatement](accounting-restatement.html) are different events.
  The latter preserves a non-reliance interval. Exact public-availability timing
  remains unverified and blocks a point-in-time availability claim.
- **Shared benefits:** the [twelve-revision allocation example](allocation-lineage-review.html)
  and its [own memo](allocation-lineage-memo.html) demonstrate shared-population
  selection, splits, corrections and recombination. This is a separate exercise;
  do not splice its figures into the ten-revision primary case.
- **Interactive human approval:** use the [Beacon quickstart](quickstart.md).
  Progress research receipts are simulated; they are not a recorded human review.

## Reproduce before presenting

From a clean checkout with Python 3.12+ and `uv`:

```sh
uv sync --frozen --extra dev
uv run python scripts/check_progress_review.py
uv run python scripts/check_allocation_review.py --include-lineage
```

The checks cover the primary Progress bundle and the separate shared-pool lifecycle.
Receipts under `var/` identify inputs and exact case revisions. Resolve failures
before presenting affected exhibits. The checks use application calculators;
they are not independent finance review.

For a complete rebuild, follow the `pvc` commands in the
[CI workflow](../../.github/workflows/ci.yml), in the artifact-rebuild step's order.
Generate `lineage-review.json` before rebuilding the primary memo with that file
as `--case-review`. Use the allocation lineage file only for its corresponding
memo. Replay IDs and recording times can change; economic/source fingerprints
reproduce, and linked exhibits within one bundle must share the exact revision.

No `.env`, LSEG/WRDS connection or live model is needed. Raw source-PDF verification
is a separate step documented with the public mappings; replay alone does not
independently re-audit the filings.

## Record real feedback when it exists

Use the [practitioner worksheet](practitioner-review.md) to record the actual
reviewed version, objections, responses and unresolved questions. Leave ratings
and endorsements unfilled until a person supplies them. Automated browser checks
do not establish that an executive understood or accepted the analysis.
