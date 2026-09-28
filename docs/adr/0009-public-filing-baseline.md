# ADR 0009: public filing facts and explicit financial measures

Status: accepted for the annual financial baseline implementation; case revision
persistence and monthly initiative modeling remain subsequent work.

Subsequent extensions: [ADR 0010](0010-monthly-underwriting.md) implements the
constructed monthly model. [ADR 0011](0011-quarterly-source-and-perimeter.md) adds
quarterly extraction/derivation and replaces the period-wide reconciliation block
below with dependency-aware gates. Original annual source records remain intact.

## Context

The existing research lane is deliberately private and expects Compustat fields.
Using it as the public issuer adapter would mislabel accounting measures and
blur vendor-output restrictions. Current-vintage statements also must not imply
historical underwriting knowledge.

## Decision

Add a small `diligence` module with strict immutable typed source, fiscal-period
and fact contracts. Preserve public filing accession, publication and retrieval
dates, source bytes hash, extraction mapping hash, original signed value/scale,
and exact page/row/column. Separate annual, discrete-quarter and YTD durations;
reject duplicate facts and foreign source/entity references. Missing is not zero.

Extract explicitly reviewed PDF tables with exact document-hash, page, header,
column-order and numeric-shape checks. This is not a universal table parser.
The adapter requires no credentials and performs no automatic scraping. Store
the compact public fact extract in the repository so analysis replays offline.
Keep source PDFs local; link the original documents.

Calculate named measures using Decimal and declared signed inputs. Reconcile
reported financial statement relationships first. An unexplained cross-statement
difference withholds derived headlines for that period while retaining reported
facts and the difference for review. Public export rejects private/constructed
source classes. Source classification is a reviewed input policy, not proof of
truth merely because a caller supplied a label.

Retain the original private research module and existing approval/workflow
semantics. A public financial baseline does not create a plan, claim a company
engagement, activate KPIs or accept a finance review.

## Calculation provenance correction

Screening sizing becomes `value-case/2`: its fingerprint includes the opportunity,
normalized optional EV multiple and calculation version. Operating scenario
amounts are unchanged. Existing stored v1 records stay historical until explicitly
recomputed. Replace nonpositive-contribution wording that incorrectly implied a
cash payback calculation. Monthly independent cost/benefit timing is a later
calculator, not silently substituted into old approved plans.

## Verification and consequences

Use synthetic PDF extraction tests, independently recomputed public fact golden
cases, negative sign/unit/period/currency/reference/source-policy tests and HTML
escaping. Preserve amortization exceptions as a test of honest missingness.
Render the baseline at desktop/tablet/mobile widths using the existing design
system. Later case revisions will reference the immutable bundle fingerprint;
this ADR does not yet implement their database persistence or review service.
