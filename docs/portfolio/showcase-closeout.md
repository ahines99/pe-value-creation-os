# Showcase closeout and next-phase boundary

> **For current status, see [STATUS.md](../STATUS.md).** This file is kept as the history of the v0.1.0 showcase closeout; where it differs from STATUS.md, STATUS.md is right.

Decision date: September 27, 2026 (America/New_York). Release code:
`31ebfe9938d6fe92232749632eba5224c0eaffaa`, version `0.1.0`.

Alex instructed: "I would like you to use your recommendations on any of my inputs
for the time being. Go ahead and finalize the goal and continue with the 5 research
agents." This supersedes waiting for routine design, client and company-selection
decisions. The portfolio engineering goal closes using the existing verified
build and delegated editorial judgment. It does not assert that Alex performed
the previously proposed full client walkthrough or that a practitioner validated
the financial case.

## Completed scope

- Public Apache-2.0 code, executive synthetic showcase, static portfolio, case
  study, walkthrough, evidence views, human decision boundary and KPI monitoring.
- Exact-release CI: all ten checks passed; 499 tests on each supported Linux
  Python version, 39 evaluations, 18 rendered browser checks, installed-package
  and Compose acceptance, infrastructure validation and core security scans.
  [Build evidence](../releases/0.1.0/evidence.md).
- Private financial-statement research workflow with source lineage, revision
  handling, issuer reconciliation, candidate peers and a diligence memo.
- Claude Code selected as the primary client. Version 2.1.280 was inspected;
  the plugin was installed locally from a detached release checkout, its six
  skills enumerated, and its stdio MCP health check passed. The separate
  `pvc-showcase` HTTP connection to the persisted Docker workspace also passed.
  These are agent-performed installation and connection checks, not a model
  conversation or a human skill session.
- Progress Software selected as the first research case by delegated judgment.
  Attended LSEG access now works; same-period annual revenue and GAAP operating
  income matched the issuer's figures in a private two-field check. This is
  supplemental current-vintage evidence, not full vendor or peer validation.
  Access is distinct from permission to redistribute licensed data.

## Accepted limits and deferred validation

| Item | Closeout treatment | What would establish the stronger claim |
|---|---|---|
| New visual direction | Agent recommendation accepted as the working direction under Alex's delegation | Actual user feedback; no invented usability acceptance |
| Full human MCP/browser walkthrough | Deferred from this showcase closeout; original unchecked history retained | Dated real participant/client/build record |
| Financial/business usefulness | Research method only; no independent attestation | Finance/practitioner review and documented disagreements |
| Operating evidence and realized value | Fictional showcase or clearly constructed research exercise | Permissioned operating records, intervention and reconciled actuals |
| Hosting, paid model evaluation, production | Outside this completed showcase goal | Separately authorized scope, costs, access and original production gates |

Earlier documents' open human gates remain factual history. This decision changes
the showcase stopping point; it does not mark those tests as passed or close the
original production tickets. Optional telemetry-image findings remain disclosed.
No customer adoption, realized savings, independent security certification or
production readiness is claimed.

## Next work

The [operating-partner roadmap](../operating-partner-roadmap.md) consolidates five
research agents' findings into one delivery sequence. Codex owns the research,
implementation, financial model, integration, public case, testing and review
packet. Nondelegable participation is needed only when claiming actual company
authorization, management decisions, independent review or observed outcomes.

Claude Code's plugin stdio server is an isolated fixture workspace. Use
`pvc-showcase` when a task must share runs with the Docker browser at
`http://localhost:18081/`. The local approval token is for the browser, not a
vendor credential and not a model's authority to approve a plan. New terminals
pick up the installed `uv` command; restarting an already-running client may be
necessary after its environment changes.
