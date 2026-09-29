"""Append-only company-scoped private processing grants and revocations."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      create table private_processing_grants (
        event_id uuid primary key,
        company_id text not null references companies(company_id) on delete cascade,
        grant_key text not null check(grant_key ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'),
        sequence integer not null check(sequence > 0),
        previous_sha256 text,
        idempotency_key text not null,
        action text not null check(action in ('grant','revoke')),
        actor_type text not null check(actor_type='human'),
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        recorded_at timestamptz not null,
        record jsonb not null,
        check((sequence=1) = (previous_sha256 is null)),
        check(action <> 'revoke' or previous_sha256 is not null),
        unique(company_id,grant_key,sequence),
        unique(company_id,grant_key,idempotency_key),
        unique(company_id,grant_key,content_sha256),
        unique(company_id,grant_key,previous_sha256),
        foreign key(company_id,grant_key,previous_sha256)
          references private_processing_grants(company_id,grant_key,content_sha256)
          deferrable initially deferred
      );
      create unique index private_grant_initial on private_processing_grants(company_id,grant_key)
        where previous_sha256 is null;
      alter table private_processing_grants enable row level security;
      alter table private_processing_grants force row level security;
      create policy private_grant_scope on private_processing_grants
        using (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')))
        with check (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')));
      do $$ begin
        if exists(select 1 from pg_roles where rolname='pvc_app') then
          grant select,insert on private_processing_grants to pvc_app;
        end if;
        if exists(select 1 from pg_roles where rolname='pvc_readonly') then
          grant select on private_processing_grants to pvc_readonly;
        end if;
      end $$;
    """)


def downgrade() -> None:
    op.execute("alter table private_processing_grants no force row level security")
    if op.get_bind().exec_driver_sql("select exists(select 1 from private_processing_grants)").scalar():
        raise RuntimeError("Private grant history exists; restore an authorized backup rather than erase it")
    op.execute("drop table private_processing_grants")
