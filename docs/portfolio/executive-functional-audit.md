# Executive workspace functional audit

> **For current status, see [STATUS.md](../STATUS.md).** This file is kept as the September 27 executive workspace audit; where it differs from STATUS.md, STATUS.md is right.

## Published engineering verification

All ten [redesign CI checks](https://github.com/ahines99/pe-value-creation-os/actions/runs/36363935682) passed at `c5d4739`: **479 tests on each of Python 3.12, 3.13 and 3.14**, **39/39 evaluations**, **18 rendered browser checks**, installed-package and Compose acceptance, infrastructure validation, and security/container scans. [PR #11](https://github.com/ahines99/pe-value-creation-os/pull/11) merged as `3a5c7a9`.

Verified 2026-09-27 America/New_York (2026-09-28 UTC). The redesigned workspace was tested through FastAPI's HTTP test client using fictional company data, the real diagnostic workflow, repository-backed approval records and a temporary filesystem evidence store. Tests did not use the live showcase database or browser.

Current direction is PE operating partners and portfolio-company executives first, with technical diligence available through disclosures and source views. Alex rejected the earlier visuals; this substantial redesign now has fresh engineering rendered evidence; human approval of the new design remains open.

The combined `tests/test_api.py`, `tests/test_executive_ui.py` and `tests/test_portfolio_integration.py` run passed **39 targeted tests**. The executive suite alone previously passed **19 tests** in 18.01 seconds. The deterministic evaluation gate passed **39/39 cases**. The full Windows regression completed with **478 passed and one symlink-privilege skip in 176.21 seconds**. PostgreSQL was enabled through a local administrator connection to an isolated disposable test database. Ruff checks across 135 files and mypy checks across 90 source files passed. These results describe the current local worktree, not a new CI run, final release or rendered screenshots; historical candidate CI remains tied to its recorded SHA.

Independent integration checks also cover a queued company without intake, an empty authorized portfolio, evidence context from another accessible company, bounded CSV preview with exact original bytes, duplicate decisions and rejection of development-session cookies in production. Ruff and formatting checks passed for the executive test module.

## Decision integrity

| Journey | Verified behavior |
|---|---|
| Approve / reject | Browser form persists a human decision; worker resume completes or rejects the run. Rejection creates no KPI definitions. Decision controls disappear after submission. |
| Duplicate submission | A repeated browser submission returns a recoverable HTML validation error and creates no second decision event. |
| Approve with exclusions | Retained initiative values sum to the authoritative approved scope. Both the review headline and portfolio total reflect edits before worker processing and after completion. Excluded value cases remain identifiable as outside the total; removed KPIs do not activate. |
| Request changes | Selected initiatives map to exclusions. Resume supersedes the original plan and creates a new review round with recalculated totals. That revised plan can then be approved. |
| Forged exclusions | Unknown IDs and an opportunity belonging to another run of the same company are rejected without recording a decision or decision audit event. |

The tests compare canonical Decimal values. Original drafted plan totals use cents; retained initiative and edited-plan values may carry additional internal precision. Display formatting is separate from the canonical values used by the assertions.

## Browser recovery and authorization

Missing rationale, missing or invalid decisions, and expired CSRF tokens return HTML feedback. Relevant submitted rationale/selection is preserved, and a fresh form permits recovery. No failed attempt changes approval state.

Analysts, model principals and human tokens issued to an unauthorized client can read an authorized plan but do not receive decision forms. Direct approval requests by those identities remain forbidden. Another company's identity cannot access the review, evidence or KPI view.

The evidence preview escapes source text and metadata; injected script and event-handler payloads do not become active HTML. The original-evidence endpoint still returns the exact stored bytes and hash under company scope. Financial and evidence responses retain `Cache-Control: no-store`.

## Portfolio and operating performance

- Portfolio totals include each company's latest assessment once. Historical run links remain available without adding historical values to the current total.
- Different company currencies produce separate totals; the interface does not silently sum them or invent an exchange rate.
- A run-filtered scorecard displays that run's KPI definitions and observations, including definitions superseded by a newer approved plan. It does not substitute the latest run's metrics.
- The same filter rejects a run belonging to another company even when the caller can access both companies.
- Ratio, duration and ticket-volume metrics retain their meaning: fractions display as percentages, payback as months, and ticket rates as tickets per customer per month. An approved target with no observation is explicitly unobserved.

## Read-only runtime and capture checks

The running local Docker stack returned HTTP 200 with `Cache-Control: no-store` for the portfolio, approved Beacon plan review, exact-run KPI view, Delta controlled-failure view and evidence preview. These checks inspected existing state without submitting a live decision. Local links and anchors were validated across 15 HTML captures. Captured application HTML is not a rendered screenshot or proof of visual usability.

Rendered engineering checks are recorded below; human accessibility/usability and release acceptance remain open. Any subsequent changes require checks appropriate to those changes; the results above are evidence for the tested worktree rather than a claim that every future revision passed.

## Reproduce

```powershell
.venv/Scripts/python.exe -m pytest tests/test_api.py tests/test_executive_ui.py tests/test_portfolio_integration.py -q --tb=short --show-capture=no
.venv/Scripts/ruff.exe check tests/test_executive_ui.py
.venv/Scripts/ruff.exe format --check tests/test_executive_ui.py
```

This test result does not certify pixel layout, browser accessibility, live identity-provider behavior, PostgreSQL deployment, source connectors or AWS. Those require the separate visual, integration and deployment checks. The suite verifies the redesigned HTTP and domain behavior with isolated synthetic state.


## Rendered browser evidence

`scripts/check_portfolio_browser.py` passed **18 page/viewport checks** in isolated Linux Chromium 153.0.8010.12 in Docker: public landing, workspace, Beacon memo, Delta controlled failure, operating performance and evidence at **1440, 768 and 375 pixels**. Collapsed and expanded disclosures produced no horizontal overflow. Keyboard checks covered skip-link focus and native disclosure activation. The main element's focus target was corrected using `tabindex`.

The coordinator inspected the actual screenshots. Evidence: [machine-readable browser results](screenshots/browser-checks.json), [desktop workspace](screenshots/workspace-1440.png), [mobile workspace](screenshots/workspace-375.png), [Beacon memo](screenshots/memo-1440.png), [expanded evidence](screenshots/memo-evidence-detail.png), [Delta](screenshots/gaps-1440.png), [KPIs](screenshots/performance-1440.png) and [public landing](screenshots/landing-1440.png).

These checks render captured synthetic application output; they do not automate decisions in a live user session or constitute comprehensive accessibility certification. The unreliable native Windows connector no longer blocks engineering rendering. Human new-design approval and the remaining MCP/browser session remain pending; all ten redesign CI checks passed at `c5d4739`. No final release is claimed. The 478-pass/one-skip full-suite result is unchanged; All 39 targeted API/UI/integration tests passed again after the final fixes. The local API, MCP and worker were rebuilt and report healthy.
