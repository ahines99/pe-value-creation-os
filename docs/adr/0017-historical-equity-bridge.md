# ADR 0017: dated enterprise-to-equity sensitivities

Status: implemented, September 28, 2026.

The existing operating exercise values only constructed incremental earnings.
It cannot establish the public reference company's enterprise or equity value.
The public case now adds a separate historical sensitivity, using the defined
FY2025 calculated EBITDA and November 30, 2025 balance-sheet date. Information
was assembled through September 28, 2026, including a later-filed 10-K. This is
not a contemporaneous backtest or a current capital structure.

## Source and calculation decisions

`BalanceFact` represents an instant; it does not invent a fiscal duration for
cash or debt. The reviewed adapter checks PDF bytes, entity heading, page
footer, table heading, units, ordered date columns, repeated-row occurrence and
complete numeric row shape. Comparative dashes remain missing, and a selected
dash cannot silently become zero. Source and mapping hashes remain separate.
The original 241 duration facts and their fingerprints are unchanged.

Thirteen facts from the FY2025 10-K, printed/PDF pages 37 and 55, establish:

| Reconciled item | USD millions |
|---|---:|
| Cash and cash equivalents | 94.807 |
| Current convertible note principal | 360.000 |
| Noncurrent convertible note principal | 450.000 |
| Revolving credit principal | 600.000 |
| Total principal | 1,410.000 |
| Net carrying value | 1,400.349 |
| Note discount/issuance-cost deduction | 9.651 |
| Current/noncurrent operating lease liabilities | 29.567 |

Five checks reconcile the revolver across statements, current and noncurrent
notes from principal to carrying value, long-term principal and total debt
carrying value. Missing inputs, unexpected signs or mismatches withhold every
valuation row. The earnings measure must be a same-date, same-currency annual
bridge and pass its existing dependency-aware accounting checks. Nonpositive or
unavailable earnings withhold this positive-multiple model.

The formula is calculated EBITDA × authored multiple + eligible cash + credited
nonoperating assets − debt principal − selected lease claims − other claims −
transaction costs. The source EBITDA is 304.202 million; it is neither normalized
nor issuer-adjusted. No constructed initiative benefit is added to it.

The 4x/6x/8x/10x range is an authored sensitivity, not market comparables. Three
columns show full cash availability, half availability and a no-cash/claims
stress. Every cash, lease, nonoperating asset, other-claim and transaction-cost
treatment requires an explicit input and rationale. Zero is an assumption, not
evidence of absence. At 4x with all reported cash available, the residual is
negative 98.385 million; at 8x it is 1,118.423 million. Negative residuals are
preserved, not represented as negative per-share prices.

Convertible notes are assumed to settle at cash principal. Conversion, dilution,
capped calls, premiums and accrued interest are not modeled. Operating leases
are excluded under an EBITDA-after-rent convention in the first two columns.
Deducting them in the stress column is deliberately punitive; it is not a
lease-adjusted market-multiple convention. Actual surplus cash, debt-like items,
fees and a complete payoff bridge remain unresolved.

## Integration and authority

`pvc historical-valuation` exports HTML and a full JSON calculation packet.
Executive memo version 2 embeds the same computed matrix and requires two new
exact input bindings: balances and valuation specification. Changing a multiple
invalidates the memo binding without altering source earnings or operating
cash flows. CI rebuilds both reports and exercises the installed package.

The exhibit retains the subsequent Domo acquisition as context, without treating
the historical balances as post-acquisition. `current_equity_value`,
`per_share_value` and `transaction_proceeds` remain unavailable. This closes the
mechanical historical bridge increment, not independent valuation review, the
underwriting-to-realization demonstration or any permissioned pilot.

## Verification

`scripts/verify_balance_source.py` exactly reproduces all 13 facts from the
previously downloaded public source PDF; pages 37 and 55 were also visually
reviewed. Tests cover hand-worked values, all required input omissions, debt
mismatches, signs, earnings availability, multiple isolation, source identity,
private-source exclusion, parsing ambiguity, export protection and HTML escaping.
Browser acceptance covers the standalone exhibit and embedded memo matrix at
desktop, tablet and phone widths, with keyboard navigation and JSON downloads.
