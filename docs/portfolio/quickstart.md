# Review the project in ten minutes

This walkthrough is for PE operating partners, investment professionals and portfolio-company executives, with a technical diligence path for engineering reviewers. Review a synthetic investment case, inspect the evidence, make a decision and follow its execution record. No realized customer savings or production acceptance are claimed.

For a two-minute read-only introduction, open the [project introduction](../index.html), [portfolio overview](examples/workspace.html), [Beacon investment memo](examples/beacon-pricing.html), [execution KPIs](examples/beacon-kpis.html) and [Delta evidence pause](examples/delta-broken.html). Those captures cannot submit decisions.

## Run the five-scenario demonstration

Install Python 3.12+ and uv, then from a checkout of the reviewed commit:

```sh
uv sync --frozen --extra dev
uv run pvc demo
uv run pvc eval --suite all --gate
```

The demo needs no database, cloud account or model key. Its Markdown report appears at `var/demo-report.md`. Review a success path, human-principal approval, missing evidence, partial failure and recovery. The approval in this automated command is simulated; it does not replace a real human acceptance session.

## Open the actual review workspace

Start Docker Desktop with Linux containers, then run:

```sh
python scripts/showcase.py up
```

The command builds the application, starts PostgreSQL and migrations, generates a local approver token, seeds two fictional companies and waits for the worker. Open **http://localhost:18081/** and enter the token printed by setup. You can also copy only the token value from ignored `var/local-showcase/settings.json`, without quotes. An unsuccessful sign-in returns to the form with recovery instructions; use the saved local token and try again.

1. **Portfolio overview.** Find Beacon and Delta, compare their workflow states, and use the decision desk to identify the next review. Company cards prioritize the latest run; history remains available for context.
2. **Beacon investment memo.** Review the base annual run-rate and in-year opportunity, workstream owners and initiative contribution. Expand technical detail to inspect the calculation assumptions; the downside scenario matters as much as the headline.
3. **Evidence room.** Follow a cited source from the memo. Inspect its provenance and content, then return to the same decision context. Treat all source records as fictional fixture data.
4. **Human decision.** Approve, request changes with a rationale, or reject. Read any validation feedback; correct the form and resubmit. Approval activates the scoped plan's KPIs after the worker resumes. Refresh to inspect the resulting run status.
5. **Execution and KPIs.** Follow the memo's KPI link to retain the selected run context. Read baseline, day-100 target, run-rate target and any observations together. Missing observations should remain explicit; approval alone proves no business outcome.
6. **Delta's evidence pause.** Review the named missing or stale inputs and suspicious-content findings. A credible process stops when the fact base is insufficient.

The redesigned application presents executive summaries first and places identifiers, formulas and provenance in supporting detail. Use the keyboard to inspect focus order, and narrow the viewport to check that decisions and evidence remain usable. Record any confusing language or visual defect in the human acceptance feedback.

Create fresh runs for another decision path with `python scripts/showcase.py seed`. Existing runs and evidence remain available. Local sign-in lasts one hour in the browser; setup's token remains in ignored `var/local-showcase/settings.json`. Never use this dev configuration for an internet-facing service.

Stop services while retaining synthetic data:

```sh
python scripts/showcase.py down
```

To deliberately erase only this showcase project's synthetic volumes:

```sh
python scripts/showcase.py reset --confirm-reset pvc-showcase
```

Ports are loopback-only: database 54332, MCP 18001, API 18081. The project is named `pvc-showcase`, separate from ordinary `docker compose` development. A second local stack can run on different ports. If a port is occupied, stop the conflicting local test service before starting this one.

The local database now uses Alpine and a separate `pgdata_alpine` volume. Older Debian-created `pgdata` volumes are retained and are not automatically reused: libc/locale differences require a logical `pg_dump`/restore into the fresh cluster for data you want to preserve. The setup seeds new synthetic runs without deleting the old volume. Never reuse an old database directory across this base-image change.

Optional telemetry: `python scripts/showcase.py up --observability` starts Grafana on 3000, Prometheus on 9090 and Alertmanager on 9093. These images have a separate scan/acceptance record; see [container acceptance](../container-acceptance.md) before enabling them. Grafana's local account is `admin`; set `PVC_GRAFANA_PASSWORD` before first startup. No external alert receiver is configured.

## Connect an MCP client

Follow [the pinned client installation instructions](../skills_distribution.md). The bundled stdio configuration explicitly selects the fixture adapter, deterministic rules and four synthetic company scopes. It installs the server extra and needs no provider API key. Its in-memory state is separate from the Docker browser workspace; use the HTTP MCP endpoint at `http://localhost:18001/mcp` for the same persisted showcase runs.

Record your actual human session using [the acceptance checklist](acceptance.md). Scripted checks are engineering evidence; they are not attributed to you.
