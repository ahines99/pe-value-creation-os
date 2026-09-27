# Local package and container acceptance — September 27, 2026

## Follow-up: showcase finalization

The initial results below are retained as historical evidence. Subsequent work replaced the Debian application base with pinned Python 3.12/Alpine 3.24 and produced a local Alpine PostgreSQL image that replaces the upstream obsolete Go-based `gosu` helper with native `su-exec`. Both candidates pass the unchanged HIGH/CRITICAL gate. Package LICENSE/NOTICE files and Apache-2.0 metadata are included. Final committed-SHA CI remains pending.

`scripts/showcase.py up` now builds, configures and seeds the local browser workspace. Real HTTP acceptance passed local sign-in, CSRF negative cases, evidence retrieval, approval, worker resume, KPI definitions and Delta's controlled pause. A later database restart exposed stale pooled connections; connection checkout validation and a real backend-termination regression were added. Live revalidation then returned HTTP 200 on the first API read after database restart. Restarting MCP/API and starting the stopped worker preserved the approval and resumed the run to `complete`. The polling client disconnected during the deliberate API restart, so this was recorded as a separate recovery check, not an uninterrupted HTTP session.

The optional observability profile ran successfully: Prometheus scraped application metrics, Tempo returned 14 application traces from the preceding hour, Grafana provisioned both data sources and its dashboard, and Prometheus discovered Alertmanager. Promtool accepted all nine rules. No external page or email was sent. Separate image scans found 104 HIGH/CRITICAL package findings in Grafana 13.2.2, 12 in Tempo 2.10.8 and two in Alertmanager 0.34.1; Collector 0.161.0 and Prometheus 3.15.0 had none at these severities. These optional-image findings remain unresolved and are not hidden by the passing application/database scans.

Current source validation before the connection-recovery addition: 451 tests passed and one Windows symlink-privilege test skipped, 129 files passed formatting, 87 source files passed type checks. The recovery/infrastructure suite then passed 18 tests. An earlier Alpine installed-artifact run passed 438 tests, with 12 shell-dependent cases skipped because Bash is absent from the runtime image; the Linux symlink case executed. All 39 container evaluation cases passed.

Infrastructure checks ran in pinned Linux tool images: Actionlint, ShellCheck, Terraform formatting/validation for both environments and the module, and all seven mocked-provider tests passed. CI now includes these checks, isolated wheel/demo evaluation, full core Compose HTTP smoke and strict scans for application/database images. Cloud delivery requires `PVC_ENABLE_CD=true`.

Gitleaks 8.30.0 found no leaks in 22 commits or the 352-file publication candidate snapshot. Alex confirmed publication rights and public Apache-2.0 publication. Human MCP acceptance and browser rendering remain open; the automation tool exposes no browser surface. See [the reviewer guide](portfolio/quickstart.md) and [acceptance record](portfolio/acceptance.md).

## Initial run (superseded image, retained for traceability)

The installed package and core Compose workflow worked locally. **The initial Debian image was not release accepted:** its strict Trivy scan failed. Results describe the then-uncommitted worktree, not a released SHA or a fresh GitHub CI run.

## Environment and scope

- Windows x64, Docker Desktop 4.92.0, Engine 29.8.0, Compose 5.5.1, `desktop-linux`, Linux/AMD64 containers; Python 3.12.14 in the application image.
- Repository: <https://github.com/ahines99/pe-value-creation-os>, private, default branch `main`; existing PR #1 targets this repository. No publication, license change, push, merge or AWS deployment was performed.
- Image: `pvc:showcase-local`; Docker image ID reported by inspect: `sha256:9321032105dd8644d1ca277ed98a2a9197a1e214cfd48f36e6f169a067511ab2`. This is local identity evidence, not a registry promotion digest.
- Only synthetic fixtures and the deterministic proposer were used. No paid model calls or customer data.

## Results

| Check | Result |
|---|---|
| Build wheel and source distribution | Passed |
| Install wheel into separate server-only environment, run outside checkout | Demo passed; 39/39 golden/adversarial evaluations passed |
| Build Linux image; run `pvc demo --quiet` with working directory `/tmp` | Passed |
| Compose PostgreSQL role bootstrap and migrations | Passed; migration task exited 0 |
| Core database, MCP, API and worker health | All healthy |
| Synthetic cross-service smoke | Passed: MCP access, persisted evidence, queued run, worker approval checkpoint, review, human-principal rejection and worker resume to `rejected` |
| Targeted demo, fixture, evaluation and infrastructure regression tests | 27 passed |
| Compose configuration, Actionlint and dependency lock check | Passed |
| Changed-file lint/format, full type check and diff whitespace check | Passed; type check covers 87 source files |
| Trivy 0.70.0, HIGH/CRITICAL, including unfixed | **Failed: 44 HIGH findings, zero CRITICAL; eight distinct OS CVEs** |

The Compose smoke used development MCP authentication and an explicitly configured development API approver token. It does not prove production OAuth or browser login. The earlier local staging-mode RSA-token test is recorded separately in [deployment](deployment.md).

## Changes that made these checks possible

The wheel now includes synthetic company fixtures and evaluation data. Runtime code prefers installed assets, with a source-checkout fallback. Docker builds the same package instead of relying on a second fixture copy. CI now installs the wheel into an isolated environment, runs the demo/eval gate outside the checkout, and runs the synthetic demo in the built image.

Core Compose ports bind to loopback and support `PVC_DB_PORT`, `PVC_MCP_PORT` and `PVC_API_PORT`. `PVC_ENV_FILE` selects a local runtime file without editing tracked Compose configuration.

## Scan evidence and next action

The scan used `--scanners vuln --severity HIGH,CRITICAL --exit-code 1`; no `ignore-unfixed` flag or new exception was used. The report identifies Debian 13.7 OS packages; no Python HIGH/CRITICAL findings were reported in this scan. Counts represent package findings, not independent exploit paths.

| CVE | Package findings |
|---|---:|
| CVE-2026-76642 | 9 |
| CVE-2026-78408 | 9 |
| CVE-2026-78409 | 9 |
| CVE-2026-78410 | 9 |
| CVE-2026-54369 | 1 |
| CVE-2025-69720 | 4 |
| CVE-2026-16742 | 2 |
| CVE-2026-9538 | 1 |

No finding listed a fixed version. The image build's OS upgrade step found no available upgrades. These are scanner observations, not conclusions about application exploitability. Next engineering work is to verify upstream advisories and supported base-image options, then rebuild, rerun compatibility checks and rescan. Do not weaken the existing release gate to label this image clean.

Full local evidence is retained in ignored `var/showcase/trivy.json` and `var/showcase/image.tar`; installed evaluation evidence is at `C:\pvc-audit-20260927\installed-eval-report.json`. These machine-local files are not a portable release bundle; CI/release artifact publication remains pending.

## Local reproduction details

The isolated Compose project was `pvc-showcase-check`, with loopback ports 54331 (database), 18000 (MCP) and 18080 (API). An ignored `var/showcase/runtime.env` selected the Beacon fixture, set `MCP_RESOURCE_URL=http://localhost:18000/mcp`, and defined a synthetic approver in `PVC_DEV_TOKENS`. An ignored Compose override selected `pvc:showcase-local` for migrate/MCP/API/worker.

```powershell
$env:PVC_ENV_FILE='var/showcase/runtime.env'
$env:PVC_DB_PORT='54331'
$env:PVC_MCP_PORT='18000'
$env:PVC_API_PORT='18080'
docker compose -p pvc-showcase-check -f docker-compose.yml -f var/showcase/compose.acceptance.yaml up --no-build --wait --wait-timeout 120
```

Seed the synthetic Beacon profile and evidence through `build_context()` and its fixture adapter under `system_principal('beacon-pricing')` before invoking `infra/scripts/smoke_authenticated.py`. Configure `PVC_SMOKE_COMPANY`, the MCP/API URLs and their local smoke tokens. The script deliberately rejects the plan and verifies resume; the in-process demo separately exercises approval and KPI activation.

After testing, the isolated stack was stopped with Compose `down`; its synthetic data volumes and local image/evidence were retained. Docker Desktop remains available.

Optional observability services, restart/recovery, remote CI, image release acceptance and a human MCP/browser session remain open. See the [portfolio roadmap](portfolio-finalization-roadmap.md) for implementation and owner actions.
