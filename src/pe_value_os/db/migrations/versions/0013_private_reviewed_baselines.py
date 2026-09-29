"""Role-specific private plan reviews and immutable comparison baselines."""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      alter table private_capacity_plans add constraint private_capacity_review_reference
        unique(company_id,revision_id,content_sha256);
      create table private_plan_reviews (
        review_id uuid primary key,
        company_id text not null references companies(company_id) on delete cascade,
        case_key text not null,
        capacity_revision_id uuid not null,
        capacity_sha256 text not null,
        review_kind text not null check(review_kind in ('finance','operating')),
        sequence integer not null check(sequence > 0),
        previous_sha256 text,
        idempotency_key text not null,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        record jsonb not null,
        check(record->>'review_id'=review_id::text and record->>'company_id'=company_id
          and record->>'case_key'=case_key and record->>'review_kind'=review_kind
          and record->>'capacity_revision_id'=capacity_revision_id::text and record->>'content_sha256'=content_sha256),
        check((sequence=1) = (previous_sha256 is null)),
        unique(company_id,capacity_revision_id,review_kind,sequence),
        unique(company_id,capacity_revision_id,review_kind,idempotency_key),
        unique(company_id,capacity_revision_id,review_kind,content_sha256),
        unique(company_id,capacity_revision_id,review_kind,previous_sha256),
        unique(company_id,capacity_revision_id,review_id,content_sha256),
        foreign key(company_id,capacity_revision_id,review_kind,previous_sha256)
          references private_plan_reviews(company_id,capacity_revision_id,review_kind,content_sha256) deferrable initially deferred,
        foreign key(company_id,capacity_revision_id,capacity_sha256)
          references private_capacity_plans(company_id,revision_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,capacity_sha256)
          references private_capacity_plans(company_id,case_key,content_sha256) deferrable initially deferred
      );
      create unique index private_plan_review_initial on private_plan_reviews(company_id,capacity_revision_id,review_kind)
        where previous_sha256 is null;
      create table private_baselines (
        baseline_id uuid primary key,
        company_id text not null references companies(company_id) on delete cascade,
        case_key text not null check(case_key ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'),
        sequence integer not null check(sequence > 0),
        previous_sha256 text,
        idempotency_key text not null,
        capacity_revision_id uuid not null,
        capacity_sha256 text not null,
        finance_review_id uuid not null,
        finance_review_sha256 text not null,
        operating_review_id uuid not null,
        operating_review_sha256 text not null,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        record jsonb not null,
        check(record->>'baseline_id'=baseline_id::text and record->>'company_id'=company_id
          and record->>'case_key'=case_key and record->>'content_sha256'=content_sha256),
        check((sequence=1) = (previous_sha256 is null)),
        unique(company_id,case_key,sequence),
        unique(company_id,case_key,idempotency_key),
        unique(company_id,case_key,content_sha256),
        unique(company_id,case_key,previous_sha256),
        foreign key(company_id,case_key,previous_sha256)
          references private_baselines(company_id,case_key,content_sha256) deferrable initially deferred,
        foreign key(company_id,capacity_revision_id,capacity_sha256)
          references private_capacity_plans(company_id,revision_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,capacity_sha256)
          references private_capacity_plans(company_id,case_key,content_sha256) deferrable initially deferred,
        foreign key(company_id,capacity_revision_id,finance_review_id,finance_review_sha256)
          references private_plan_reviews(company_id,capacity_revision_id,review_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,capacity_revision_id,operating_review_id,operating_review_sha256)
          references private_plan_reviews(company_id,capacity_revision_id,review_id,content_sha256) deferrable initially deferred
      );
      create unique index private_baseline_initial on private_baselines(company_id,case_key) where previous_sha256 is null;
    """)
    for table in ("private_plan_reviews", "private_baselines"):
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
    for table in ("private_baselines", "private_plan_reviews"):
        op.execute(f"alter table {table} no force row level security")
        if op.get_bind().exec_driver_sql(f"select exists(select 1 from {table})").scalar():
            raise RuntimeError(
                "Private reviewed baseline history exists; restore an authorized backup rather than erase it"
            )
    op.execute("drop table private_baselines")
    op.execute("drop table private_plan_reviews")
    op.execute("alter table private_capacity_plans drop constraint private_capacity_review_reference")
