# Review a choice without counting the same benefit twice

Start with the [allocation review](allocation-review.html), then inspect its
[executive memo](allocation-memo.html). This is a separate constructed exercise
using Progress as the public research reference; it does not change the historical
ten-revision initiative-lineage demonstration.

1. Two pricing candidates share one reference population, initially assigned 60%
   and 40%. Inspect the original [underwriting](allocation-underwriting.html).
2. Both packages cannot fit the original capacity budgets. The
   [first-wave proposal](allocation-operating-plan.html) defers the 40% alternative;
   its share remains unused rather than inflating the selected candidate.
3. The modeled close freezes that selection. Constructed accounting and claims are
   recorded against it. They are method examples, not observed company results.
4. Exact contracts, vendor/service records and invoices constrain the forecast.
   A subsequent policy revision selects one mutually exclusive pricing alternative
   on the eligible full cohort. It does not transfer the earlier candidate's claims.
5. Removing unsupported vendor release evidence leaves the current forecast at
   **-163,165 year-one EBITDA** and **-181,890 pre-tax cash**. The
   [source exhibit](allocation-sources.html) shows the constraints. The memo keeps
   this adverse result and calls for reworking the first wave.

All six revisions, exact source assignments, simulated reviews, frozen observations
and financial claims are in the [download](allocation-review.json). Actual company
impact and financial attribution inferred from population shares remain unavailable.

## Reproduce locally

Run from the repository root with the development environment installed:

```powershell
uv run python scripts/build_allocation_example.py
uv run pvc allocation-demo --underwriting data/constructed/progress/allocation-underwriting.json --operating-plan data/constructed/progress/allocation-plan.json --exercise data/constructed/progress/allocation-realization.json --sources data/constructed/progress/allocation-sources.json --output docs/portfolio/allocation-review
uv run pvc underwriting --input data/constructed/progress/allocation-underwriting.json --output docs/portfolio/allocation-underwriting
uv run pvc operating-plan --input data/constructed/progress/allocation-plan.json --underwriting data/constructed/progress/allocation-underwriting.json --output docs/portfolio/allocation-operating-plan
uv run pvc decision-memo --brief data/constructed/progress/allocation-brief.json --facts data/public/progress/financial-facts.json --growth data/public/progress/growth-context.json --peers data/public/progress/peer-context.json --underwriting data/constructed/progress/allocation-underwriting.json --operating-plan data/constructed/progress/allocation-plan.json --balances data/public/progress/balance-facts.json --valuation data/constructed/progress/historical-valuation.json --output docs/portfolio/allocation-memo --case-review docs/portfolio/allocation-review.json
uv run python scripts/check_allocation_review.py
```

Replays create new IDs and recording timestamps; financial results and source
rules reproduce. No model, vendor credentials or live company service is required.

The underlying contracts and limitations are in [ADR 0027](../adr/0027-benefit-pool-allocation.md).
