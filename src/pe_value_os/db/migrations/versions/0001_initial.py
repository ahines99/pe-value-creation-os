"""Initial schema: runs, evidence, findings, opportunities, value cases, plans, approvals, audit (PVC-030).

Also enables row-level security on every company-scoped table (PVC-034) and makes audit_events append-only
for the application role (PVC-033).

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

COMPANY_TABLES = [
    "companies",
    "workflow_runs",
    "evidence",
    "findings",
    "opportunities",
    "value_cases",
    "priority_scores",
    "plans",
    "approvals",
    "audit_events",
]

SCHEMA = """
create table companies (
  company_id text primary key,
  name text not null,
  profile jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table workflow_runs (
  run_id uuid primary key,
  company_id text not null references companies(company_id),
  project_type text not null,
  status text not null,
  current_step text,
  completed_steps jsonb not null default '[]'::jsonb,
  state jsonb not null default '{}'::jsonb,
  idempotency_key text,
  schema_version int not null default 1,
  requested_by text not null,
  reference_date date,
  params jsonb not null default '{}'::jsonb,
  resume_requested_at timestamptz,
  locked_by text,
  locked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (company_id, idempotency_key)
);
create index workflow_runs_status_idx on workflow_runs (status, resume_requested_at);

create table evidence (
  evidence_id uuid primary key,
  company_id text not null references companies(company_id),
  run_id uuid references workflow_runs(run_id),
  source_uri text not null,
  source_type text not null,
  as_of timestamptz,
  retrieved_at timestamptz not null default now(),
  content_hash text not null,
  storage_key text not null,
  size_bytes bigint not null,
  metadata jsonb not null default '{}'::jsonb,
  unique (company_id, content_hash)
);

create table findings (
  finding_id uuid primary key,
  run_id uuid not null references workflow_runs(run_id),
  company_id text not null references companies(company_id),
  finding_type text not null,
  title text not null,
  statement text not null,
  confidence text not null check (confidence in ('low', 'medium', 'high')),
  assumptions jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table finding_evidence (
  finding_id uuid references findings(finding_id) on delete cascade,
  evidence_id uuid references evidence(evidence_id),
  relation text not null check (relation in ('supports', 'contradicts', 'context')),
  primary key (finding_id, evidence_id, relation)
);

create table opportunities (
  opportunity_id uuid primary key,
  run_id uuid not null references workflow_runs(run_id),
  company_id text not null references companies(company_id),
  lever text not null,
  title text not null,
  baseline_metric text not null,
  baseline_value numeric not null,
  ebitda_flow_through numeric not null,
  flow_through_rule text not null default '',
  scenarios jsonb not null,
  annual_run_cost numeric not null default 0,
  one_time_cost numeric not null default 0,
  confidence text not null,
  rationale text not null,
  assumptions jsonb not null default '[]'::jsonb,
  metric_params jsonb not null default '{}'::jsonb,
  proposer text not null,
  created_at timestamptz not null default now()
);

create table opportunity_evidence (
  opportunity_id uuid references opportunities(opportunity_id) on delete cascade,
  evidence_id uuid references evidence(evidence_id),
  primary key (opportunity_id, evidence_id)
);

create table value_cases (
  value_case_id uuid primary key,
  opportunity_id uuid not null references opportunities(opportunity_id),
  run_id uuid not null references workflow_runs(run_id),
  company_id text not null references companies(company_id),
  annual_ebitda_low numeric not null,
  annual_ebitda_base numeric not null,
  annual_ebitda_high numeric not null,
  one_time_cost numeric not null default 0,
  ev_multiple numeric,
  ev_impact_base numeric,
  calc_version text not null,
  inputs_hash text not null,
  policy_version text not null,
  superseded_at timestamptz,
  created_at timestamptz not null default now()
);
create index value_cases_opportunity_idx on value_cases (opportunity_id, created_at desc);

create table priority_scores (
  run_id uuid not null references workflow_runs(run_id),
  opportunity_id uuid not null references opportunities(opportunity_id),
  company_id text not null references companies(company_id),
  rank int not null,
  score numeric not null,
  components jsonb not null,
  run_rate_ebitda_base numeric not null,
  in_year_ebitda_base numeric not null,
  start_month int not null,
  primary key (run_id, opportunity_id)
);

create table plans (
  plan_id uuid primary key,
  run_id uuid not null references workflow_runs(run_id),
  company_id text not null references companies(company_id),
  status text not null check (status in ('proposed', 'approved', 'rejected', 'superseded')),
  plan jsonb not null,
  approved_plan jsonb,
  created_at timestamptz not null default now(),
  approved_at timestamptz
);

create table approvals (
  approval_id uuid primary key,
  run_id uuid not null references workflow_runs(run_id),
  company_id text not null references companies(company_id),
  artifact_type text not null,
  artifact_id uuid not null,
  decision text check (decision in ('approved', 'rejected', 'changes_requested')),
  decided_by text,
  rationale text,
  edits jsonb not null default '{}'::jsonb,
  diff jsonb not null default '{}'::jsonb,
  requested_at timestamptz not null default now(),
  decided_at timestamptz,
  escalated_at timestamptz
);
create index approvals_run_idx on approvals (run_id, requested_at desc);

create table audit_events (
  event_id bigserial primary key,
  run_id uuid,
  company_id text not null,
  step text not null,
  actor text not null,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index audit_events_run_idx on audit_events (run_id, event_id);
create index audit_events_company_idx on audit_events (company_id, created_at);
"""

RLS_TEMPLATE = """
alter table {t} enable row level security;
alter table {t} force row level security;
create policy {t}_company_scope on {t}
  using (company_id = any (string_to_array(current_setting('pvc.companies', true), ',')))
  with check (company_id = any (string_to_array(current_setting('pvc.companies', true), ',')));
"""

# Child tables without company_id are scoped through their parent.
CHILD_RLS = """
alter table finding_evidence enable row level security;
alter table finding_evidence force row level security;
create policy finding_evidence_scope on finding_evidence
  using (exists (select 1 from findings f where f.finding_id = finding_evidence.finding_id))
  with check (exists (select 1 from findings f where f.finding_id = finding_evidence.finding_id));
alter table opportunity_evidence enable row level security;
alter table opportunity_evidence force row level security;
create policy opportunity_evidence_scope on opportunity_evidence
  using (exists (select 1 from opportunities o where o.opportunity_id = opportunity_evidence.opportunity_id))
  with check (exists (select 1 from opportunities o where o.opportunity_id = opportunity_evidence.opportunity_id));
"""

GRANTS = """
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'pvc_app') then
    grant usage on schema public to pvc_app;
    grant select, insert, update, delete on
      companies, workflow_runs, evidence, findings, finding_evidence, opportunities, opportunity_evidence,
      value_cases, priority_scores, plans, approvals
      to pvc_app;
    grant select, insert on audit_events to pvc_app;
    grant usage, select on sequence audit_events_event_id_seq to pvc_app;
  end if;
  if exists (select 1 from pg_roles where rolname = 'pvc_readonly') then
    grant usage on schema public to pvc_readonly;
    grant select on all tables in schema public to pvc_readonly;
  end if;
end $$;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    for t in COMPANY_TABLES:
        op.execute(RLS_TEMPLATE.format(t=t))
    op.execute(CHILD_RLS)
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute(
        """
        drop table if exists audit_events, approvals, plans, priority_scores, value_cases, opportunity_evidence,
          opportunities, finding_evidence, findings, evidence, workflow_runs, companies cascade;
        """
    )
