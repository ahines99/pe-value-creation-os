# ADR 0023: Reopen the executive preference when source evidence changes

Status: accepted for the public research and constructed-exercise memo.

## Decision problem

The original memo conditionally favored service-first sequencing because it
advanced a modeled vendor cost reduction. The subsequent saved source review
removed that reduction and retained all original costs. Leaving the original
preference prominent in the executive memo would contradict its own stated
falsifier, even though a separate case-history page showed the correction.

## Implementation

`pvc decision-memo --case-review <source-review.json>` validates and imports the
constructed case history, then recomputes every registered first-wave sequence
using the latest underwriting, source rows, resources and work packages. Only
priority order and resulting dates vary between alternatives. Source-book plan
hashes are explicitly rebound to those hypothetical schedules. The shared
source forecast owns the financial calculations; the memo adds no new sizing
formula. A signed incremental earnings waterfall reconciles exactly to EBITDA,
and the separate cash bridge retains collection reversals and capex.

The imported context requires the original, a contiguous same-case revision
chain, exact parent/source bindings and simulation receipts for their exact
revision hashes. The memo's original underwriting and plan must appear in that
history. The latest stored financial snapshot is reproduced and compared before
export; changing its outputs and recomputing its envelope hash is insufficient
to substitute a favorable result. Receipt corrections retain actor, revision and
mode. Missing, rejected, withdrawn or change-requested review is displayed as
such, never promoted to acceptance.

These are integrity checks on the supplied export, not cryptographic signatures
or proof that a snapshot contains every subsequent database event. The output
records the full typed context and its hash. It identifies the exact snapshot
being discussed rather than claiming a live latest-case query. Public export
accepts simulation receipts only; actual identity/publication consent belongs
to the later permissioned workflow.

The source-responsive result uses memo version 3. The original decision brief
and conditional options remain intact in a clearly marked historical disclosure;
their positive values do not become the current forecast. The front page reopens
selection and selects no new alternative automatically. Acceptance of the saved
research revision does not approve these recomputed alternatives or authorize
an intervention. Source-bounded operating terms do not establish maintainable
exit value, so the revised financial scenarios withhold incremental valuation.
The independently sourced historical company equity sensitivity stays separate.

Without `--case-review`, the legacy original-assumption memo remains available.
Published portfolio and installed-package CI commands include the context and
generate the source-review export first. Exercise effective dates are disclosed
separately from the public-filing cutoff; the re-estimate is not a historical
point-in-time backtest or actuals-plus-remaining forecast.

## Acceptance

The current corrected case must reopen the preference; all tested sequences
retain costs and show nonpositive base year-one EBITDA. Original public facts,
historical equity assumptions and original options remain unchanged. Tests reject
broken histories, mismatched receipts, human-review relabeling, wrong original
inputs, overwritten source files and rehashed output tampering. The waterfall
must reconcile exactly, including negative values. CI and browser checks verify
that the evidence update appears before the public thesis and the original
preference is identified as reopened on desktop and narrow screens.

This resolves executive consistency, not the full five-outcome goal. Broader
source/perimeter diligence, independent challenge, explicit exit/learning scope,
final acceptance and the real permissioned pilot remain separately tracked.
