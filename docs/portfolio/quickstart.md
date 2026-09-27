# Review the project in ten minutes

This showcase is for technical hiring managers and applied-AI leaders. It demonstrates governed workflows over fictional PE portfolio-company data. It makes no claim of realized customer savings or production acceptance.

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

The command builds the application, starts PostgreSQL and migrations, generates a local approver token, seeds two fictional companies and waits for the worker. Open **http://localhost:18081/** and enter the token printed by setup.

1. Open Beacon's **Review plan and evidence** link. Inspect low/base/high value cases and follow an evidence link.
2. Approve a plan, request changes with a rationale, or reject it. Approval activates the plan's KPIs after the worker resumes; reload the workspace to inspect the resulting status.
3. Open **View KPIs** to inspect the approved definitions. Definitions are not proof of realized performance; observations require a later monitoring run.
4. Open Delta to inspect the explicit `needs evidence` pause. The system records suspicious content rather than treating it as instructions.

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
