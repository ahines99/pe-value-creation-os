"""KPI monitoring and notification outbox (PVC-120..123).

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TABLES = ["kpi_definitions", "kpi_observations", "kpi_alerts", "notifications"]

SCHEMA = """
create table kpi_definitions (
  kpi_id uuid primary key,
  company_id text not null references companies(company_id),
  plan_id uuid not null references plans(plan_id),
  run_id uuid not null references workflow_runs(run_id),
  metric text not null,
  metric_params jsonb not null default '{}'::jsonb,
  description text not null,
  baseline numeric not null,
  day_100_target numeric not null,
  run_rate_target numeric not null,
  direction text not null check (direction in ('increase', 'decrease')),
  cadence_days int not null check (cadence_days > 0),
  source text not null,
  evidence_ids jsonb not null default '[]'::jsonb,
  start_date date not null,
  active boolean not null default true,
  created_at timestamptz not null default now()
);
create index kpi_definitions_company_idx on kpi_definitions (company_id, active);

create table kpi_observations (
  observation_id uuid primary key,
  kpi_id uuid not null references kpi_definitions(kpi_id),
  company_id text not null references companies(company_id),
  observed_at timestamptz not null,
  period_end date,
  value numeric not null,
  target numeric not null,
  status text not null check (status in ('on_track', 'off_track')),
  variance numeric not null,
  evidence_ids jsonb not null default '[]'::jsonb
);
create index kpi_observations_kpi_idx on kpi_observations (kpi_id, observed_at);

create table kpi_alerts (
  alert_id uuid primary key,
  kpi_id uuid not null references kpi_definitions(kpi_id),
  company_id text not null references companies(company_id),
  observation_id uuid not null references kpi_observations(observation_id),
  rule text not null check (rule in ('threshold', 'trend')),
  detail text not null,
  created_at timestamptz not null default now()
);

create table notifications (
  notification_id uuid primary key,
  company_id text not null references companies(company_id),
  channel text not null,
  subject text not null,
  body text not null,
  created_at timestamptz not null default now(),
  delivered_at timestamptz,
  status text not null default 'pending'
);
"""

RLS = """
alter table {t} enable row level security;
alter table {t} force row level security;
create policy {t}_company_scope on {t}
  using (company_id = any (string_to_array(current_setting('pvc.companies', true), ',')))
  with check (company_id = any (string_to_array(current_setting('pvc.companies', true), ',')));
"""

GRANTS = """
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'pvc_app') then
    grant select, insert, update, delete on kpi_definitions, kpi_observations, kpi_alerts, notifications to pvc_app;
  end if;
  if exists (select 1 from pg_roles where rolname = 'pvc_readonly') then
    grant select on kpi_definitions, kpi_observations, kpi_alerts, notifications to pvc_readonly;
  end if;
end $$;
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    for t in TABLES:
        op.execute(RLS.format(t=t))
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute("drop table if exists notifications, kpi_alerts, kpi_observations, kpi_definitions cascade;")
