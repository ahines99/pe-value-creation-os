-- Least-privilege roles (PVC-132). Run once per cluster as an administrator, before migrations.
-- Passwords are supplied by the caller (psql -v app_password=... -v readonly_password=...), never committed.
--   pvc_migrator : owns the schema; used only by the migration job.
--   pvc_app      : application runtime; subject to row-level security; audit_events is insert/select only.
--   pvc_readonly : reporting and access reviews; select only; subject to row-level security.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'pvc_migrator') then
    create role pvc_migrator login;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'pvc_app') then
    create role pvc_app login;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'pvc_readonly') then
    create role pvc_readonly login;
  end if;
end $$;
