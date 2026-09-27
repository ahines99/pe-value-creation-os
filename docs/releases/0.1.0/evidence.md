# 0.1.0 showcase candidate: evidence index

## Verified engineering baseline

Commit **48459bab86954e6e9b75bad2936bbe5afcb8600a** passed all ten jobs in [GitHub Actions run 36358720925](https://github.com/ahines99/pe-value-creation-os/actions/runs/36358720925) on September 27, 2026.

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

These are the CI artifacts shown on that run, not reports from a different historical commit. Download them while retained by GitHub Actions. Final release attachments and checksums must be taken from the selected release SHA's successful run; they are not inferred from this earlier baseline.

## Independent local checks

A detached checkout at `48459ba` was created outside the working repository. `uv sync --frozen --extra dev`, the five-scenario demo and the full evaluation gate passed. A separately installed wheel also passed outside the source checkout during packaging remediation.

The live local recovery exercise stopped the worker, recorded an approval, restarted PostgreSQL, MCP and API, then started the worker. The first API read after the database restart returned HTTP 200 and the approved run subsequently reached `complete`. An uninterrupted post-restart HTTP smoke passed separately. Details and the initial failures are preserved in [container acceptance](../../container-acceptance.md).

Optional telemetry runtime checks confirmed application metrics in Prometheus, traces in Tempo, Grafana provisioning and Alertmanager discovery. These checks **do not certify the optional images**: Grafana, Tempo and Alertmanager retain HIGH/CRITICAL findings, documented in container acceptance. No external alert notification was sent.

## Publication and acceptance boundaries

Alex confirmed ownership/publication rights and authorized a public Apache-2.0 showcase. The technical audience is hiring managers and applied-AI leaders. The [case study](../../portfolio/case-study.md), [static portfolio](../../index.html), captured review/evidence views, [walkthrough](../../portfolio/quickstart.md), license, notices and maintainer guides form the publication package.

Actual human MCP acceptance and rendered browser review remain pending in [the acceptance record](../../portfolio/acceptance.md). Captured HTML is genuine application output; it is not a screenshot or proof of rendered usability. No customer ROI, independent security sign-off, current live-provider acceptance, deployed AWS acceptance or production launch is claimed.

Cloud delivery remains disabled unless `PVC_ENABLE_CD=true`; paid nightly model evaluation has its own opt-in. The [production roadmap](../../portfolio-finalization-roadmap.md) retains the owner inputs and gates required after the showcase.
