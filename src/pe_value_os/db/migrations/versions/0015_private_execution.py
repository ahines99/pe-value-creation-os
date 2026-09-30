"""Private human intervention decisions and delivery receipts."""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      create table private_execution_events (
        event_id uuid primary key,
        company_id text not null references companies(company_id) on delete cascade,
        case_key text not null,
        baseline_id uuid not null,
        baseline_sha256 text not null,
        sequence integer not null check(sequence > 0),
        previous_sha256 text,
        idempotency_key text not null,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        record jsonb not null,
        check(record->>'event_id'=event_id::text and record->>'company_id'=company_id
          and record->>'case_key'=case_key and record->>'baseline_id'=baseline_id::text
          and record->>'content_sha256'=content_sha256),
        check((sequence=1) = (previous_sha256 is null)),
        unique(company_id,baseline_id,sequence),
        unique(company_id,baseline_id,idempotency_key),
        unique(company_id,baseline_id,content_sha256),
        unique(company_id,baseline_id,previous_sha256),
        foreign key(company_id,baseline_id,previous_sha256)
          references private_execution_events(company_id,baseline_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,baseline_id,baseline_sha256)
          references private_baselines(company_id,case_key,baseline_id,content_sha256) deferrable initially deferred
      );
      create unique index private_execution_initial on private_execution_events(company_id,baseline_id)
        where previous_sha256 is null;
      alter table private_execution_events enable row level security;
      alter table private_execution_events force row level security;
      create policy private_execution_scope on private_execution_events
        using (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')))
        with check (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')));
      do $$ begin
        if exists(select 1 from pg_roles where rolname='pvc_app') then
          grant select,insert on private_execution_events to pvc_app;
        end if;
        if exists(select 1 from pg_roles where rolname='pvc_readonly') then
          grant select on private_execution_events to pvc_readonly;
        end if;
      end $$;
    """)


def downgrade() -> None:
    op.execute("alter table private_execution_events no force row level security")
    if op.get_bind().exec_driver_sql("select exists(select 1 from private_execution_events)").scalar():
        raise RuntimeError("Private execution history exists; restore an authorized backup rather than erase it")
    op.execute("drop table private_execution_events")
