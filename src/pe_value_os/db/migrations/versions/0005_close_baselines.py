"""Immutable, review-bound hypothetical-close comparison baselines."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      alter table case_reviews add constraint review_baseline_identity unique
        (company_id, case_id, revision_id, revision_sha256, mode, review_id);
      create table case_close_baselines (
        baseline_id uuid primary key,
        company_id text not null,
        case_id text not null,
        sequence integer not null check(sequence > 0),
        revision_id uuid not null,
        revision_sha256 text not null,
        review_id uuid not null,
        mode text not null check(mode in ('human','simulation')),
        previous_id uuid unique,
        actor_type text not null check(actor_type in ('human','service','model')),
        content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
        record jsonb not null,
        check(mode <> 'human' or actor_type='human'),
        unique(company_id, case_id, mode, baseline_id),
        unique(case_id, mode, sequence),
        foreign key(company_id, case_id, revision_id, revision_sha256, mode, review_id)
          references case_reviews(company_id, case_id, revision_id, revision_sha256, mode, review_id) on delete cascade,
        foreign key(company_id, case_id, mode, previous_id)
          references case_close_baselines(company_id, case_id, mode, baseline_id) deferrable initially deferred
      );
      create unique index case_close_initial on case_close_baselines(case_id, mode) where previous_id is null;
      alter table case_close_baselines enable row level security;
      alter table case_close_baselines force row level security;
      create policy case_close_scope on case_close_baselines
        using (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')))
        with check (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')));
      do $$ begin
        if exists(select 1 from pg_roles where rolname='pvc_app') then
          grant select, insert on case_close_baselines to pvc_app;
        end if;
        if exists(select 1 from pg_roles where rolname='pvc_readonly') then
          grant select on case_close_baselines to pvc_readonly;
        end if;
      end $$;
    """)


def downgrade() -> None:
    op.execute("alter table case_close_baselines no force row level security")
    if op.get_bind().exec_driver_sql("select exists(select 1 from case_close_baselines)").scalar():
        raise RuntimeError("Close baseline history exists; restore an authorized backup rather than erase designations")
    op.execute("drop table case_close_baselines")
    op.execute("alter table case_reviews drop constraint review_baseline_identity")
