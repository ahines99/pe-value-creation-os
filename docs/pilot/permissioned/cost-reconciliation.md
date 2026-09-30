# Private delivery-cost reconciliation

The calculation contract is implemented and has 21 focused fictional-fixture
checks. It is not yet integrated into either repository, the human API or the
review workspace. No persisted finance acceptance or cross-stream reservation
is represented. The existing workspace continues to identify delivery costs as
unreconciled until those integration and review gates are implemented and met.

## Financial meaning

A delivery report records incurred cost without proving its accounting treatment.
The new matching request identifies exact delivery receipts, accepted ledger
sources and source rows. Its author must explain the report's comparability to
expense and capex cash, the timing of recognition/payment, population and limits.
The financial definitions remain those of the reviewed intake policy.

Expense and capex cash are shown separately. A capex payment is not automatically
an asset addition or an incurred-cost measure. Operating cash is excluded from
this matching pool to avoid counting an expense and its settlement as two costs.
Additional invoice/asset/accrual evidence may be necessary to establish a common
basis. The current contract does not establish complete project cost, cash-paid
reconciliation, tax treatment or asset capitalization.

This is a link to existing amounts, never another financial posting. Neither
underwriting nor observations change. It cannot subtract implementation expense
twice, create savings, or establish causal impact.

## Calculation and evidence controls

The request binds the frozen baseline and exact execution head. It includes all
current delivery segments in the comparison, even if no ledger amount is assigned
to them. Corrected segments replace their predecessors; a superseded receipt
cannot be selected for a new allocation.

Every source must match the company's entity, currency and origin. Its bytes,
preflight, current finance acceptance and exact processing grant are checked before
parsing, under the integrating repository's company lock. Same-byte duplicates
and overlapping logical cost rows in changed exports cannot create another pool.
Logical identity uses source system, entity, accounting month and source row ID;
it relies on truthful stable source identifiers, not arbitrary renamed aliases.

Each allocation retains its source charge or credit sign. Splitting a row across
deliveries cannot exceed that row's magnitude. Credits cannot offset overuse of a
different row. Zero, floating-point and nonfinite allocation amounts are rejected.
The calculator uses explicit Decimal precision independent of the caller's context.

Outputs retain each delivery's reported cost, matched expense, matched capex cash
and difference, plus each source row's allocated and unassigned amount. Equal
aggregate totals do not count as a full match when individual deliveries differ.
Unassigned company ledger amounts are not automatically missing project costs;
the source can contain unrelated company activity.

`all_reported_costs_matched` describes arithmetic for the supplied scope only.
`all_project_costs_captured`, `finance_reviewed`,
`cross_stream_reservations_checked` and `additional_ebitda_or_cash_posting` remain
false. Historical event validity is distinct from active operating permission.

## Required integration before use

1. Resolve baseline, execution and accepted source contexts under the existing
   company transaction; require current baseline/source support for new work.
2. Persist append-only proposals, exact source and delivery bindings, corrections,
   actor-bound retries and audit records in both repositories with forced RLS.
3. Add distinct human finance assessment of source identity, comparability,
   treatment, completeness and unexplained differences. Preserve withdrawal after
   permission revocation without reopening private source bytes.
4. Reserve accepted source-row amounts against other active reconciliation streams
   across the company, including different baselines and corrected exports. Test
   concurrent acceptance, revocation, source correction and rollback.
5. Add bounded human API routes, current-use reproduction, offboarding/migration
   coverage and a review workspace display that separates recorded acceptance from
   current support. Reconciliation must not silently promote attribution claims.
6. Complete CI and exact-build release verification. Actual company source mapping,
   invoice/contract validation, independent finance participation and the performed
   pilot remain separate evidence requirements.
