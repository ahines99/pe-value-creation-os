# Private ledger intake preflight

This is the first executable increment of private-data readiness. It checks a
normalized monthly export against an explicit scope, account mapping and separate
control totals. It does **not** verify permission, admit records to a case, record
finance approval, or authorize an operating intervention. The existing
[pilot entry gates](../pilot-plan.md) remain required.

The command is a local operator tool. It has no model invocation, source-system
connection, database write, public renderer or MCP tool. Its receipt is private
even when the input is a synthetic test fixture.

## Three inputs

| Input | Contents | Check |
|---|---|---|
| `IntakePolicy` | Company/entity, native currency, complete monthly period range, purpose, authorization-document reference/hash, processing and retention dates, account mappings and independently sourced controls | Unique account mapping; all six components covered for every declared month; no missing period/control interpreted as zero |
| `IntakeManifest` | Company, source/export identity, extraction reference/time, cutoff, source-file hash, canonical policy hash and record count | Exact bytes and policy match; company, cutoff, extraction and processing window agree |
| `Ledger` | Unique source-row ID, entity, month start, account code, currency and native-currency amount for each row | Reject extra fields, duplicate IDs, unmapped accounts, foreign scope, partial/out-of-scope periods, floats, nonfinite values and sub-cent amounts |

Amounts use decimal strings or integers, never JSON floating-point amounts.
Account mappings declare a `1` or `-1` multiplier explicitly. Standardized expense
and cash-outflow controls use signed amounts; credits remain signed source rows.
The six components are revenue, operating expense, implementation expense,
operating cash, working-capital cash and capex cash. Their definitions and
non-overlap must be reviewed by finance: matching totals alone does not prove
correct accounting classification, complete economic coverage or a counterfactual.

The normalized contract is not a general ERP extractor. Company-specific source
queries and transformations must retain lineage and be reconciled separately.
Each file is limited to 10 MiB and a ledger to 100,000 rows. Duplicate JSON keys
are rejected before model parsing. The policy fingerprint is SHA-256 of its
validated JSON-mode representation with sorted keys, using the module's
`fingerprint` function. The source fingerprint covers the original ledger bytes.

Authorization and control-source references are declarations supplied for review.
The preflight does not retrieve or authenticate those documents. A syntactically
valid reference is never reported as verified permission or independent review.

## Run the synthetic rehearsal

The committed [fixture inputs](../../../tests/fixtures/pilot-intake/) are seven
fictional rows. They include a revenue credit and explicit debit-to-expense
mapping. They represent no sponsor, actual permission or company ledger.

PowerShell, from the repository root:

```powershell
$env:PVC_OPERATOR_COMPANIES = "pilot-fixture"
uv run pvc pilot-intake-check --policy tests/fixtures/pilot-intake/policy.json --manifest tests/fixtures/pilot-intake/manifest.json --ledger tests/fixtures/pilot-intake/ledger.json --name fixture-review-one
```

The fixture's processing window is September 1, 2026 through January 1, 2027
(exclusive); retention ends February 1, 2027. The command uses actual UTC time,
so an expired fixture correctly fails before opening the ledger. Tests freeze the
assessment at September 29, 2026. Do not change an actual company's dates or
authorization reference to bypass an expiry check.

The local operator must explicitly name the company in `PVC_OPERATOR_COMPANIES`.
This is the existing operator-machine trust boundary, not deployed identity
provider authentication and not a data-access agreement. The library also checks
company scope, human principal type, operator role and `pvc.read` when OAuth scopes
are present. It rejects an unauthorized operator before opening the ledger.

## Read the result

The console contains only status, issue count and false authorization/admission
flags. Validation errors do not echo private cell values or paths.

The detailed receipt is written to
`var/permissioned-pilot/fixture-review-one.json`. Paths cannot escape that root
or redirect through a symlink to a public directory. Receipts use exclusive
creation: choose a new name for a correction or rerun; an existing receipt and
the three inputs are not overwritten.

- **`ready_for_finance_review` / exit 0:** structural, scope and exact control-total
  checks pass. Permission verification, finance acceptance and data admission
  are still false.
- **`quarantined` / exit 2:** the entire batch fails preflight. Source files stay
  in place; this is a verdict, not a persisted quarantine queue. Row-level issues
  identify source ordinals without copying the offending field values. Failed
  identity, scope, date or size checks prevent ledger parsing.
- **Command failure / exit 2:** malformed or mismatched policy/manifest, expired
  processing/retention window, missing scope, unsafe
  output location, existing receipt or I/O failure. No successful receipt is
  claimed. Inspect private inputs locally; do not paste private exception data
  into a public issue.

Matched controls do not permit partial acceptance when another row fails.
Missing zero-value components need explicit zero rows. Exact cents are retained
under debit/credit cancellation and independently of caller Decimal precision.
The report retains source, policy and manifest hashes for a later review binding.
It cannot be rendered as a public exhibit by this tool.

## What remains before actual intake

This command does not replace the [permissioned pilot package](README.md).
Still required are authenticated grant/revocation records, authorized source
storage, persisted quarantine and correction history, finance decisions bound
to exact versions, accepted-record integration with private case/actuals
contracts, and retention/deletion enforcement for all copies and backups.
Passing preflight creates none of those records. Current constructed-only case,
operating-source, execution and realization contracts remain unchanged.

Testing uses only fictional inputs. No private company data has been received,
no pilot has started, and no external approval is inferred.
