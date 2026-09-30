# Private executive finance review

The private review workspace brings an exact attribution proposal, accounting
comparison, frozen plan, delivery history and finance decision into one page.
It was released in PR #51 with fictional acceptance fixtures; exact-build
verification is recorded in the [acceptance map](../../portfolio/progress-acceptance.md).
It does not represent a performed company pilot.

## Open a review

Use an authenticated, company-scoped human identity to open `/private-reviews`.
The desk lists the latest proposal in each accessible case and attribution stream.
Its displayed decision is a recorded historical decision, not a current-support
certificate. Open a card to inspect
`/companies/{company_id}/private-reviews/{revision_id}`.

The server checks current source, observation, baseline, proposal and finance
support using its configured processing environment. A missing environment or
revoked permission leaves historical review records readable to authorized human
readers, with a warning and substantive decision controls disabled. Historical
access includes stored financial amounts; it does not reopen original source bytes.

The page shows actuals, counterfactuals, their difference, frozen incremental plan
and variance for the same measured months. Allocation plus residual equals the
accounting difference. Earnings and cash remain separate. Expand the monthly
components, source assumptions, valuation limits, claim evidence or version trail
for the underlying detail. The page states the currency and unit basis explicitly.

Recorded delivery costs are displayed separately and are not yet reconciled to
individual accounting entries. A supported historical task acceptance does not
imply that operating authorization remains active today. Finance acceptance does
not authorize operating changes or prove causal impact.

## Record the human decision

An authorized finance reviewer other than the proposal author can accept, reject
or request changes while the proposal has current support. Acceptance requires a
rationale and all five assessments: accounting reconciliation, mechanism/delivery,
alternative explanations, double counting/residuals and attribution limits.
Other decisions retain any additional assessment notes in their rationale.

Every submission binds the exact proposal, execution head and preceding finance
review. The repository checks those bindings again under the company lock. A stale
form cannot overwrite a later decision. The page preserves submitted notes when
displaying a validation or version-conflict response; inspect the refreshed
evidence before submitting again. A preceding acceptance can be withdrawn after
processing revocation without restoring permission.

The form uses the existing authenticated browser session, a short-lived HTTP-only
SameSite Strict CSRF cookie, a matching form token and a bounded URL-encoded body.
Cookies are Secure outside development. JSON write endpoints continue to require
explicit bearer authentication. Model and service identities cannot use these
human review workflows. Responses are non-cacheable and require no JavaScript.

The stored evidence fingerprint covers the submitted note and exact review
bindings. It identifies an internal authored review record; it does not assert
that an external supporting document was independently authenticated. The
review-data fingerprint identifies the assembled data, not the rendered HTML.

## Verification and limits

Workflow tests exercise both repository implementations, browser-session
decisions, exact version checks, role boundaries, CSRF failures, escaped content,
withdrawal after revocation and retention of decision notes. The isolated browser
checks render pending, accepted, revoked and index states at 1440, 768 and 375
pixels, checking overflow, keyboard entry, controls and accessible table regions.
These fixture captures stay under ignored `var/`, outside public exports.

This is the attribution-review interface. Source onboarding, underwriting and
operating-plan authoring still use their existing private API contracts. A complete
private executive memo, the remaining pilot screens, operating-source/cost
reconciliation, retention operations and real participant acceptance remain open.
