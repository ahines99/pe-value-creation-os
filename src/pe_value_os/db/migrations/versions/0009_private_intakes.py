"""Private source custody, correction chains and exact-version finance decisions."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      create table private_intakes (
        intake_id uuid primary key,
        company_id text not null references companies(company_id) on delete cascade,
        dataset_key text not null check(dataset_key ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'),
        sequence integer not null check(sequence > 0),
        previous_sha256 text,
        idempotency_key text not null,
        grant_key text not null,
        grant_sha256 text not null,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        source_sha256 text not null,
        source_bytes bytea not null,
        record jsonb not null,
        check(octet_length(source_bytes) between 1 and 10485760),
        check(source_sha256 = encode(sha256(source_bytes),'hex')),
        check(record->>'intake_id' = intake_id::text and record->>'company_id' = company_id
          and record->>'dataset_key' = dataset_key and record->>'source_sha256' = source_sha256
          and record->>'content_sha256' = content_sha256),
        check((sequence=1) = (previous_sha256 is null)),
        unique(company_id,dataset_key,sequence),
        unique(company_id,dataset_key,idempotency_key),
        unique(company_id,dataset_key,content_sha256),
        unique(company_id,dataset_key,previous_sha256),
        unique(company_id,intake_id,content_sha256),
        foreign key(company_id,dataset_key,previous_sha256)
          references private_intakes(company_id,dataset_key,content_sha256) deferrable initially deferred,
        foreign key(company_id,grant_key,grant_sha256)
          references private_processing_grants(company_id,grant_key,content_sha256) deferrable initially deferred
      );
      create unique index private_intake_initial on private_intakes(company_id,dataset_key)
        where previous_sha256 is null;
      create table private_intake_reviews (
        review_id uuid primary key,
        company_id text not null references companies(company_id) on delete cascade,
        intake_id uuid not null,
        intake_sha256 text not null,
        sequence integer not null check(sequence > 0),
        previous_sha256 text,
        idempotency_key text not null,
        grant_key text not null,
        grant_sha256 text not null,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        decision text not null check(decision in ('accept','reject','request_changes','withdraw')),
        actor_type text not null check(actor_type='human'),
        record jsonb not null,
        check(record->>'review_id' = review_id::text and record->>'company_id' = company_id
          and record->>'intake_id' = intake_id::text and record->>'content_sha256' = content_sha256),
        check((sequence=1) = (previous_sha256 is null)),
        check(decision <> 'withdraw' or previous_sha256 is not null),
        unique(company_id,intake_id,sequence),
        unique(company_id,intake_id,idempotency_key),
        unique(company_id,intake_id,content_sha256),
        unique(company_id,intake_id,previous_sha256),
        foreign key(company_id,intake_id,intake_sha256)
          references private_intakes(company_id,intake_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,intake_id,previous_sha256)
          references private_intake_reviews(company_id,intake_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,grant_key,grant_sha256)
          references private_processing_grants(company_id,grant_key,content_sha256) deferrable initially deferred
      );
      create unique index private_review_initial on private_intake_reviews(company_id,intake_id)
        where previous_sha256 is null;
    """)
    for table in ("private_intakes", "private_intake_reviews"):
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
    # A migration owner with no company setting must still see populated tables.
    for table in ("private_intake_reviews", "private_intakes"):
        op.execute(f"alter table {table} no force row level security")
        if op.get_bind().exec_driver_sql(f"select exists(select 1 from {table})").scalar():
            raise RuntimeError(
                "Private source/review history exists; restore an authorized backup rather than erase it"
            )
    op.execute("drop table private_intake_reviews")
    op.execute("drop table private_intakes")
