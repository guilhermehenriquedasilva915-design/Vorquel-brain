\set ON_ERROR_STOP on

-- Run BEFORE 20260922_006, with the four-value scope constraint still in force.
--
-- Its job is to make "backward compatible" a claim that can fail rather than a
-- sentence in a migration header. It writes one row under every legacy scope
-- and records the exact constraint text in force at that moment; the companion
-- test, run after the migration, checks that those rows came through untouched
-- and that the constraint widened rather than changed.

-- The pre-migration constraint, captured rather than remembered. Dropped again
-- by brain_scope_vertical_entity_v01.sql, so it leaves nothing behind.
create table n8n_brain._scope_migration_probe (
  table_name   text primary key,
  constraint_name text not null,
  definition   text not null
);

insert into n8n_brain._scope_migration_probe (table_name, constraint_name, definition)
select r.relname, c.conname, pg_get_constraintdef(c.oid)
from pg_constraint c
join pg_class     r on r.oid = c.conrelid
join pg_namespace n on n.oid = r.relnamespace
where n.nspname = 'n8n_brain'
  and r.relname in ('operational_experiences','build_runs')
  and c.conname in ('operational_experiences_scope_type_check','build_runs_scope_type_check');

do $$
begin
  if (select count(*) from n8n_brain._scope_migration_probe) <> 2 then
    raise exception 'pre-migration scope_type constraints were not found on both tables';
  end if;

  -- The starting point this whole migration is defined against.
  if exists (
    select 1 from n8n_brain._scope_migration_probe
    where definition like '%VERTICAL%' or definition like '%ENTITY%'
  ) then
    raise exception 'storage already accepts VERTICAL/ENTITY before the migration ran';
  end if;
end $$;

-- One row per legacy scope. These are the rows that must survive.
insert into n8n_brain.operational_experiences
  (experience_id, scope_type, scope_id, environment, category, observed_error, epistemic_status)
values
  ('exp_legacy_global',  'GLOBAL_VORQUEL', 'GLOBAL',  'DEV', 'EXPRESSION', 'legacy global row',  'OBSERVADO'),
  ('exp_legacy_client',  'CLIENT',         'chaves',  'DEV', 'MAPPING',    'legacy client row',  'DECLARADO'),
  ('exp_legacy_project', 'PROJECT',        'proj-a',  'DEV', 'DATA_SHAPE', 'legacy project row', 'INFERIDO'),
  ('exp_legacy_private', 'PRIVATE_TEST',   'sandbox', 'SANDBOX', 'TRANSIENT', 'legacy private row', 'ESTIMADO');

insert into n8n_brain.build_runs
  (run_id, scope_type, scope_id, environment, goal)
values
  ('run_legacy_global',  'GLOBAL_VORQUEL', 'GLOBAL',  'DEV', 'legacy global run'),
  ('run_legacy_client',  'CLIENT',         'chaves',  'DEV', 'legacy client run');

-- VERTICAL is rejected today. The test after the migration asserts it is not.
do $$
begin
  begin
    insert into n8n_brain.operational_experiences
      (experience_id, scope_type, scope_id, environment, category, observed_error)
    values
      ('exp_probe_vertical', 'VERTICAL', 'imobiliaria', 'DEV', 'UNKNOWN', 'probe');
    raise exception 'VERTICAL was accepted before the migration that adds it';
  exception
    when check_violation then null;
  end;
end $$;
