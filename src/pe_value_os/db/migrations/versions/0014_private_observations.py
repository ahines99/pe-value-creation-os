"""Reviewed private counterfactuals and immutable whole-month observations."""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      alter table private_baselines add constraint private_baseline_measurement_reference
        unique(company_id,case_key,baseline_id,content_sha256);
      alter table private_financial_snapshots add constraint private_financial_measurement_reference
        unique(company_id,case_key,snapshot_id,content_sha256);
      create table private_counterfactuals (
        revision_id uuid primary key,
        company_id text not null references companies(company_id) on delete cascade,
        case_key text not null,
        counterfactual_key text not null,
        sequence integer not null check(sequence > 0),
        previous_sha256 text,
        idempotency_key text not null,
        baseline_id uuid not null,
        baseline_sha256 text not null,
        financial_snapshot_sha256 text not null,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        record jsonb not null,
        check(record->>'revision_id'=revision_id::text and record->>'company_id'=company_id
          and record->>'case_key'=case_key and record->>'counterfactual_key'=counterfactual_key
          and record->>'content_sha256'=content_sha256),
        check((sequence=1) = (previous_sha256 is null)),
        unique(company_id,case_key,counterfactual_key,sequence),
        unique(company_id,case_key,counterfactual_key,idempotency_key),
        unique(company_id,case_key,counterfactual_key,content_sha256),
        unique(company_id,case_key,counterfactual_key,previous_sha256),
        unique(company_id,case_key,revision_id,content_sha256),
        unique(company_id,revision_id,baseline_id,baseline_sha256,content_sha256),
        foreign key(company_id,case_key,counterfactual_key,previous_sha256)
          references private_counterfactuals(company_id,case_key,counterfactual_key,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,baseline_id,baseline_sha256)
          references private_baselines(company_id,case_key,baseline_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,financial_snapshot_sha256)
          references private_financial_snapshots(company_id,case_key,content_sha256) deferrable initially deferred
      );
      create unique index private_counterfactual_initial on private_counterfactuals(company_id,case_key,counterfactual_key)
        where previous_sha256 is null;
      create table private_counterfactual_reviews (
        review_id uuid primary key,
        company_id text not null references companies(company_id) on delete cascade,
        case_key text not null,
        counterfactual_revision_id uuid not null,
        counterfactual_sha256 text not null,
        sequence integer not null check(sequence > 0),
        previous_sha256 text,
        idempotency_key text not null,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        record jsonb not null,
        check(record->>'review_id'=review_id::text and record->>'company_id'=company_id
          and record->>'case_key'=case_key and record->>'counterfactual_revision_id'=counterfactual_revision_id::text
          and record->>'content_sha256'=content_sha256),
        check((sequence=1) = (previous_sha256 is null)),
        unique(company_id,counterfactual_revision_id,sequence),
        unique(company_id,counterfactual_revision_id,idempotency_key),
        unique(company_id,counterfactual_revision_id,content_sha256),
        unique(company_id,counterfactual_revision_id,previous_sha256),
        foreign key(company_id,counterfactual_revision_id,previous_sha256)
          references private_counterfactual_reviews(company_id,counterfactual_revision_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,counterfactual_revision_id,counterfactual_sha256)
          references private_counterfactuals(company_id,case_key,revision_id,content_sha256) deferrable initially deferred
      );
      create unique index private_counterfactual_review_initial on private_counterfactual_reviews(company_id,counterfactual_revision_id)
        where previous_sha256 is null;
      create table private_observations (
        observation_id uuid primary key,
        company_id text not null references companies(company_id) on delete cascade,
        case_key text not null,
        measurement_key text not null,
        sequence integer not null check(sequence > 0),
        previous_sha256 text,
        idempotency_key text not null,
        baseline_id uuid not null,
        baseline_sha256 text not null,
        counterfactual_revision_id uuid not null,
        counterfactual_sha256 text not null,
        counterfactual_review_sha256 text not null,
        actual_snapshot_id uuid not null,
        actual_snapshot_sha256 text not null,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        record jsonb not null,
        check(record->>'observation_id'=observation_id::text and record->>'company_id'=company_id
          and record->>'case_key'=case_key and record->>'measurement_key'=measurement_key
          and record->>'content_sha256'=content_sha256),
        check((sequence=1) = (previous_sha256 is null)),
        unique(company_id,case_key,measurement_key,sequence),
        unique(company_id,case_key,measurement_key,idempotency_key),
        unique(company_id,case_key,measurement_key,content_sha256),
        unique(company_id,case_key,measurement_key,previous_sha256),
        foreign key(company_id,case_key,measurement_key,previous_sha256)
          references private_observations(company_id,case_key,measurement_key,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,baseline_id,baseline_sha256)
          references private_baselines(company_id,case_key,baseline_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,counterfactual_revision_id,counterfactual_sha256)
          references private_counterfactuals(company_id,case_key,revision_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,counterfactual_revision_id,baseline_id,baseline_sha256,counterfactual_sha256)
          references private_counterfactuals(company_id,revision_id,baseline_id,baseline_sha256,content_sha256) deferrable initially deferred,
        foreign key(company_id,counterfactual_revision_id,counterfactual_review_sha256)
          references private_counterfactual_reviews(company_id,counterfactual_revision_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,actual_snapshot_id,actual_snapshot_sha256)
          references private_financial_snapshots(company_id,case_key,snapshot_id,content_sha256) deferrable initially deferred
      );
      create unique index private_observation_initial on private_observations(company_id,case_key,measurement_key)
        where previous_sha256 is null;
    """)
    for table in ("private_counterfactuals", "private_counterfactual_reviews", "private_observations"):
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
    for table in ("private_observations", "private_counterfactual_reviews", "private_counterfactuals"):
        op.execute(f"alter table {table} no force row level security")
        if op.get_bind().exec_driver_sql(f"select exists(select 1 from {table})").scalar():
            raise RuntimeError("Private measurement history exists; restore an authorized backup rather than erase it")
    op.execute("drop table private_observations")
    op.execute("drop table private_counterfactual_reviews")
    op.execute("drop table private_counterfactuals")
    op.execute("alter table private_financial_snapshots drop constraint private_financial_measurement_reference")
    op.execute("alter table private_baselines drop constraint private_baseline_measurement_reference")
