# Presenting Value Creation OS

> **For current status, see [STATUS.md](../STATUS.md).** This file is kept as interview preparation notes; where it differs from STATUS.md, STATUS.md is right.

**Portfolio and interview guide · public research plus constructed operating exercise**

Start with the [portfolio site](../index.html), use the
[ten-minute walkthrough](progress-demo.md), and keep the
[exact-build acceptance map](progress-acceptance.md) available for technical questions.
This guide describes delivered capabilities. It does not claim an actual Progress
engagement, independent practitioner approval, production deployment or realized savings.

## A 45-second introduction

> I built a PE value-creation research platform that connects evidence to an
> operating decision. It combines a sourced public-company case with a separately
> labeled operating simulation. Deterministic calculations separate earnings,
> cash and valuation assumptions, while a capacity-constrained plan shows when
> benefits could become available. The central demonstration is that better
> evidence overturns an initially positive case. The system preserves the earlier
> assumptions, reviews and accounting comparisons so a reviewer can explain why
> the recommendation changed. AI can help propose and explain; it cannot approve
> an operating plan. The next validation step is a permissioned company pilot.

## Resume language

Use the two or three bullets that fit the role; keep this under projects unless
it was undertaken within an actual employment relationship.

**PE / commercial analytics emphasis**

- Built an evidence-linked PE value-creation platform combining public-company
  diligence with constructed operating scenarios, separate EBITDA/cash/valuation
  models, and a capacity-constrained 100-day plan.
- Developed an executive review that traces revised contract and vendor evidence
  through forecasts and first-wave selection, preserving prior assumptions,
  accounting comparisons and unassigned measurement residuals.

**Applied AI / software engineering emphasis**

- Engineered typed MCP tools, deterministic Decimal financial calculations and
  immutable PostgreSQL case revisions, with tenant access controls and a separate
  human approval API.
- Built reproducible public research and lifecycle demonstrations with numerical,
  adversarial, persistence, package, Docker and browser validation; optional model
  proposals remain separate from financial arithmetic and operating authority.

If quoting a test count, name its tested release using the acceptance map rather
than treating a historical count as the current suite. If describing individual
contributions, explain the use of AI-assisted implementation and your own role
accurately; this document cannot establish what you personally reviewed or authored.

## Evidence to show for common questions

| Reviewer question | Show | Explain |
|---|---|---|
| What business decision does this improve? | [Executive memo](decision-memo.html) | Whether a proposed first wave merits further diligence given downside, scarce capacity and corrected evidence |
| Is the data real? | [Public baseline](progress-baseline.html), then [operating sources](operating-sources.html) | Issuer facts are public; contracts, vendor records, capacity and observations in the operating exercise are authored. They are not Progress operating data |
| What is the financial model doing? | [Underwriting](underwriting.html) | Monthly earnings, cash timing, costs and downside; calculated public EBITDA is distinct from normalized earnings and fictional operating uplift |
| Why does sequencing matter? | [100-day plan](operating-plan.html) | Dependencies and limited weekly resources change dates and benefit timing; a feasible schedule does not make an adverse case attractive |
| What happens when a source is wrong? | [Source review](source-review.html) | Create a new version, recompute affected economics, reopen the preference and retain the frozen comparison basis |
| How do you prevent counting the same benefit twice? | [Allocation review](allocation-review.html) | Explicit population/shared-cost rules and mutually exclusive selection; this is a separate example with its own assumptions |
| What was actually realized? | [Measurement history](lineage-review.html) | Only constructed observations and claims exist; reconciliation leaves residuals, and claim totals do not prove causality |
| Why use an LLM? | [Architecture](../architecture.md) | Optional proposals and explanations over typed tools; default replay requires no live model. Do not claim demonstrated model superiority |
| How is approval protected? | [Local quickstart](quickstart.md), [architecture](../architecture.md) | The application has a separate human approval API; the public case's simulated receipts do not constitute a real person's decision |
| What is missing before a real pilot? | [Sponsor brief](../pilot/permissioned/sponsor-brief.md), [remaining work](remaining-work.md) | Private-input acceptance, an authorized sponsor and records, finance validation, operator decisions and observed periods |

## Defensible claims and limits

The technical result is an inspectable workflow that changes its recommendation
when evidence changes. Present the negative result as a useful finding, not a
failure to produce a large savings number. There is no need to quote a fictional
opportunity amount in a resume bullet.

The public case is retrospective research with stated information limits. Exact
historical publication timing remains unverified. Current transaction value,
normalized earnings, causal company impact and a performed pilot remain unavailable.
Security and CI checks are evidence of tested behavior, not certification or a
claim that a staffed production service exists.

The existing pilot plan requires authenticated staging and live alerting evidence,
plus domain, threat-model and data-processing reviews. A prepared sponsor packet
does not satisfy those entry gates; the completion checklist retains them.

For live interviews, follow the same primary case through all six stops. Open
the shared-pool and fictional Beacon examples only when relevant, and introduce
each as a separate exercise. End with the next evidence request and who would
need to authorize it.
