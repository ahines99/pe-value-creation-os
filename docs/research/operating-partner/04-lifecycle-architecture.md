# Investment lifecycle, baseline integrity and institutional learning

Research date: 27 September 2026. Scope: repository audit and proposed roadmap; no implementation or investment-performance claim. Owner: Codex. Progress Software is the first research case; any ownership journey is an explicitly constructed case exercise unless permissioned operating records subsequently exist.

## Recommendation

Add a small investment-case layer above the existing diagnostic runs. Preserve the current workflow, approval UI, evidence store, PostgreSQL repository and audit trail. Freeze an underwriting revision, record a separate close-validation revision, then compare later operating observations and reconciled financial results against both. The showcase should demonstrate this loop with transparent constructed schedules, while leaving actual realized value unavailable wherever transaction or finance evidence is absent.

The central missing capability is a durable answer to: **What did we believe at that decision date, what changed, who accepted the change, and what result can we substantiate?** A new dashboard, additional synthetic companies, generic project-management SaaS or event-sourcing infrastructure would not answer that question.

## What already exists, and the precise gap

| Existing implementation | Evidence in repository | Gap to the investment lifecycle |
|---|---|---|
| Run identity, statuses, reference date, parameters and step artifacts | `src/pe_value_os/domain/runs.py`; `workflows/primary.py` | A run is a diagnostic execution, not an investment, original underwriting case or ownership stage. `complete` means the workflow completed, not that EBITDA was realized. |
| Frozen input and policy snapshots; linked replacement runs on refresh | `workflows/steps.py` intake; `workflows/primary.py` `execute` and `refresh_inputs` | Good replay foundations. There is no named underwriting/close baseline or structured cross-run explanation of assumption changes. `supersedes_run_id` lives in parameters rather than a business-case version contract. |
| Deterministic value cases with `calc_version`, `inputs_hash`, scenarios, cost and optional EV fields | `domain/project_models.py` | No complete financial measurement basis, reporting period, original forecast series or realized-value attribution contract. Existing hashes prove input identity; they do not establish financial correctness or historical availability. |
| Original proposed plan, approved plan, edits/diff and human decision receipt | `approvals.py`; `domain/runs.py`; migration `0001` | Valuable governance to retain. The decision service loads a plan and activates KPIs: a new baseline or realization review cannot safely reuse it unchanged just because `artifact_type` is a string. |
| KPI definitions linked to plan/run, baselines and dated observations with evidence | `domain/kpi_models.py`; `kpi.py`; migration `0002` | Movement is observable, but its incremental P&L contribution is not reconciled. New matching metric/parameter definitions deactivate older active definitions; a lifecycle comparison must explicitly retrieve historical definitions, not only the active set. |
| Evidence hashes, retrieved/as-of timestamps, supporting and contradicting findings | `domain/models.py`; `adapters/evidence_store.py` | Add typed publication/data-origin policy and historical availability semantics. Existing free-form metadata is insufficient to enforce public export or point-in-time claims. |
| Application authorization, company RLS, separate database roles and append-only application audit permissions | `security.py`; `approvals.py`; `db/roles.sql`; migrations `0001`–`0003` | Extend these boundaries to every new case record and export. Current database audit permissions do not make all business records immutable or tamper-proof. |
| Private financial research bundle with original row, file hash, vintage, availability and period/currency | `research/models.py`; `research/pilot.py` | `retrospective_current_vintage` is correctly explicit. There is no investment-case persistence or permission to relabel standardized historical extracts as what was known at an earlier underwriting date. |

This audit read code and contracts; it did not rerun unrelated regression suites or claim new test results.

## Research basis and limits

IPEV distinguishes a valuation basis, technique and inputs; its 2025 guidance calls for documented judgments and review. Its backtesting discussion compares prior estimates with subsequent liquidity events while considering information available at the earlier measurement date. This supports preserving original judgments and explaining later differences. It does **not** certify this project's operating model or make an EBITDA-times-multiple sensitivity a fair-value opinion. [IPEV 2025, introduction, application, sections 2.6–2.7](https://www.privateequityvaluation.com/Portals/0/Documents/Guidelines/2025%20IPEV%20Valuation%20Guidelines.pdf)

ILPA is refreshing its portfolio-company metrics template for investment-level comparability, with the updated version expected in 2027. Use consistent company, period and measurement definitions now; avoid claiming conformity to a future template or confusing the fees/carry reporting template with an operating initiative ledger. [ILPA portfolio-company metrics refresh](https://ilpa.org/news/portfolio-company-metrics-template-refresh/)

SEC submissions and XBRL APIs provide public filing context. The frames endpoint selects a last-filed fact fitting a calendar period, and companies' fiscal periods can differ. Therefore the proposed historical-evidence mode must preserve a specific filing and reporting context rather than treat a current frames response as a historical information set. [SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

The architecture below is an engineering recommendation inferred from the product's needs and existing implementation; these sources do not prescribe its schema.

## Smallest viable typed architecture

Retain Pydantic, Decimal, PostgreSQL JSONB, existing repositories and Alembic. Use ordinary transactions plus immutable business revisions and the existing audit stream. No message bus, generic workflow replacement, graph database, fund-accounting platform or custom event-sourcing engine is required.

### Initial three tables

1. **`investment_cases`**: `case_id`, `company_id`, label, `case_kind` (`research_exercise` or `permissioned_investment`), reporting currency, nullable actual close/exit dates, created actor/time, and an optimistic-concurrency version. A research exercise has an explicit hypothetical timeline; it must not invent an acquisition of Progress Software.
2. **`case_revisions`**: immutable revision UUID, case/company IDs, monotonic revision number, parent revision ID, stage (`underwriting`, `close_validation`, `ownership_review`, `exit_review`), effective date, recorded timestamp, author, reason, schema version, canonical payload hash and typed JSONB payload. The payload contains the thesis, disconfirming conditions, baseline facts, assumptions, scenario ID, stable initiative IDs, source run/plan IDs, calculation/policy versions and evidence references. Store original underwriting and close revision pointers as explicit reviewed designations; do not define either as simply the newest revision.
3. **`case_reviews`**: a human receipt bound to the exact revision ID/hash, review kind, decision, actor, time and rationale. It is separate from existing plan approval because reviewing a research case does not authorize company operations. Correction or withdrawal is a new receipt with a supersedes reference. A pending review remains pending; a model may draft but cannot sign it.

Draft editing can remain in a local typed case file for the first showcase. Persisting a revision creates a new immutable record; subsequent edits create another revision. Avoid building collaborative draft-editing software before the single-case loop is convincing.

### Three later tables when ownership tracking is implemented

4. **`period_actuals`**: case/company, metric-definition version, period start/end, fiscal basis, currency, unit, actual value, source origin, evidence references, recorded time and prior-revision reference. Corrections append; original numbers remain inspectable. A typed nullable value with missing reason is preferable to silently substituting zero.
5. **`realization_claims`**: stable initiative ID, comparison-baseline revision, period, linked KPI observation IDs and actual-record IDs, incremental revenue/expense bridge, recurring benefit, implementation expense/cash, working-capital movement, attribution explanation, allocation references and calculation version. Review receipts cover these claims as a distinct artifact type with enforced foreign-key targets, not an unconstrained ID string. Extend `case_reviews` with explicit nullable revision/claim target columns and a check requiring exactly one target.
6. **`case_lessons`**: review date, source revision/claim references, expectation, outcome, variance reason, alternative explanations, proposed policy change and later acceptance/rejection. This is a small searchable review register. It does not automatically retrain a model or recalibrate probability estimates from one case.

Stable initiative IDs live inside immutable revision payloads initially, with a typed mapping to run-specific opportunity IDs. Add a relational initiative table only if actual querying or integrity requirements justify it. Splitting or merging initiatives requires explicit predecessor IDs and allocation rules; title matching is not identity.

### Required nested contracts

| Contract | Required semantics |
|---|---|
| `MetricDefinition` | Name, version, unit, currency where relevant, fiscal period, accounting basis, scope and formula. GAAP, issuer-adjusted and analyst-constructed EBITDA remain distinct. |
| `BaselineFact` | Metric definition, value or missing reason, evidence, reporting period, selected vintage, normalization adjustments and reviewer status. A close revision never overwrites underwriting facts. |
| `Assumption` | Stable ID, value/unit, low/base/high or scenario reference, rationale, evidence, uncertainty, owner and invalidating condition. Keep probability of success separate from magnitude/capture rate. |
| `SourcePolicy` | `public_filing`, `licensed_private`, `constructed` or `permissioned_private`; provenance, permitted outputs and review status. Derived artifacts inherit the most restrictive input policy unless explicitly cleared. |
| `ExecutionUpdate` | Planned/in progress/blocked/completed/cancelled, effective date, owner, milestone evidence and reason. This describes work, not realized financial value. |
| `ValueEvidence` | Modeled / operationally observed / financially reconciled / reviewer accepted. Separate run-rate estimate, period EBITDA contribution, cash release and transaction proceeds. |
| `ActualComparison` | Frozen comparison revision, original forecast, current forecast, actual, variance components and unexplained residual, using consistent period and basis. |
| `Lesson` | Hypothesis tested, evidence maturity, outcome, causes, residual uncertainty and proposed change. Descriptive learning must precede any claim of statistical calibration. |

## Three independent state dimensions

Do not implement `Identified → Approved → Execution → KPI Achieved → EBITDA → EV Realized` as one mandatory linear status. An approved initiative can be blocked; a KPI can improve for unrelated reasons; a realized cash release can occur without recurring EBITDA; an initiative can be cancelled after partial benefit.

| Dimension | Example states | Transition evidence |
|---|---|---|
| Decision | Draft, submitted, accepted, rejected, withdrawn, superseded | Human receipt for the precise artifact/version. |
| Execution | Planned, in progress, blocked, complete, cancelled | Owner update, dated milestone and evidence. |
| Measurement | Modeled, KPI observed, financial bridge prepared, financially reviewed | Source observations, a finance bridge and a qualified reviewer receipt. |

Transaction outcomes belong to the investment case, not automatically to individual initiatives. An exit-price or proceeds record needs actual transaction evidence; a public market multiple or estimated EV change cannot produce `EV realized`. A completed milestone cannot manufacture financial acceptance. Missing evidence remains visible even if the user accepts the software showcase.

## Historical information and revisions

Record four distinct times: the economic reporting period, source publication/availability time, ingestion time, and decision/effective time. Preserve both source revisions and case revisions. A report generated today about an earlier fiscal year is not automatically point-in-time.

Keep the existing Compustat pilot labeled retrospective current-vintage. A separate `filing_snapshot` mode can use archived public filings, with accession/document identity, publication timestamp, fiscal context, source hash and extraction version. To support an earlier decision-date comparison, reject records published later than that date and preserve the original fact instead of substituting a later restatement. When a reliable timestamp or original vintage is absent, disable the historical-availability assertion rather than guessing.

Do not promise full historical point-in-time LSEG or WRDS coverage merely because an attended session succeeds. Entitled fields, revision semantics and timestamp coverage need verification. A narrow reproducible filing snapshot is sufficient for the portfolio milestone; a general financial data warehouse is deferred.

## Migration, provenance and permission plan

- Add schema revisions after the actual current Alembic head at implementation time; do not assume a migration number remains free. First add case/revision/review tables without altering existing diagnostic semantics.
- Use company-scoped composite foreign keys where a child carries both company and parent identity. Validate nested evidence/run/plan/initiative references in the transaction against the same company and case. Reject foreign or invisible references.
- Apply forced RLS to every new table and reuse the non-owner runtime role. PostgreSQL owners normally bypass RLS unless forced; superusers and `BYPASSRLS` roles remain outside it. Run isolation tests with the real restricted role. [PostgreSQL RLS documentation](https://www.postgresql.org/docs/18/ddl-rowsecurity.html)
- Grant runtime select/insert for immutable revisions and receipts; expose only narrowly needed updates on case metadata. Controlled corrections append new business records. Keep administrative retention/deletion separate and audited; immutability does not mean retaining confidential data forever.
- Add scoped commands for authoring revisions, reviewing cases and reviewing financial claims. Preserve the existing prohibition on model principals approving. Finance-review authority is an application capability, not a claim that a token holder is a qualified accountant.
- Never backfill existing showcase approvals as investment underwriting or finance acceptance. Offer explicit linking of a legacy diagnostic to a new research case; copy relevant references and mark their original context.
- Public export operates on an explicit allowed-data projection, including prose, charts, tooltips, embedded JSON and source metadata. Licensed raw values, credentials, local paths and vendor-derived prohibited outputs cannot leak through a narrative or chart just because a CSV was omitted.
- Retain the current original/approved plans and old KPI history through upgrade. Verify a rollback on disposable data and take a backup before any future migration of the live showcase. A rollback that would erase newly authored case history requires an explicit restore/export plan.

## Prioritized implementation tickets

Engineering days are focused implementation estimates including targeted tests and review, not a calendar promise. Work overlaps other agents' financial, evidence and executive-output tickets; the coordinator must deduplicate rather than sum every estimate.

| Ticket | Priority / effort | Dependency | Deliverable and acceptance | Meaningful verification |
|---|---|---|---|---|
| LC-01 Measurement and identity contract | P0 / 1–2 days | Financial-method and evidence contracts | Typed case/revision/baseline/assumption schemas; stable initiative mapping; origin classification. One approved design ADR with worked constructed examples and explicit absent-realization states. | Reject mixed units/bases, invalid periods, duplicate initiative IDs, future evidence and unspecified source policy. |
| LC-02 Additive case persistence | P0 / 2–3 days | LC-01 | Three initial tables, repository protocol plus memory/PostgreSQL implementations, RLS and immutable revisions. Existing Beacon/Delta history remains readable. | Upgrade populated disposable DB; cross-company parent/reference injection; mutation rejection; two simultaneous revision writes produce one conflict rather than lost history. |
| LC-03 Review and version comparison | P0 / 2–3 days | LC-02 | Dedicated case-review service, exact revision/hash binding, structured assumption/baseline delta and explicit underwriting/close pointers. | Stale revision review, duplicate decision, model principal, unauthorised company and transaction rollback tests. Change a baseline; original underwriting result and receipt remain identical. |
| LC-04 One transparent lifecycle case | P0 / 2–3 days | LC-03; research/evidence and finance outputs | Progress research exercise with public reported facts, clearly constructed operational schedules, alternative thesis, rejected hypothesis and hypothetical close revision. Public export excludes restricted inputs. | Rebuild from allowed sources; change an assumption and verify downstream deltas; inspect every exported data surface; verify constructed records never become reported actuals. |
| LC-05 Period actuals and financial attribution | P1 / 3–5 days | LC-02; financial-realization method | Append-only actuals/claims; original/current forecast versus actual; finance bridge and review. Demonstrate with constructed finance records first. Real results stay unavailable without evidence. | Restatement preserves prior record; idempotent import; duplicated benefit allocations; period/currency mismatch; cost/cash/EBITDA separation; negative result and unexplained residual survive export. |
| LC-06 Execution and KPI lineage | P1 / 2–3 days | LC-03; operating-method sequencing | Independent execution updates, stable initiative links and historical KPI comparisons. No automatic conversion from on-track KPI to financially accepted benefit. | KPI target revised after approval; old history still shown; cancelled initiative with partial benefit; split/merged initiative allocation; execution cannot bypass review permissions. |
| LC-07 Filing-date replay | P1 / 2–4 days | LC-01; public-source ingestion | One historical filing snapshot with accession/time/hash/context and decision-date eligibility. Existing vendor bundle remains current-vintage. | Later amendment excluded from earlier replay; same-period facts retained by accession; missing timestamp blocks historical claim; fiscal YTD versus quarter mismatch rejected. |
| LC-08 Exit and lesson review | P2 / 2–3 days | LC-05–07 | Investment-level exit scenario/actual separation and searchable lesson register with attribution limitations. Constructed exit walkthrough is labeled throughout. | Market multiple change does not create realized proceeds; actual transaction absent yields unavailable; lessons retain original forecast and later information distinction. |
| LC-09 Restricted export and retention hardening | P1 / 1–2 days | LC-04–06 | Consistent policy propagation, private export route, scoped audit and retention documentation. Basic export gate ships in LC-04; this expands coverage. | Restricted datum injected into narrative/chart/source metadata is blocked; caller cannot query another company; retention process cannot silently change surviving revision content. |

The first reviewable lifecycle showcase is LC-01–04: approximately **7–11 engineering days**, dependent on the parallel finance and evidence work. The fuller research-exercise loop is approximately **17–28 engineering days** across all tickets. This estimate excludes obtaining real operating data, elapsed independent-review time and any production deployment program.

## Ownership and stopping rules

Codex owns schemas, ADRs, source adapters, migrations, authorization integration, deterministic comparisons, UI/export, constructed walkthrough data, tests and reviewer materials. Use the existing local Docker setup and Claude Code connection. The user need not select tables, database technology, workflow engine or cloud services.

The user supplies only nondelegable future inputs: permissioned company data and its allowed uses, management facts unavailable from public sources, and actual authorized human decisions if the project becomes an operating pilot. A finance practitioner can review the attribution method later; Codex prepares the packet and can implement corrections, but must not create a fictitious practitioner acceptance.

The showcase is done when a reviewer can inspect one company's original thesis, challenge an assumption, see a justified revision, trace each number to an allowed source or a labeled construction, and distinguish modeled value from observed and financially reviewed outcomes. A real operating pilot is a separate milestone requiring real operational and financial evidence. Production multitenancy, generic portfolio aggregation, formal fair-value reporting and automated institutional calibration remain deferred until that evidence and use case exist.
