"""Append-only constructed observations and explicit attribution claims."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      alter table case_close_baselines add constraint close_observation_identity
        unique(company_id,case_id,baseline_id,content_sha256);
      create table case_observations (
        observation_id uuid primary key,
        company_id text not null,
        case_id text not null,
        baseline_id uuid not null,
        baseline_sha256 text not null,
        period_start date not null,
        period_end date not null,
        sequence integer not null check(sequence > 0),
        previous_id uuid unique,
        ingestion_key text not null,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        recorded_at timestamptz not null,
        record jsonb not null,
        check(period_start = date_trunc('month',period_start)::date),
        check(period_end = (period_start + interval '1 month - 1 day')::date),
        unique(case_id,ingestion_key),
        unique(case_id,baseline_id,period_start,sequence),
        unique(company_id,case_id,observation_id,content_sha256),
        unique(company_id,case_id,baseline_id,period_start,observation_id),
        foreign key(company_id,case_id,baseline_id,baseline_sha256)
          references case_close_baselines(company_id,case_id,baseline_id,content_sha256) on delete cascade,
        foreign key(company_id,case_id,baseline_id,period_start,previous_id)
          references case_observations(company_id,case_id,baseline_id,period_start,observation_id)
          deferrable initially deferred
      );
      create unique index observation_initial on case_observations(case_id,baseline_id,period_start) where previous_id is null;
      create table case_attributions (
        attribution_id uuid primary key,
        company_id text not null,
        case_id text not null,
        observation_id uuid not null,
        observation_sha256 text not null,
        mode text not null check(mode in ('human','simulation')),
        actor_type text not null check(actor_type in ('human','service','model')),
        sequence integer not null check(sequence > 0),
        previous_id uuid unique,
        ingestion_key text not null,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        recorded_at timestamptz not null,
        record jsonb not null,
        check(mode <> 'human' or actor_type='human'),
        unique(case_id,ingestion_key),
        unique(observation_id,sequence),
        unique(company_id,case_id,observation_id,mode,attribution_id),
        foreign key(company_id,case_id,observation_id,observation_sha256)
          references case_observations(company_id,case_id,observation_id,content_sha256) on delete cascade,
        foreign key(company_id,case_id,observation_id,mode,previous_id)
          references case_attributions(company_id,case_id,observation_id,mode,attribution_id)
          deferrable initially deferred
      );
      create unique index attribution_initial on case_attributions(observation_id) where previous_id is null;
    """)
    for table in ("case_observations", "case_attributions"):
        op.execute(f"""
          alter table {table} enable row level security;
          alter table {table} force row level security;
          create policy {table}_scope on {table}
            using (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')))
            with check (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')));
          do $$ begin
            if exists(select 1 from pg_roles where rolname='pvc_app') then
              grant select,insert on {table} to pvc_app;
            end if;
            if exists(select 1 from pg_roles where rolname='pvc_readonly') then
              grant select on {table} to pvc_readonly;
            end if;
          end $$;
        """)


def downgrade() -> None:
    for table in ("case_observations", "case_attributions"):
        op.execute(f"alter table {table} no force row level security")
        if op.get_bind().exec_driver_sql(f"select exists(select 1 from {table})").scalar():
            raise RuntimeError("Realization history exists; restore an authorized backup rather than erase records")
    op.execute("drop table case_attributions,case_observations")
    op.execute("alter table case_close_baselines drop constraint close_observation_identity")
