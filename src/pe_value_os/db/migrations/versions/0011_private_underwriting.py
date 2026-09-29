"""Private forecast revision history, anchored to exact financial snapshots."""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      create table private_underwriting (
        revision_id uuid primary key,
        company_id text not null references companies(company_id) on delete cascade,
        case_key text not null check(case_key ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'),
        sequence integer not null check(sequence > 0),
        previous_sha256 text,
        idempotency_key text not null,
        snapshot_sha256 text not null,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        record jsonb not null,
        check(record->>'revision_id' = revision_id::text and record->>'company_id' = company_id
          and record->>'case_key' = case_key and record->>'content_sha256' = content_sha256),
        check((sequence=1) = (previous_sha256 is null)),
        unique(company_id,case_key,sequence),
        unique(company_id,case_key,idempotency_key),
        unique(company_id,case_key,content_sha256),
        unique(company_id,case_key,previous_sha256),
        foreign key(company_id,case_key,previous_sha256)
          references private_underwriting(company_id,case_key,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,snapshot_sha256)
          references private_financial_snapshots(company_id,case_key,content_sha256) deferrable initially deferred
      );
      create unique index private_underwriting_initial on private_underwriting(company_id,case_key)
        where previous_sha256 is null;
      alter table private_underwriting enable row level security;
      alter table private_underwriting force row level security;
      create policy private_underwriting_scope on private_underwriting
        using (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')))
        with check (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')));
      do $$ begin
        if exists(select 1 from pg_roles where rolname='pvc_app') then
          grant select,insert on private_underwriting to pvc_app;
        end if;
        if exists(select 1 from pg_roles where rolname='pvc_readonly') then
          grant select on private_underwriting to pvc_readonly;
        end if;
      end $$;
    """)


def downgrade() -> None:
    op.execute("alter table private_underwriting no force row level security")
    if op.get_bind().exec_driver_sql("select exists(select 1 from private_underwriting)").scalar():
        raise RuntimeError("Private underwriting history exists; restore an authorized backup rather than erase it")
    op.execute("drop table private_underwriting")
