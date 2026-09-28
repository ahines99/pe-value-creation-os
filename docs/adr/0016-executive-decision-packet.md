# ADR 0016: A bound executive decision packet

Status: implemented September 28, 2026. Research-author judgments and constructed
options; no company decision, independent practitioner review or realized result.

The public source appendix, underwriting exercise and capacity proposal were
individually inspectable but did not explain the executive decision among first
waves. The new [decision memo](../portfolio/decision-memo.html) assembles these
layers with a concise thesis, counterarguments, adjustment register, competing
sequences, downside, dated gates and the next evidence request.

## One calculation path, distinct evidence layers

`DecisionBrief` binds the exact public financial, growth, peer, underwriting and
operating-plan model fingerprints. Any input change requires an explicit brief
revision before export. The information cutoff must match the public sources;
this forward proposal must start after that cutoff. Public-source and constructed
case constraints remain enforced by the existing models and engines. All input
contracts validate before the exporter creates either output file.

The memo calls `analyze_facts`, `analyze_growth`, `analyze_peers` and `evaluate_plan`.
It does not implement new earnings, cash, valuation or scheduling arithmetic.
The reported company baseline and assumed incremental operating scenarios remain
separate objects and visibly separate sections. There is no combined hypothetical
Progress forecast, normalized-EBITDA value, equity valuation or realized-value total.

Thesis points reference registered public facts, source documents, growth evidence,
research assessments or the bound peer context. These references establish lineage,
not independent proof of the author's interpretation. Counterarguments and the
next evidentiary test are mandatory fields.

## Adjustment and maintainability register

The eight-entry initial register retains stock compensation, restructuring,
acquisition expense and cyber-response cost; no new accounting addback is accepted.
It identifies acquired-intangible amortization and debt amortization as already
covered by the defined bridge, preventing a second suggested addback. An
already-in-bridge disposition must refer to a supported component of an available
earnings bridge. The two earlier-year amortization scope exceptions must correspond
to actual reconciliation mismatches, rather than unsupported exception labels.

Register rows carry original fact IDs, periods, reported amounts, source-page links,
the author's treatment rationale and the evidence needed for further review.
The FY2025 EBITDA bridge displays source precision. Earlier-year dependent EBITDA
remains withheld where definitions are unresolved. No expense label establishes
maintainability or avoidable cash spending, and this register is not a financial
attestation. Independent review and any future normalized earnings bridge remain
outstanding.

## Comparable operating choices

Three authored alternatives prioritize collections, pricing or service work after
the common foundation. Each retains the exact original task set, resource budgets,
dependencies, economic assumptions, spending commitments and earliest economic
dates. Only scheduling priority, its rationale and the option's revision ID change.
Every alternative passes through the same full capacity and dependency checks,
then the same schedule-linked monthly financial engine. A ready task cannot move
a contract's assumed effective date forward.

The service-first alternative restores sixteen days of the base service benefit:
18,000 per month × 16 / 31 = 9,290.32 additional year-one EBITDA relative to the
current collections-first proposal. Its base year-one incremental EBITDA is
228,266.97 and cash proxy 179,461.97, in assumed USD. This is a comparison of authored
cases, not an optimizer or a recommendation to deploy automation at Progress.

The adverse scenario remains negative: year-one EBITDA −327,840 and a maximum
24-month modeled funding need of 583,630. Day-100 base cash includes 180,000 of
temporary receivables acceleration, which reverses on the original payment date
and adds no EBITDA. The memo exposes this distinction rather than presenting early
cash as a recurring benefit.

The recorded preference is conditional on vendor cost-action evidence and quality
validation. Missing capacity blocks the relevant tasks, suppresses benefits with
committed costs retained and changes the memo status to `reopen_blocked_preference`.
Neither a feasible schedule nor the author's preference creates an approved case
revision or an accepted deliverable. Existing immutable revision history remains
an independently labeled walkthrough.

## Replay and verification

The current replay uses brief schema 2 and packet version 2, adding exact balance
and valuation bindings under [ADR 0017](0017-historical-equity-bridge.md). The
original packet version 1 described above remains part of repository history.

```sh
uv run pvc decision-memo --brief data/constructed/progress/decision-brief.json --facts data/public/progress/financial-facts.json --growth data/public/progress/growth-context.json --peers data/public/progress/peer-context.json --underwriting data/constructed/progress/underwriting.json --operating-plan data/constructed/progress/operating-plan.json --balances data/public/progress/balance-facts.json --valuation data/constructed/progress/historical-valuation.json --output docs/portfolio/decision-memo
```

The HTML links to its complete JSON companion, source appendix, original plan and
underwriting. The JSON retains all option schedules, source facts, monthly outputs,
assumptions and calculation fingerprints. Inputs cannot be overwritten by either
output. No model call, live database migration or vendor account is required.

Tests include independently worked sequence economics, earnings-to-cash identities,
retained spending, adverse scenarios, stale bindings, invalid evidence, unsafe
adjustment labels, private sources, blocked capacity, authority boundaries, escaping
and input preservation. Installed-package smoke invokes the new command. Browser
checks cover desktop, tablet and phone, keyboard navigation, disclosure expansion,
overflow, the conditional preference and the JSON's non-approval/absent-actuals flags.

This is an executive research packet, not completion of the whole goal. Independent
valuation review, constructed actuals and attribution, reviewed close
designation and a genuinely permissioned operating pilot still require further work.
