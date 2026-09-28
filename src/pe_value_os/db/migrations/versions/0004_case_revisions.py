"""Immutable constructed case revisions and separate research review receipts."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TABLES = ("investment_cases", "case_revisions", "case_reviews")

SCHEMA = """
create table investment_cases (
  case_id text primary key,
  company_id text not null references companies(company_id) on delete cascade,
  label text not null,
  currency text not null check (currency ~ '^[A-Z]{3}$'),
  classification text not null check (classification = 'constructed_operating_exercise'),
  created_by text not null,
  created_at timestamptz not null,
  version integer not null default 0 check (version >= 0),
  current_revision_id uuid,
  original_revision_id uuid,
  unique (company_id, case_id),
  check ((version = 0 and current_revision_id is null and original_revision_id is null)
      or (version > 0 and current_revision_id is not null and original_revision_id is not null))
);
create table case_revisions (
  revision_id uuid primary key,
  company_id text not null,
  case_id text not null,
  sequence integer not null check (sequence >= 1),
  parent_revision_id uuid,
  content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
  record jsonb not null,
  foreign key (company_id, case_id) references investment_cases(company_id, case_id) on delete cascade,
  unique (company_id, case_id, revision_id),
  unique (company_id, case_id, revision_id, content_sha256),
  unique (case_id, sequence),
  foreign key (company_id, case_id, parent_revision_id)
    references case_revisions(company_id, case_id, revision_id) deferrable initially deferred
);
alter table investment_cases add constraint case_current_fk
  foreign key (company_id, case_id, current_revision_id)
  references case_revisions(company_id, case_id, revision_id) deferrable initially deferred;
alter table investment_cases add constraint case_original_fk
  foreign key (company_id, case_id, original_revision_id)
  references case_revisions(company_id, case_id, revision_id) deferrable initially deferred;
create table case_reviews (
  review_id uuid primary key,
  company_id text not null,
  case_id text not null,
  revision_id uuid not null,
  revision_sha256 text not null,
  mode text not null check (mode in ('human', 'simulation')),
  decision text not null check (decision in ('accept','request_changes','reject','withdraw')),
  actor text not null,
  actor_type text not null check (actor_type in ('human','model','service')),
  recorded_at timestamptz not null,
  supersedes_review_id uuid unique,
  record jsonb not null,
  check (mode <> 'human' or actor_type = 'human'),
  check (decision <> 'withdraw' or supersedes_review_id is not null),
  unique (company_id, case_id, revision_id, mode, actor, review_id),
  foreign key (company_id, case_id, revision_id, revision_sha256)
    references case_revisions(company_id, case_id, revision_id, content_sha256) on delete cascade,
  foreign key (company_id, case_id, revision_id, mode, actor, supersedes_review_id)
    references case_reviews(company_id, case_id, revision_id, mode, actor, review_id) deferrable initially deferred
);
create unique index case_review_initial on case_reviews(revision_id, mode, actor) where supersedes_review_id is null;
create function enforce_case_head() returns trigger language plpgsql as $$
begin
  if new.version <> old.version + 1 or new.current_revision_id is not distinct from old.current_revision_id
     or (old.original_revision_id is not null and new.original_revision_id is distinct from old.original_revision_id)
     or (old.original_revision_id is null and new.original_revision_id is distinct from new.current_revision_id)
     or not exists (select 1 from case_revisions r where r.revision_id=new.current_revision_id
       and r.company_id=new.company_id and r.case_id=new.case_id and r.sequence=new.version
       and r.parent_revision_id is not distinct from old.current_revision_id) then
    raise exception 'case head must advance by one immutable linked revision';
  end if;
  return new;
end $$;
create trigger case_head_guard before update on investment_cases for each row execute function enforce_case_head();
"""


def upgrade() -> None:
    op.execute(SCHEMA)
    for table in TABLES:
        op.execute(f"""
          alter table {table} enable row level security;
          alter table {table} force row level security;
          create policy {table}_scope on {table}
            using (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')))
            with check (company_id = any(string_to_array(current_setting('pvc.companies', true), ',')));
        """)
    op.execute("""
      do $$ begin
        if exists (select 1 from pg_roles where rolname = 'pvc_app') then
          grant select, insert on investment_cases, case_revisions, case_reviews to pvc_app;
          grant update (version, current_revision_id, original_revision_id) on investment_cases to pvc_app;
        end if;
        if exists (select 1 from pg_roles where rolname = 'pvc_readonly') then
          grant select on investment_cases, case_revisions, case_reviews to pvc_readonly;
        end if;
      end $$;
    """)


def downgrade() -> None:
    if op.get_bind().exec_driver_sql("select exists(select 1 from investment_cases)").scalar():
        raise RuntimeError(
            "Case history exists; restore an authorized pre-migration backup rather than erase it through downgrade"
        )
    op.execute("alter table investment_cases drop constraint case_current_fk, drop constraint case_original_fk")
    op.execute("drop table case_reviews, case_revisions, investment_cases")
    op.execute("drop function enforce_case_head()")
