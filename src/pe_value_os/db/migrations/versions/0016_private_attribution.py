"""Private signed attribution proposals and distinct human finance reviews."""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      alter table private_observations add constraint private_observation_attribution_reference
        unique(company_id,case_key,observation_id,baseline_id,baseline_sha256,content_sha256);
      create table private_attributions (
        revision_id uuid primary key,
        company_id text not null references companies(company_id) on delete cascade,
        case_key text not null,
        attribution_key text not null,
        sequence integer not null check(sequence > 0),
        previous_sha256 text,
        idempotency_key text not null,
        baseline_id uuid not null,
        baseline_sha256 text not null,
        observation_id uuid not null,
        observation_sha256 text not null,
        execution_head_sha256 text,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        record jsonb not null,
        check(record @> jsonb_build_object('revision_id',revision_id::text,'company_id',company_id,
          'case_key',case_key,'attribution_key',attribution_key,'sequence',sequence,
          'baseline_id',baseline_id::text,'baseline_sha256',baseline_sha256,'content_sha256',content_sha256)),
        check(record->'request' @> jsonb_build_object('observation_id',observation_id::text,
          'observation_sha256',observation_sha256,'idempotency_key',idempotency_key)),
        check((record->'request'->>'expected_previous_sha256') is not distinct from previous_sha256),
        check((record->'request'->>'expected_execution_head_sha256') is not distinct from execution_head_sha256),
        check((sequence=1) = (previous_sha256 is null)),
        unique(company_id,case_key,attribution_key,sequence),
        unique(company_id,case_key,attribution_key,idempotency_key),
        unique(company_id,case_key,attribution_key,content_sha256),
        unique(company_id,case_key,attribution_key,previous_sha256),
        unique(company_id,case_key,revision_id,baseline_id,content_sha256),
        foreign key(company_id,case_key,attribution_key,previous_sha256)
          references private_attributions(company_id,case_key,attribution_key,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,baseline_id,baseline_sha256)
          references private_baselines(company_id,case_key,baseline_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,observation_id,baseline_id,baseline_sha256,observation_sha256)
          references private_observations(company_id,case_key,observation_id,baseline_id,baseline_sha256,content_sha256) deferrable initially deferred,
        foreign key(company_id,baseline_id,execution_head_sha256)
          references private_execution_events(company_id,baseline_id,content_sha256) deferrable initially deferred
      );
      create unique index private_attribution_initial on private_attributions(company_id,case_key,attribution_key)
        where previous_sha256 is null;
      create table private_attribution_reviews (
        review_id uuid primary key,
        company_id text not null references companies(company_id) on delete cascade,
        case_key text not null,
        attribution_revision_id uuid not null,
        attribution_sha256 text not null,
        baseline_id uuid not null,
        sequence integer not null check(sequence > 0),
        previous_sha256 text,
        idempotency_key text not null,
        execution_head_sha256 text,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        record jsonb not null,
        check(record @> jsonb_build_object('review_id',review_id::text,'company_id',company_id,
          'case_key',case_key,'attribution_revision_id',attribution_revision_id::text,
          'sequence',sequence,'content_sha256',content_sha256)),
        check(record->'request' @> jsonb_build_object('expected_attribution_sha256',attribution_sha256,
          'idempotency_key',idempotency_key)),
        check((record->'request'->>'expected_previous_sha256') is not distinct from previous_sha256),
        check((record->'request'->>'expected_execution_head_sha256') is not distinct from execution_head_sha256),
        check((sequence=1) = (previous_sha256 is null)),
        unique(company_id,attribution_revision_id,sequence),
        unique(company_id,attribution_revision_id,idempotency_key),
        unique(company_id,attribution_revision_id,content_sha256),
        unique(company_id,attribution_revision_id,previous_sha256),
        foreign key(company_id,attribution_revision_id,previous_sha256)
          references private_attribution_reviews(company_id,attribution_revision_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_key,attribution_revision_id,baseline_id,attribution_sha256)
          references private_attributions(company_id,case_key,revision_id,baseline_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,baseline_id,execution_head_sha256)
          references private_execution_events(company_id,baseline_id,content_sha256) deferrable initially deferred
      );
      create unique index private_attribution_review_initial on private_attribution_reviews(company_id,attribution_revision_id)
        where previous_sha256 is null;
      alter table private_attributions enable row level security;
      alter table private_attributions force row level security;
      alter table private_attribution_reviews enable row level security;
      alter table private_attribution_reviews force row level security;
      create policy private_attribution_scope on private_attributions
        using (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')))
        with check (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')));
      create policy private_attribution_review_scope on private_attribution_reviews
        using (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')))
        with check (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')));
      do $$ begin
        if exists(select 1 from pg_roles where rolname='pvc_app') then
          grant select,insert on private_attributions,private_attribution_reviews to pvc_app;
        end if;
        if exists(select 1 from pg_roles where rolname='pvc_readonly') then
          grant select on private_attributions,private_attribution_reviews to pvc_readonly;
        end if;
      end $$;
    """)


def downgrade() -> None:
    for table in ("private_attribution_reviews", "private_attributions"):
        op.execute(f"alter table {table} no force row level security")
        if op.get_bind().exec_driver_sql(f"select exists(select 1 from {table})").scalar():
            raise RuntimeError("Private attribution history exists; restore an authorized backup rather than erase it")
    op.execute("drop table private_attribution_reviews, private_attributions")
    op.execute("alter table private_observations drop constraint private_observation_attribution_reference")
