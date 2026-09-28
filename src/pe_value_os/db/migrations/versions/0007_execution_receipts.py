"""Immutable constructed assignment, steering, delivery, review and claim links."""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      alter table case_attributions add constraint attribution_execution_identity
        unique(company_id,case_id,attribution_id,content_sha256);
      create table case_execution_events (
        event_id uuid primary key,
        company_id text not null,
        case_id text not null,
        baseline_id uuid not null,
        baseline_sha256 text not null,
        mode text not null check(mode in ('human','simulation')),
        kind text not null check(kind in ('assignment','steering','delivery','acceptance','claim_link')),
        stream_key text not null check(stream_key ~ '^[0-9a-f]{64}$'),
        sequence integer not null check(sequence > 0),
        previous_id uuid unique,
        ingestion_key text not null,
        actor_type text not null check(actor_type in ('human','service','model')),
        effective_on date not null,
        supporting_event_id uuid,
        supporting_sha256 text,
        attribution_id uuid,
        attribution_sha256 text,
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        recorded_at timestamptz not null,
        record jsonb not null,
        check(mode <> 'human' or actor_type='human'),
        check((supporting_event_id is null) = (supporting_sha256 is null)),
        check((attribution_id is null) = (attribution_sha256 is null)),
        check((kind in ('assignment','steering')) = (supporting_event_id is null)),
        check((kind='claim_link') = (attribution_id is not null)),
        unique(case_id,ingestion_key),
        unique(baseline_id,stream_key,sequence),
        unique(company_id,case_id,baseline_id,mode,stream_key,event_id),
        unique(company_id,case_id,baseline_id,mode,event_id,content_sha256),
        foreign key(company_id,case_id,baseline_id,baseline_sha256)
          references case_close_baselines(company_id,case_id,baseline_id,content_sha256) on delete cascade,
        foreign key(company_id,case_id,mode,baseline_id)
          references case_close_baselines(company_id,case_id,mode,baseline_id) on delete cascade,
        foreign key(company_id,case_id,baseline_id,mode,stream_key,previous_id)
          references case_execution_events(company_id,case_id,baseline_id,mode,stream_key,event_id) deferrable initially deferred,
        foreign key(company_id,case_id,baseline_id,mode,supporting_event_id,supporting_sha256)
          references case_execution_events(company_id,case_id,baseline_id,mode,event_id,content_sha256) deferrable initially deferred,
        foreign key(company_id,case_id,attribution_id,attribution_sha256)
          references case_attributions(company_id,case_id,attribution_id,content_sha256) on delete cascade
      );
      create unique index execution_initial on case_execution_events(baseline_id,stream_key) where previous_id is null;
      alter table case_execution_events enable row level security;
      alter table case_execution_events force row level security;
      create policy execution_scope on case_execution_events
        using (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')))
        with check (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')));
      do $$ begin
        if exists(select 1 from pg_roles where rolname='pvc_app') then
          grant select,insert on case_execution_events to pvc_app;
        end if;
        if exists(select 1 from pg_roles where rolname='pvc_readonly') then
          grant select on case_execution_events to pvc_readonly;
        end if;
      end $$;
    """)


def downgrade() -> None:
    op.execute("alter table case_execution_events no force row level security")
    if op.get_bind().exec_driver_sql("select exists(select 1 from case_execution_events)").scalar():
        raise RuntimeError("Execution history exists; restore an authorized backup rather than erase receipts")
    op.execute("drop table case_execution_events")
    op.execute("alter table case_attributions drop constraint attribution_execution_identity")
