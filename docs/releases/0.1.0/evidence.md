# 0.1.0 showcase release: evidence index

## Released showcase: 31ebfe9

The `v0.1.0` showcase release targets **31ebfe9938d6fe92232749632eba5224c0eaffaa**.
All ten jobs in [the exact-commit CI run](https://github.com/ahines99/pe-value-creation-os/actions/runs/36367128767)
passed: **499 tests on each of Python 3.12, 3.13 and 3.14**, **39/39 deterministic
evaluations**, **18 rendered browser checks**, installed-package and Compose
acceptance, infrastructure checks, dependency/secret scans and zero HIGH/CRITICAL
findings in the application and local PostgreSQL images.

The release assets were assembled from that run: wheel, source distribution,
source/plugin ZIP, CI evidence ZIP with browser screenshots, candidate manifest,
release notes and SHA256SUMS. Distribution hashes were checked against CI;
uploaded asset digests were checked against the local bundle. The manifest records
the tested image IDs. See the [candidate manifest](candidate-manifest.json) and
[asset checksums](SHA256SUMS). The source, wheel and source distribution are
unchanged from the verified candidate. Closeout metadata, release notes and the
evidence archive manifest were updated to record the delegated release decision.

The source archive and packages exclude local credentials, licensed vendor extracts
and private research reports. The package includes the new financial-statement
research workflow; the shipped operational examples remain synthetic. The research
pilot is not independently accepted and LSEG values do not enter its calculations.

**Closeout decision:** Alex authorized delegated recommendations and finalization
on September 27, 2026. The [closeout record](../../portfolio/showcase-closeout.md)
defers the full human MCP/usability session from the showcase stopping point.
Automated checks are not relabeled as human acceptance. Independent finance
review remains open. PE operating partners and executives are the primary
audience, with technical diligence throughout. This is not a production release.

The following sections preserve earlier verification history. Their commits and
counts do not describe the current draft assets.

## Historical executive workspace update

All ten [redesign CI checks](https://github.com/ahines99/pe-value-creation-os/actions/runs/36363935682) passed at `c5d4739`: **479 tests on each of Python 3.12, 3.13 and 3.14**, **39/39 evaluations**, **18 rendered browser checks**, installed-package and Compose acceptance, infrastructure validation, and security/container scans. [PR #11](https://github.com/ahines99/pe-value-creation-os/pull/11) merged as `3a5c7a9`.

The merged update includes [rendered screenshots](../../portfolio/screenshots/workspace-1440.png) and [browser results](../../portfolio/screenshots/browser-checks.json). Earlier draft-release assets below remain tied to their original candidate; they are not silently relabeled as this redesign. Human new-design/MCP acceptance and final release promotion remain separate.

## Verified engineering baseline

Commit **9f9b95f4a0bd94cbb6ddcc4ee3ef79dca9c02e18** passed all ten jobs in [GitHub Actions run 36359188626](https://github.com/ahines99/pe-value-creation-os/actions/runs/36359188626) on September 27, 2026.

| Check | Evidence and scope |
|---|---|
| Python 3.12 / 3.13 / 3.14 | 453 tests passed on each Linux runner; PostgreSQL 18 and migration round trips included; no Windows symlink skip on Linux |
| Lint/types/skills | Ruff, formatting, type checks and skills lint passed |
| Deterministic evaluation | All 39 golden/adversarial cases passed; `eval-report` artifact |
| Installed distribution | Wheel installed into an isolated environment outside checkout; demo and evaluation gate passed; `installed-package-evidence` artifact |
| Core Docker Compose | Fresh build, role bootstrap, migrations, synthetic seed, session/CSRF/evidence/approval/worker/KPI/missing-data checks passed; `compose-acceptance` artifact |
| Application and local database images | Trivy 0.70.0, HIGH/CRITICAL including unfixed: zero findings in both; `image-vulnerability-report` artifact |
| Infrastructure | Pinned Actionlint, ShellCheck, Terraform formatting/validation, seven mocked-provider runs, Compose and Prometheus alert-rule checks passed |
| Secrets/dependencies | Gitleaks and strict Python dependency audit passed; secret-scan SARIF artifact |

These are the CI artifacts shown on that run, not reports from a different historical commit. Download them while retained by GitHub Actions. The `release-distributions` artifact contains the wheel, source distribution and SHA256SUMS. Final release attachments and checksums must be taken from the selected release SHA's successful run; they are not inferred from this earlier baseline.

## Independent local checks

A detached checkout at `48459ba` was created outside the working repository. `uv sync --frozen --extra dev`, the five-scenario demo and the full evaluation gate passed. A separately installed wheel also passed outside the source checkout during packaging remediation.

The live local recovery exercise stopped the worker, recorded an approval, restarted PostgreSQL, MCP and API, then started the worker. The first API read after the database restart returned HTTP 200 and the approved run subsequently reached `complete`. An uninterrupted post-restart HTTP smoke passed separately. Details and the initial failures are preserved in [container acceptance](../../container-acceptance.md).

Optional telemetry runtime checks confirmed application metrics in Prometheus, traces in Tempo, Grafana provisioning and Alertmanager discovery. A synthetic approval-age metric then fired the Prometheus rule, reached local Alertmanager and resolved after reset. These checks **do not certify the optional images**: Grafana, Tempo and Alertmanager retain HIGH/CRITICAL findings, documented in container acceptance. No external alert notification was sent.

## Historical publication and acceptance boundaries

Alex confirmed ownership/publication rights and authorized a public Apache-2.0 showcase. The technical audience is hiring managers and applied-AI leaders. The [case study](../../portfolio/case-study.md), [static portfolio](../../index.html), captured review/evidence views, [walkthrough](../../portfolio/quickstart.md), license, notices and maintainer guides form the publication package.

Actual human MCP acceptance and rendered browser review remain pending in [the acceptance record](../../portfolio/acceptance.md). Captured HTML is genuine application output; it is not a screenshot or proof of rendered usability. No customer ROI, independent security sign-off, current live-provider acceptance, deployed AWS acceptance or production launch is claimed.

Cloud delivery remains disabled unless `PVC_ENABLE_CD=true`; paid nightly model evaluation has its own opt-in. The [production roadmap](../../portfolio-finalization-roadmap.md) retains the owner inputs and gates required after the showcase.
