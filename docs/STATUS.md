# Project status

**As of September 30, 2026, release `v0.2.0`.** This is the one current status file. The older roadmaps and acceptance registers are kept as detailed records and each points here. If they disagree with this file, this file is right.

## Where the project is

- **Implementation is complete for the portfolio scope.** Everything the repository can do without outside parties is merged, tested and released as [`v0.2.0`](https://github.com/ahines99/pe-value-creation-os/releases/tag/v0.2.0). What remains needs a reviewer, a pilot company or production owners (see [Open items](#open-items)).
- **The public showcase is published** at <https://ahines99.github.io/pe-value-creation-os/> from `main:/docs`.
- **CI:** ten required jobs: the test suite on each of Python 3.12, 3.13 and 3.14 (1,798 tests), 39 evaluations, and 96 browser checks (84 public pages, 12 private-review pages), plus the dependency audit, secret scan and container scan. A nightly workflow re-runs the evaluations and the dependency audit on `main`.
- **Repository protection:** `main` requires all ten checks, strict and enforced for admins. Dependabot alerts and security updates, secret scanning and push protection are on; merged branches are deleted automatically.
- **Nothing is deployed** beyond the static site, by decision. The AWS Terraform is validated in CI but has not been applied; the CD workflow triggers and its jobs are skipped because no deployment is configured.
- **No company pilot has happened.** The private-pilot workflow has only been exercised on fictional records.

## What is real and what is constructed

| Part | Source |
|---|---|
| Public baseline | Real Progress Software public filings: 241 mapped facts, plus four public peers |
| Operating exercise | Constructed: contracts, vendors, invoices, capacity, KPI readings, realization and exit figures |
| Approval demo companies (Beacon, Cedar, Acme, Delta) | Fictional |
| Private WRDS/LSEG research study | Licensed data, produced September 27 to 28, kept only in the gitignored `var/research-pilot/` folder. By decision, licensed figures are never published, only the method; LSEG is excluded for lack of fiscal-period, currency and unit metadata, and Compustat is the sole licensed source. The university licence is non-commercial |

The public pages label this split. Normalized EBITDA, unsupported earnings adjustments and the valuations that depend on them are withheld, not estimated. There is no Progress engagement and no realized savings.

## What is built

- **Interface:** one design system for the app, exhibits and landing page ([design-system.md](design-system.md)).
- **Core:** deterministic calculation services, a checkpointed workflow, an MCP server with 22 tools, a human approval API and browser workspace, KPI monitoring, source adapters, evals and an optional Claude model layer.
- **Public diligence:** EBITDA reconciliation, quarterly and peer views, restatement comparison, acquisition vintages and a historical valuation bridge.
- **Constructed underwriting:** monthly earnings and cash, capacity scheduling, case revisions with lineage, and a realization and attribution ledger.
- **Permissioned private chain** (migrations 0008 to 0016 of 16): processing grants, intake, financial snapshots, underwriting, capacity plans, reviewed baselines, observations, execution, attribution with separate finance review, and an executive review screen.

## Decisions recorded September 30

| Decision | Outcome |
|---|---|
| Historical disclosure timing | Permanent limitation: exact first public availability stays unverified, and the showcase says so rather than using SEC acceptance time as a proxy. Closes acceptance step 5 and OP-16 at showcase scope |
| Four amortization differences (at most about 2% of the row) | Documented limitation accepted; dependent measures stay withheld |
| AWS deployment (PVC-093, 094, 103, 131, 132, 133, 135, 136, 142, 143) | Won't do for the portfolio scope; Terraform and tests stay as built |
| Licensed benchmark data (PVC-116) | Won't do; public-filing peers replaced it |
| Research data | Never published; method only; LSEG excluded |
| Delivery-cost reconciliation, remaining private screens, per-source retention and disposal | Parked until a pilot sponsor exists. The cost-reconciliation work is kept on branch `feat/private-cost-reconciliation` |
| Demo code inside the package, about 80 MB of generated exhibits in git | Accepted. Pages serves `main:/docs` directly; moving exhibits to a build step would add machinery without changing what reviewers see |

## Roadmap

[ROADMAP.md](../ROADMAP.md) keeps the original 111 tickets: **84 done, 11 won't do, 1 built, 15 blocked.** The 16 still open are not engineering work:

| Tickets | Needs |
|---|---|
| PVC-070 | The owner runs one MCP diagnostic session personally (about 30 minutes) |
| PVC-072 | The owner authorizes one small paid live-model evaluation run |
| PVC-055 | Domain sign-off of the policy values (illustrative for the showcase) |
| PVC-071, 090, 097, 147 | Domain expert, threat-model, penetration-test and legal reviewers |
| PVC-110, 111, 113, 153, 154, 155 | A pilot company and sponsor |
| PVC-140, 144, 148 | Production owners for SLOs, retention and on-call |

## Open items

| Item | Who |
|---|---|
| Practitioner review of the showcase: packet ready ([brief](portfolio/practitioner-brief.md), [session log](portfolio/practitioner-review.md)); no session held. A reviewer with a finance background would also cover the independent finance review | Owner introduces a reviewer |
| PVC-070 session and PVC-072 live run | Owner |
| Real pilot | Needs a sponsor, authorized records, named finance and operating reviewers, a deployment and elapsed operating time |

## Engineering debts from the September 30 review

| Debt | State |
|---|---|
| Hash-chain pattern copied across the private record types | Fixed in PR #62: one 43-line `record_chain` helper replaces the copies; published record hashes are re-derived in tests |
| Logic repeated between the in-memory and PostgreSQL repositories | Fixed in PR #62: about 37 methods now live once in a shared `RecordRules` class, and each repository keeps only storage; 972 net lines removed |
| Documentation volume | Superseded plans stay in place with a pointer here, so published links keep working |
| Review | Solo project; every change goes through the ten required CI checks |

## Older documents

| Document | What it is now |
|---|---|
| [ROADMAP.md](../ROADMAP.md) | The original 111-ticket plan with per-ticket evidence |
| [IMPLEMENTATION_HANDOFF.md](../IMPLEMENTATION_HANDOFF.md) | The original design specification |
| [operating-partner-roadmap.md](operating-partner-roadmap.md) | Research and capability plan (OP-01 to OP-18), with per-PR evidence |
| [portfolio/progress-acceptance.md](portfolio/progress-acceptance.md) | Detailed acceptance evidence for the Progress case |
| [portfolio/remaining-work.md](portfolio/remaining-work.md) | Detailed pilot-preparation checklist |
| [portfolio-finalization-roadmap.md](portfolio-finalization-roadmap.md), [portfolio/acceptance.md](portfolio/acceptance.md), [portfolio/showcase-closeout.md](portfolio/showcase-closeout.md) | History of the `v0.1.0` release |
| [CHANGELOG.md](../CHANGELOG.md) | Release notes for `v0.1.0` and `v0.2.0` |
