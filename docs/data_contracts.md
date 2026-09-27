# Data contracts

Every contract is a Pydantic v2 model. Code is the source of truth; this page explains units, meaning and versioning. JSON Schemas for source records/profile, core evidence/findings/audit, proposals/value cases/plans, persisted run/approval/plan records and KPI/notification records are exported and snapshot-tested in `tests/snapshots/` (PVC-015). A change that alters a snapshot fails CI until the snapshot is regenerated and reviewed.

## Conventions

- **Money** is `Decimal` in the record's currency (ADR 0003). JSON carries decimals as strings. Nothing rounds before presentation, except published metrics: ratios are quantized to 4 dp and money to 2 dp.
- **Rates** are fractions in `[0, 1]`, so `0.05` means 5%.
- **Months** are the first day of the month (`2026-08-01`). Validators reject any other day.
- **`as_of`** belongs to a dataset (one per file or API pull), not to each row. Freshness is measured against the run's `reference_date` (policy `freshness.max_age_days`).
- **`company_id`** is on every source record and every stored row. Row-level security and `security.require` enforce it.
- **Evidence ids** are deterministic: `uuid5(namespace, company_id + sha256(content))`. The same bytes for the same company always get the same id.

## Source datasets (`pe_value_os.domain.source_models`)

| Dataset | Record | Grain | Key fields |
|---|---|---|---|
| `pnl` | `PnLLine` | company × month × account | `account` (see below), `amount`, `currency` |
| `customers` | `Customer` | customer | `segment`, `size_band`, `acquisition_channel`, `first_contract_date`, `domain`, CRM and billing ids |
| `arr` | `CustomerArrMonth` | customer × month | `arr` (annualised, ≥ 0), `product`, `price_book_id` |
| `churn` | `ChurnEvent` | customer × month | `churn_type` (`voluntary`, `involuntary_payment`, `involuntary_other`), `reason_code`, `notes` (untrusted text) |
| `price_books` | `PriceBook` | price book | `list_price_per_unit`, `effective_from/to`, `is_current` |
| `invoices` | `InvoiceLine` | invoice line | `quantity`, `list_price_per_unit`, `on_invoice_discount`, `net_amount`, `deal_size_band` |
| `concessions` | `Concession` | concession | `concession_type` (credit, free months, extended terms, rebate, uncharged services), `amount` |
| `contracts` | `ContractTerm` | contract | `contracted_uplift_rate`, `price_cap_rate`, `cpi_linked`, `mfn_clause`, `notice_days`, `termination_for_convenience` |
| `support` | `SupportTicket` | ticket | `category`, `severity`, `tier`, `handle_minutes`, `csat` (1–5) |
| `usage` | `UsageMonth` | customer × month × feature | `active_users`, `licensed_users`, `events` |
| `crm_opportunities` | `CrmOpportunity` | opportunity | `stage` (won/lost/open), `opportunity_type` (new/expansion/renewal), `amount` |
| `headcount` | `HeadcountMonth` | month × function | `fte`, `fully_loaded_annual_cost_per_fte` |
| `documents` | `Document` | document | `text` (untrusted; never treated as instructions) |

P&L accounts: `revenue_subscription`, `revenue_services`, `cogs_hosting`, `cogs_third_party`, `cogs_support`, `cogs_services`, `sales_marketing`, `research_development`, `general_admin`.

Validation errors name the file, row (1-based, header is row 1) and field, for example `arr.csv row 2891 field 'month': Input should be a valid date`. Unknown columns are rejected. Invalid rows are excluded and reported as a `row_errors` sufficiency gap. The gap blocks the analysis when invalid rows exceed 2% of a required dataset.

## Value-creation contracts (`pe_value_os.domain.project_models`)

| Contract | Owner of each field |
|---|---|
| `OpportunityProposal` | Proposer (rules or model): lever, baseline metric **name**, scenario rates, confidence, rationale, evidence ids, costs. `extra="forbid"`, so a proposer cannot send `baseline_value` or `ebitda_flow_through`. |
| `Opportunity` | Server adds `baseline_value` and `ebitda_flow_through` from company data (`domain.baselines.derive_baseline`). |
| `ValueCase` | `domain.services.size_value_case`: `annual_ebitda_{low,base,high} = baseline × improvement × realization × flow_through − annual_run_cost`. Stamped with `calc_version` and `inputs_hash`. |
| `PriorityScore` | `domain.prioritization.prioritize`: weighted score, rank, run-rate and in-year value. |
| `Plan` | `workflows.planning.build_plan`: workstreams, initiatives, KPIs, dependencies, risks. |

Scenario ordering is validated as `low ≤ base ≤ high` by effective rate (improvement × realization).

## Baseline metrics (`pe_value_os.domain.baselines.REGISTRY`)

Each lever can only use certain baseline metrics (`LEVER_METRICS`). The same registry decides whether a KPI is monitorable.

| Lever | Allowed baseline metrics |
|---|---|
| pricing | `renewing_arr`, `discounted_arr`, `legacy_price_book_arr`, `total_arr` |
| retention | `addressable_churned_arr`, `failed_payment_churned_arr`, `annual_contracted_arr` |
| sales_efficiency | `s_and_m_expense` |
| gross_margin | `subscription_cogs`, `hosting_cost` |
| ai_automation | `support_cost_tier1`, `finance_ops_cost`, `subscription_cogs` |

Ratio metrics that can be monitored as KPIs are: `grr`, `nrr`, `segment_grr`, `subscription_gross_margin`, `cac_payback_months`, `involuntary_churn_share`, `avg_new_deal_discount_rate`, `renewal_uplift_realization`, `legacy_arr_share` and `tier1_tickets_per_customer_month`.

## Stored records (PostgreSQL)

Migrations live in `src/pe_value_os/db/migrations/versions/`:

- `0001` covers companies, runs, evidence, findings, opportunities, value cases, priorities, plans, approvals and audit.
- `0002` covers KPI definitions, observations, alerts and the notification outbox.
- `0003` adds notification delivery claims for durable shared-worker retry/ownership.

`RunRecord`, `ApprovalRecord`, `PlanRecord`, `KpiAlert` and `Notification` have independent schema snapshots; `RunRecord.state` and plan JSON remain extensible payloads, so a top-level schema snapshot alone does not prove semantic compatibility of those payloads. Workflow behavior tests cover immutable input/policy snapshots, review rounds and refresh linkage.

## Numeric claim references

`get_numeric_sources(company_id)` returns a catalog with `key`, `metric`, `value`, `unit`, `company_id`, `period` and `evidence_ids`. For numeric prose in `record_finding` or `propose_opportunity`, copy a key from this catalog and write `{{quantity:KEY}}`. For example, use `Legacy share is {{quantity:pricing.legacy.legacy_arr_share}}` only when that exact key is returned. The server renders the fact with its provenance. Unbound numbers, invented keys and ID substrings cannot supply numeric evidence. Qualitative prose remains supported. Structured scenario rates/cost assumptions remain separate proposal fields; they are not facts to insert into prose.

Every company-scoped table has row-level security keyed on the `pvc.companies` session setting. `audit_events` is insert and select only for `pvc_app`.

## Versioning policy

- **Additive** changes, such as a new optional field or a new dataset, bump the minor contract version and need no migration of stored JSON.
- **Breaking** changes, such as renaming or removing a field, changing units, or tightening validation on stored data, need an ADR, an Alembic migration (where stored), a regenerated snapshot, and a note in the release changelog.
- **Calculation** changes bump the relevant `CALC_VERSION` (`value-case/1`, `saas-metrics/1`, `retention/1`, `price-waterfall/2`). Stored value cases keep their version. Recomputing is an explicit, audited action (`pvc recompute`, PVC-145).
- **Policy** changes bump `policy.toml` `version`. The version is recorded on value cases and audit events.
