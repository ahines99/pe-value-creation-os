# Deployment

This document covers M13 (PVC-130 to PVC-136), the network half of PVC-094 (egress allow-list) and the container scan in PVC-096.

> **Status: not yet applied.** The Terraform and the CD pipeline are written and validated offline, and the image builds and passes the Trivy scan in CI. No AWS account has been connected, so:
> - nothing has been provisioned (`terraform plan`/`apply` has not run against AWS);
> - the CD workflow has not run.
>
> Offline checks that passed: `terraform fmt -check -recursive`; `terraform init -backend=false` and `terraform validate` in both environment roots; the mocked-provider module tests (`infra/terraform/modules/pvc/tests`, 5 runs including the security controls); `actionlint` with shellcheck on every workflow; `shellcheck` on `infra/scripts/*.sh`.
> Treat the first staging apply as the real test, and update this note once it has run.

## Layout

| Path | What it is |
|---|---|
| `Dockerfile`, `.dockerignore` | One image for every process. uv build stage, slim runtime, non-root user (uid 10001), runtime extras only. |
| `.env.example` | Every runtime variable with dev-safe values. `docker compose` loads it. |
| `infra/docker/` | Files baked into the image: `healthcheck.py` (container health check) and `bootstrap_db.py` (role bootstrap task). |
| `infra/terraform/modules/pvc/` | One environment: `network.tf`, `database.tf`, `storage.tf`, `compute.tf`, `ingress.tf`, `iam.tf`, `observability.tf`, `main.tf` (KMS keys), `variables.tf`, `outputs.tf`, `tests/`. |
| `infra/terraform/envs/{staging,production}/` | Environment roots. Each has its own AWS account, its own state backend, and `*.example` files for backend and variables. |
| `infra/scripts/deploy.sh` | Push, one-off tasks, deploy and rollback. CD uses it for `migrate` and deploys; operators also use it for `bootstrap`, with their own credentials. |
| `infra/scripts/smoke.sh` | Post-deploy smoke test. |
| `.github/workflows/cd.yml` | Build, scan, push, migrate, deploy and smoke test. Staging deploys automatically; production waits for approval. |
| `.github/workflows/ci.yml` (`container-scan` job) | Builds the image on every PR, fails on HIGH/CRITICAL vulnerabilities that have a fix, and lists unfixed ones without failing. |

## Architecture (per environment, per AWS account)

```text
Internet ──443──▶ WAFv2 (rate limit, size limit, AWS managed rules)
                   │
                   ▼
            ALB (ingress subnets, TLS 1.2+, HTTP→HTTPS 301)
     host mcp.* ──▶ mcp service  :8000 ─┐
     host approvals.* ─▶ api service :8080 ─┤  ECS Fargate, private app subnets
                         worker service ────┤  (no ingress)
                  migrate / bootstrap / offboard┘  (one-off tasks)
                                            │
             ┌──────────────────────────────┼──────────────────────────────┐
             ▼                              ▼                              ▼
   RDS PostgreSQL 18 (db subnets,   S3 evidence bucket             VPC endpoints:
   KMS, TLS forced, PITR,           (versioning, Object Lock        ECR, S3, Logs,
   no public access)                governance, SSE-KMS, TLS only)  Secrets Manager
                                            │
     all other egress: app subnet ──▶ Network Firewall (domain allow-list) ──▶ NAT ──▶ Internet
```

## Environments

| | Local | Staging | Production |
|---|---|---|---|
| Where | `docker compose up` | Staging AWS account | Production AWS account |
| `PVC_ENV` | `dev` (auth off) | `staging` (auth required) | `prod` (auth required) |
| Deploys | manual | every push to `main` (CD) | CD, after approval on the `production` GitHub environment |
| Availability zones | n/a | 2 | 3 |
| Database | `postgres:18` container | single-AZ `db.t4g.medium`, 7-day PITR | Multi-AZ `db.m7g.large`, 35-day PITR |
| Deletion protection | n/a | off | on (database, ALB, firewall; secrets keep a 30-day recovery window) |
| Evidence Object Lock | n/a (filesystem) | 30 days | 2555 days (7 years); align with the retention policy (PVC-144) |
| Log retention | n/a | 30 days | 365 days |
| Default task counts (mcp/api/worker) | 1/1/1 | 1/1/1 | 3/2/2 |

Both environments are built from the same module (PVC-136). The provider's `allowed_account_ids` stops a root from running against the other environment's account. Each account has its own state bucket, GitHub OIDC deploy role, KMS keys and secrets. No credentials are shared.

## Local stack

```bash
docker compose up db             # PostgreSQL only (roles created from roles.sql + dev passwords)
docker compose up --build        # db, migrations, MCP server (:8000), approval API (:8080), worker
```

The containers read `.env.example`. To change settings, copy it to `.env` (git-ignored) and edit `docker-compose.yml`'s `env_file`, or export the variables before running outside Docker.

## Prerequisites (once per account)

1. **AWS account** for each environment, and an administrator identity to run Terraform.
2. **State bucket.** Create an S3 bucket in the same account, with versioning, default encryption and public access blocked. Put its name in `backend.hcl` (copy `backend.hcl.example`). Locking uses S3 conditional writes (`use_lockfile`), so no DynamoDB table is needed.
3. **ACM certificate** in the deployment region, covering both hostnames (for example `mcp.staging.example.com` and `approvals.staging.example.com`), issued and validated.
4. **Identity provider.** Register two resources and their clients with the fund's IdP (see `src/pe_value_os/auth.py`):
   - **MCP:** audience `https://<mcp_hostname>/mcp` (or `auth_audience`). Scopes `pvc.read` for access and `pvc.write` for tools that change state.
   - **Approval API:** its own audience, `api_audience` (default `https://<api_hostname>`). An approval UI client whose id goes in `api_client_ids`, with scope `pvc.approve` for approvers only. If you use the ALB sign-in for the review pages (`api_browser_oidc`), that client's access token must be issued for the API audience.
   - Every token carries `pvc_companies`, `pvc_roles` and `pvc_principal_type`. Only humans get `pvc_principal_type: "human"`.
5. **GitHub environments** `staging` and `production`. Give `production` required reviewers, and allow deployments only from `main`. On a private repository this needs GitHub Pro, Team or Enterprise. Without it, the environments carry no protection rules, and the deploy role's trust is the only gate. CD also refuses to deploy anything but `main`.
6. **Tools**: Terraform 1.11 or later (validated with 1.16.4), AWS CLI v2, `jq`, and Docker for the first image push.

## First-time bootstrap order

Run steps 1 to 3 and 7 in `infra/terraform/envs/<env>/`, and steps 4 to 6 and 8 from the repository root. All of them need administrator credentials for that environment's account. Order matters: the database roles must exist before migrations, and migrations must run before the services start.

1. **Terraform apply, no tasks yet.**
   ```bash
   cp backend.hcl.example backend.hcl && cp terraform.tfvars.example terraform.tfvars   # then edit both
   terraform init -backend-config=backend.hcl
   terraform apply            # the example tfvars sets desired_counts = { mcp = 0, api = 0, worker = 0 }
   ```
   This creates the VPC, firewall, RDS, bucket, ECR, ECS cluster, task definitions, services (at zero tasks), ALB, WAF, secrets, roles and alarms. If the account already has a GitHub OIDC provider, set `create_github_oidc_provider = false` and `github_oidc_provider_arn`.
2. **DNS.** Point both hostnames at `terraform output alb_dns_name` (a Route 53 alias uses `alb_zone_id`).
3. **Secret values.** Terraform generates the three database role passwords. Set the other secrets yourself, and only the ones you use:
   ```bash
   aws secretsmanager put-secret-value --secret-id pvc-<env>/app/anthropic-api-key --secret-string "$ANTHROPIC_API_KEY"   # if proposer = "model"
   aws secretsmanager put-secret-value --secret-id pvc-<env>/app/notify-webhook-url --secret-string "$WEBHOOK_URL"        # if notify_webhook_enabled
   ```
4. **First image.** Export the variables from `terraform output github_environment_variables`, then:
   ```bash
   aws ecr get-login-password | docker login --username AWS --password-stdin "${ECR_REPOSITORY_URL%%/*}"
   docker build -t pvc:first .
   IMAGE=$(infra/scripts/deploy.sh push pvc:first)
   ```
5. **Bootstrap roles** (as the RDS master user, with your administrator credentials: the CD role cannot run this task). This creates `pvc_migrator`, `pvc_app` and `pvc_readonly`, sets their passwords from Secrets Manager (sent to PostgreSQL as SCRAM verifiers, so no plaintext reaches the database log), and lets `pvc_migrator` create objects in `public`:
   ```bash
   infra/scripts/deploy.sh run-task bootstrap "$IMAGE"
   ```
6. **Migrate and deploy.** This runs `pvc db upgrade` as `pvc_migrator`, then rolls every service to the image:
   ```bash
   infra/scripts/deploy.sh deploy "$IMAGE"
   ```
7. **Scale up.** Remove the `desired_counts` override from `terraform.tfvars` and run `terraform apply` again. The services keep the task-definition revision set in step 6.
8. **Smoke test:** `MCP_URL=... API_URL=... infra/scripts/smoke.sh`
9. **Wire CD.** Copy every entry of `terraform output github_environment_variables` into the variables of the matching GitHub environment. After this, pushes to `main` deploy staging, and production follows after approval.

## Continuous delivery (PVC-133)

`.github/workflows/cd.yml` runs on every push to `main`, and can also be started manually:

1. **build**: `docker build`, then a Trivy scan (`HIGH,CRITICAL`, fixable only, `exit-code 1`). The job saves the scanned image as a workflow artifact and records its image ID.
2. **deploy-staging** (GitHub environment `staging`):
   - load the artifact and check that its image ID matches the scanned one;
   - assume the staging deploy role through OIDC;
   - push to staging ECR, tagged with the commit SHA (tags are immutable) and deployed by digest;
   - `deploy.sh deploy` runs the `migrate` task, stops if it fails, rolls `mcp`, `api` and `worker`, and waits until each service is stable on the new revision. A circuit-breaker rollback fails the job.
   - `smoke.sh` checks four things:
     - `GET /healthz` returns 200;
     - an unauthenticated MCP `initialize` gets 401 with a Bearer challenge;
     - the OAuth protected-resource metadata is served;
     - HTTP redirects to HTTPS.
3. **deploy-production** (GitHub environment `production`, which requires approval): the same steps, with the same image artifact, against the production account.

There are no static AWS keys anywhere. The deploy role trusts only `repo:<owner>/<repo>:environment:<env>`. It may push to its own ECR repository, register task definitions, update the three services, run the `migrate` task family on its cluster, and pass the service and migrate roles to ECS. It cannot run or pass the roles of `bootstrap` (RDS master secret) or `offboard` (evidence deletion); those are operator actions. Both deploy jobs run only for `main`.

The workflow does not wait for `ci`. Make `ci` a required status check on `main` (branch protection, which needs GitHub Pro on a private repository) so that only green commits reach CD.

### Container scanning (PVC-096)

Two Trivy scans run: `ci.yml` → `container-scan` on every PR and push, and CD `build` before any push. Both fail on HIGH/CRITICAL findings that have a fix available. Unfixed findings do not fail the build, because rebuilding cannot remediate them. A second, non-blocking Trivy step lists them on every CI run; review them as part of dependency upkeep. Every action is pinned to a commit SHA and the base images to digests; Dependabot (`.github/dependabot.yml`) proposes weekly updates. ECR also scans on push.

## Secrets

| Secret (Secrets Manager) | Value set by | Read by (as ECS secret) | Rotation |
|---|---|---|---|
| RDS-managed master secret (`rds!db-...`) | RDS | `bootstrap` only (`PGPASSWORD`) | RDS rotates it. `bootstrap` reads the current value at run time. |
| `pvc-<env>/db/pvc_app-password` | Terraform (write-only) | `mcp`, `api`, `worker` (`PGPASSWORD`); `bootstrap` | Bump `db_role_password_version`, run `terraform apply`, then `deploy.sh run-task bootstrap <image>`, then `deploy.sh deploy <image>` to restart the tasks. |
| `pvc-<env>/db/pvc_migrator-password` | Terraform (write-only) | `migrate`; `bootstrap` | Same procedure as `pvc_app`. |
| `pvc-<env>/db/pvc_readonly-password` | Terraform (write-only) | `bootstrap` | Same procedure as `pvc_app`. Not for people: row-level security binds the application, not a direct database user, who could widen their own scope. Serve reporting through the API or `pvc audit-export`. |
| `pvc-<env>/app/anthropic-api-key` | Operator | `mcp`, `api`, `worker` when `proposer = "model"` | `put-secret-value`, then redeploy. |
| `pvc-<env>/app/notify-webhook-url` | Operator | `worker` when `notify_webhook_enabled` | `put-secret-value`, then redeploy. |

Terraform generates the role passwords with an ephemeral resource and stores them through write-only attributes, so they never appear in plan output or state. Connection URLs carry no password: libpq reads `PGPASSWORD`. All secrets are encrypted with the environment's data KMS key. Each workload's execution role can read only its own secrets.

## Egress allow-list (PVC-094)

**One list feeds both enforcement layers.** The module builds `local.egress_domains` from:

| Source | Variable |
|---|---|
| model provider | `model_provider_host` (default `api.anthropic.com`) |
| identity provider | hosts of `auth_issuer` and `auth_jwks_url` |
| telemetry | host of `otel_exporter_otlp_endpoint` |
| data sources | `data_source_hosts` |
| webhook | `notify_webhook_host` |
| exceptions | `extra_egress_domains` |

That list is enforced twice:

- **Network:** an AWS Network Firewall stateful rule group (`ALLOWLIST` on TLS SNI and HTTP Host, strict rule order, default `drop_established`). Every packet from the app subnets to the internet passes through it.
- **Process:** the same list goes into `PVC_EGRESS_ALLOWLIST` (`src/pe_value_os/egress.py`). A request to any other host fails before it leaves the process.

AWS APIs the platform needs (ECR, S3, CloudWatch Logs, Secrets Manager) go through VPC endpoints and never reach the firewall. The database subnets have no route out of the VPC.

**To add or remove a host:**

1. Open a PR that changes the variable in `envs/<env>/terraform.tfvars` (or the module inputs), and say why in the PR.
   - A leading dot allows subdomains: `.example.com` becomes `*.example.com` for the in-process check.
   - Use exact hosts where you can.
2. After review, run `terraform apply`. The firewall rule group updates in place, and the task definitions get the new `PVC_EGRESS_ALLOWLIST`.
3. Deploy. The next CD run picks up the new list. To apply it now, run `infra/scripts/deploy.sh deploy <current image>`.
4. Check `terraform output egress_allowed_domains`.

**Monitoring.** The `<prefix>-egress-denied` alarm fires when the firewall drops outbound traffic. Alert and flow logs are in `/network-firewall/<prefix>/{alert,flow}`. Data sources that allow-list callers by IP should allow `terraform output nat_public_ips`.

**Limits.**

- The security groups allow outbound TCP 443 only. The telemetry collector and data sources must therefore be reachable over HTTPS on 443. For anything else, open that port explicitly.
- SNI filtering does not decrypt traffic. A process that fakes SNI could reach an allowed name on an IP it does not own. The in-process check and the absence of tools that send email or write to source systems are the other layers. Add Network Firewall TLS inspection if that residual risk is not acceptable.

## Ingress, TLS and limits (PVC-135)

- **TLS:** the ALB's HTTPS listener uses `ELBSecurityPolicy-TLS13-1-2-Res-2021-06`, and HTTP gets a 301 to HTTPS. RDS forces TLS (`rds.force_ssl=1`, TLS 1.2 minimum, and `sslmode=verify-full` against the pinned RDS CA bundle in every URL). The evidence bucket denies non-TLS requests and TLS below 1.2.
- **Routing:** host-based. `mcp_hostname` goes to `mcp`, `api_hostname` goes to `api`, and any other host gets 404. The ALB drops invalid header fields.
- **Rate limiting:** a WAF rate-based rule allows `waf_rate_limit` requests per client IP per 5 minutes (default 1000). A blocked-request spike raises the `<prefix>-waf-blocked-spike` alarm.
- **Request size:**
  - ALB WAF inspects only the first 8 KB of a body, so the limit is enforced on the declared `Content-Length`. The default `max_request_body_bytes = 1000000` blocks any request declaring 1,000,000 bytes or more.
  - The managed `SizeRestrictions_BODY` rule, which would block any body over 8 KB, is set to count.
  - Chunked requests with no `Content-Length` are not caught by WAF. For those, the MCP SDK's own body limit applies.
- **Managed rules:** AWS Common Rule Set and Known Bad Inputs. WAF logs redact the `authorization` and `cookie` headers.
- **Health checks:**
  - `api`: `GET /healthz` must return 200.
  - `mcp`: `GET /.well-known/oauth-protected-resource/mcp` must return 200. That endpoint is served without a token once auth is configured.
  - Containers also run `infra/docker/healthcheck.py`.

## Rollback

- **Automatic.** Every service has the ECS deployment circuit breaker with rollback. A deployment whose tasks fail health checks goes back to the previous revision, and `deploy.sh` then fails the CD job.
- **Application rollback.** Do **not** redeploy an old image with `deploy.sh deploy`. That command runs migrations first, and an old image cannot migrate a database that is already at a newer revision. Point each service back at its previous task-definition revision instead:
  ```bash
  aws ecs list-task-definitions --family-prefix pvc-production-api --sort DESC --max-items 3
  infra/scripts/deploy.sh rollback api arn:aws:ecs:...:task-definition/pvc-production-api:41
  ```
  Repeat for `mcp` and `worker`. This is safe because migrations are written expand-then-contract: a release must keep working against the schema of the release after it.
- **Schema rollback.** Use `pvc db downgrade --revision <target>` as a deliberate operator action (run it as a one-off task with a `migrate` override command), and only when the downgrade does not drop data that is still needed. The command refuses to run without `--revision`; `--revision base` drops the whole schema.
- **Data recovery.** Use RDS point-in-time restore to a new instance within the retention window. The restore drill is PVC-142; the database restore runbook is in `docs/runbooks/`.
- **Infrastructure.** Revert the Terraform change and run `terraform apply`. The database, bucket, ALB and firewall are protected from deletion in production. A plan that wants to replace them needs explicit review.

## Operational notes

- **Configuration drift between Terraform and CD.** Terraform owns the task-definition content. CD owns which revision is running (`ignore_changes = [task_definition]` on the services). `deploy.sh` copies the latest registered revision and changes only the image, so configuration applied by Terraform takes effect on the next deploy.
- **Cost drivers:** Network Firewall endpoints and NAT gateways (one each per AZ), the Multi-AZ database in production, and interface endpoints. Staging uses 2 AZs to reduce cost.
- **Performance Insights** is on, with 7-day retention and the data KMS key. Statement logging covers DDL only, because query text may contain portfolio-company data. `ALTER ROLE ... PASSWORD` is DDL, which is why the bootstrap task sends SCRAM verifiers, never plaintext passwords.
- **Load balancer access logs** go to `<prefix>-alb-logs-<account>` (SSE-S3, which is the only encryption ALB log delivery supports) and expire after `log_retention_days`.
- **Review UI sign-in.** With `api_browser_oidc` set, the ALB signs users in for the review, form, evidence and KPI pages and forwards the IdP access token in `x-amzn-oidc-accesstoken`. The API verifies that token like a bearer token. JSON API clients send `Authorization: Bearer` and do not go through the ALB sign-in.
- **Alarms.** Production requires `alarm_topic_arn`, the SNS topic that pages on-call; staging may leave it empty.
- **Offboarding** runs as the operator-only `offboard` task, whose role alone may delete evidence versions under Object Lock. See `docs/data_retention.md`.

## Application gaps found during infrastructure review (resolved)

The infrastructure review found five application-side gaps. All five are fixed:

1. **MCP host validation.** `create_http_app()` passes `transport_security` built from `PVC_MCP_RESOURCE_URL` and `PVC_MCP_ALLOWED_HOSTS`, so requests to the public hostname are accepted and other Host headers are rejected (DNS-rebinding protection). `tests/test_auth.py` covers both cases.
2. **`boto3`.** It is in the `aws` extra, which the `server` extra includes.
3. **Evidence KMS key.** `S3EvidenceStore` sends `SSEKMSKeyId` from `PVC_EVIDENCE_KMS_KEY_ID`, which Terraform sets to the data key ARN. Without that variable, the store sends no encryption headers, so the bucket default applies.
4. **Migrator privileges.** `roles.sql` grants `usage, create on schema public` to `pvc_migrator`, the same grant `bootstrap_db.py` applies.
5. **Server certificate verification.** The image pins the Amazon RDS CA bundle by checksum at `/app/certs/rds-global-bundle.pem`, and every database URL uses `sslmode=verify-full&sslrootcert=...`. When AWS rotates the bundle, the image build fails on the checksum. Update the `RDS_CA_SHA256` build argument in the `Dockerfile` then.
