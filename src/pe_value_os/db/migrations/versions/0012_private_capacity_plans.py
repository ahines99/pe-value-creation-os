"""Private capacity revision history, anchored to exact underwriting revisions."""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      create table private_capacity_plans (
        revision_id uuid primary key,
        company_id text not null references companies(company_id) on delete cascade,
        case_key text not null check(case_key ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'),
        sequence integer not null check(sequence > 0),
        previous_sha256 text,
        idempotency_key text not null,
        underwriting_sha256 text not null,
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
          references private_capacity_plans(company_id,case_key,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,underwriting_sha256)
          references private_underwriting(company_id,case_key,content_sha256) deferrable initially deferred
      );
      create unique index private_capacity_plans_initial on private_capacity_plans(company_id,case_key)
        where previous_sha256 is null;
      alter table private_capacity_plans enable row level security;
      alter table private_capacity_plans force row level security;
      create policy private_capacity_plans_scope on private_capacity_plans
        using (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')))
        with check (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')));
      do $$ begin
        if exists(select 1 from pg_roles where rolname='pvc_app') then
          grant select,insert on private_capacity_plans to pvc_app;
        end if;
        if exists(select 1 from pg_roles where rolname='pvc_readonly') then
          grant select on private_capacity_plans to pvc_readonly;
        end if;
      end $$;
    """)


def downgrade() -> None:
    op.execute("alter table private_capacity_plans no force row level security")
    if op.get_bind().exec_driver_sql("select exists(select 1 from private_capacity_plans)").scalar():
        raise RuntimeError("Private capacity history exists; restore an authorized backup rather than erase it")
    op.execute("drop table private_capacity_plans")
