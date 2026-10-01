# Project status

**As of September 30, 2026.** This is the one current status file. The older roadmaps and acceptance registers are kept as detailed records and each points here. If they disagree with this file, this file is right.

## Where the project is

- **The public showcase is shipped.** `main` (PR #52) is published at <https://ahines99.github.io/pe-value-creation-os/>, and every file under `docs/` matches the live site.
- **CI is green on `main`:** ten jobs, 1,781 tests on each of Python 3.12, 3.13 and 3.14, 39 evaluations, and 96 browser checks (84 public pages, 12 private-review pages).
- **Nothing is deployed** beyond the static site. The AWS Terraform and the CD workflow have never run.
- **No company pilot has happened.** The private-pilot workflow has only been exercised on fictional records.
- **"Released" so far means merged to `main` and published.** The only tagged release is `v0.1.0` (September 28). The private-workflow work in PRs #41 to #52 has no tag or version bump yet.

## What is real and what is constructed

| Part | Source |
|---|---|
| Public baseline | Real Progress Software public filings: 241 mapped facts, plus four public peers |
| Operating exercise | Constructed: contracts, vendors, invoices, capacity, KPI readings, realization and exit figures |
| Approval demo companies (Beacon, Cedar, Acme, Delta) | Fictional |

The public pages label this split. Normalized EBITDA, unsupported earnings adjustments and the valuations that depend on them are withheld, not estimated. There is no Progress engagement and no realized savings.

## What is built

- **Core:** deterministic calculation services, a checkpointed workflow, an MCP server with 22 tools, a human approval API, KPI monitoring, source adapters, evals and an optional Claude model layer.
- **Public diligence:** EBITDA reconciliation, quarterly and peer views, restatement comparison, acquisition vintages and a historical valuation bridge.
- **Constructed underwriting:** monthly earnings and cash, capacity scheduling, case revisions with lineage, and a realization and attribution ledger.
- **Permissioned private chain** (16 migrations): processing grants, intake, financial snapshots, underwriting, capacity plans, reviewed baselines, observations, execution, attribution with separate finance review, and an executive review screen.

## Open items

| Item | State | Who |
|---|---|---|
| Practitioner review of the showcase | Packet ready ([brief](portfolio/practitioner-brief.md), [session log](portfolio/practitioner-review.md)); no session held | Owner introduces a reviewer |
| Historical disclosure timing | Original and restated filings are compared. Exact first public availability is unverified, because the current bar rejects SEC acceptance timestamps | Owner decides: accept SEC acceptance time as the stated proxy, or record a permanent limitation |
| Four amortization differences (at most about 2% of the row) | Unexplained; dependent measures stay withheld | Owner decides whether the documented limitation is acceptable for a showcase |
| Delivery-cost reconciliation | Calculator and review contracts exist on branch `feat/private-cost-reconciliation` only; no storage, API or screen | Engineering |
| Remaining private screens and the private decision memo | Only the attribution review screen exists | Engineering |
| Retention and disposal | Whole-company offboarding exists; per-source expiry, legal holds and backup disposal do not | Engineering; the company supplies its policy |
| Real pilot | Not started | Needs a sponsor, authorized records, named finance and operating reviewers, an AWS deployment and elapsed operating time |
| Six Dependabot PRs (#2 to #7) | Open; #3 fails the container scan | Engineering |
| New tagged release | Not cut since `v0.1.0` | Owner decides when |

## Known engineering debts

A September 30 review found the code healthy (lint, types, tests, evals and the demo pass; no arithmetic errors in the financial logic) but out of proportion to its users:

- **Boilerplate.** The same hash-chain pattern is hand-copied across 13 private record types.
- **Duplicated logic.** About 700 lines repeat between the in-memory and PostgreSQL repositories.
- **Packaging.** Demo and HTML-rendering code ships inside the installed package.
- **Repository size.** About 80 MB of generated JSON exhibits is tracked in git.
- **Documentation volume.** It far exceeds the code, and several plans overlap. This file replaces them for status.
- **Review.** Every PR was merged with CI as the only gate; no second person reviewed them.

The review's advice was to consolidate before adding more pilot stages.

One modelling trap from that review is fixed: a cost of kind `recurring` must now be posted for every month through the horizon, so a single row can no longer understate later months.

## Older documents

| Document | What it is now |
|---|---|
| [ROADMAP.md](../ROADMAP.md) | The original 111-ticket production plan, frozen September 27 (78 done, 14 built, 19 blocked) |
| [IMPLEMENTATION_HANDOFF.md](../IMPLEMENTATION_HANDOFF.md) | The original design specification |
| [operating-partner-roadmap.md](operating-partner-roadmap.md) | Research and capability plan (OP-01 to OP-18), with per-PR evidence |
| [portfolio/progress-acceptance.md](portfolio/progress-acceptance.md) | Detailed acceptance evidence for the Progress case |
| [portfolio/remaining-work.md](portfolio/remaining-work.md) | Detailed pilot-preparation checklist |
| [portfolio-finalization-roadmap.md](portfolio-finalization-roadmap.md), [portfolio/acceptance.md](portfolio/acceptance.md), [portfolio/showcase-closeout.md](portfolio/showcase-closeout.md) | History of the `v0.1.0` release |
