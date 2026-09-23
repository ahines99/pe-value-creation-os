# Portfolio company onboarding playbook (PVC-155)

For the engineer and the operating-team member onboarding a portfolio company. Work through the steps in order. Each step ends with a check you can verify. Record the date and the person against each step in the onboarding record at the bottom.

## 1. Data-access agreement

- [ ] Agreement signed by the portfolio company. It covers purpose (value-creation diagnostics), datasets, read-only access, retention period, deletion on exit, and the model provider as a subprocessor ([model_data_handling.md](../model_data_handling.md)).
- [ ] Retention period entered in the onboarding record. Offboarding follows [data_retention.md](../data_retention.md) (`pvc offboard --company ID --confirm`).
- [ ] Company id chosen: lowercase, hyphenated, stable (for example `acme-portco`). The same id is used in tokens, configuration and the database.

**Check:** the signed agreement is stored where the fund keeps legal documents, and its link is in the onboarding record.

## 2. Source adapters

Warehouse-first (ADR 0008). Use vendor APIs only for datasets the warehouse lacks.

1. List which of the 13 datasets in [data_contracts.md](../data_contracts.md) exist, and where they live.
2. For warehouse sources, create the `pvc_<dataset>` views in the company's schema, following the column contracts in `data_contracts.md`.
3. Issue read-only credentials. Store them in Secrets Manager. The configuration holds only the environment-variable names.
4. Add the company to the `PVC_SOURCES_CONFIG` file ([sources.example.toml](../sources.example.toml)), including `id_systems` for customer-keyed datasets. Leave `accept_name_matches = false` unless the operating team accepts name-only matches.
5. Add every vendor API host to `PVC_EGRESS_ALLOWLIST`.

**Check:** `PVC_SOURCE_ADAPTER=composite uv run pvc onboard-check --company <id>` loads every expected dataset, with `row_errors` at 0 or explained.

## 3. Sufficiency baseline

```bash
uv run pvc onboard-check --company <id> > onboarding/<id>-baseline.json
```

The command is read-only. It stores nothing and starts no run. It exits 0 when at least `run.min_sufficient_analyses` analyses are supported, and 2 otherwise. Review with the operating team:

- `sufficient_analyses`: which of unit economics, pricing, retention and AI opportunity can run.
- `gaps`: each has a code, a dataset and a detail. Decide for each one: fix at the source, accept (runs will need `pvc resume --accept-gaps`, which is recorded), or leave that analysis out of scope.
- `stale_datasets`: anything older than the policy freshness window.
- `entity_resolution`: duplicates merged, and unresolved or name-only matches waiting for review.

**Check:** the command exits 0, and every remaining gap has a decision in the onboarding record.

## 4. Approvers and access

- [ ] In the identity provider, grant `pvc_companies: ["<id>"]` to the deal team and operating partner. Grant `pvc_roles: ["approver"]` only to the named approvers, all with `pvc_principal_type: "human"`.
- [ ] Analysts get `pvc_roles: ["analyst"]` and the same company scope.
- [ ] Escalation contact confirmed in policy (`approval.escalation_contact`), and `approval.expiry_hours` agreed.
- [ ] Add the company to `PVC_WORKER_COMPANIES` so the worker picks up its runs and KPI refreshes.
- [ ] Run `uv run pvc access-review --grants <export.json>` and confirm that only the intended people can see the company.

**Check:** an approver can open `/runs/<run_id>/review` for this company and gets 404 for any other company's runs (out-of-scope records are reported as not found, so their existence is not revealed).

## 5. First run

```bash
uv run pvc run --company <id>
uv run pvc status <run_id>
```

- [ ] Engineering reviews the run summary (`run://<run_id>/summary`) before the approvers see it.
- [ ] Approvers review in the review UI and decide with a written rationale.

**Check:** the run reaches `awaiting_approval`, or pauses at `needs_evidence` only for gaps already recorded in step 3.

## 6. KPI cadence

- [ ] On approval, KPIs activate automatically from the plan. Confirm the owners and targets with the operating team.
- [ ] Agree the refresh cadence (default `kpi.default_cadence_days = 30`) and the off-track tolerance (`kpi.off_track_tolerance`).
- [ ] Choose the digest recipients. `uv run pvc kpi digest --company <id>` produces the digest, and the worker sends it on the cadence.

**Check:** the first `pvc kpi refresh --company <id>` records an observation for every KPI.

## Onboarding record

| Step | Done by | Date | Notes and links |
|---|---|---|---|
| 1. Data-access agreement | | | |
| 2. Source adapters | | | |
| 3. Sufficiency baseline | | | |
| 4. Approvers and access | | | |
| 5. First run | | | |
| 6. KPI cadence | | | |

## Companies onboarded with this playbook

| Company | Date | Notes |
|---|---|---|
| (pilot company) | | PVC-153 |
| (second company) | | Required to close PVC-155 |
