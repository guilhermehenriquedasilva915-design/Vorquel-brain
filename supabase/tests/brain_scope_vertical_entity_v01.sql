\set ON_ERROR_STOP on

-- Invariants of 20260922_006, run AFTER the migration and AFTER
-- brain_scope_legacy_seed.sql has written rows under the old constraint.
--
-- Four things are proven here, in this order:
--   1. every legacy row is still present and unchanged;
--   2. the constraint widened -- it did not become something else;
--   3. exactly the six contract scopes are accepted, no more and no fewer;
--   4. the scope-shape rule still holds for the two new values.

-- ---------------------------------------------------------------------------
-- 1. No row was rewritten, reclassified or lost.
-- ---------------------------------------------------------------------------

do $$
declare
  found int;
begin
  select count(*) into found
  from n8n_brain.operational_experiences
  where (experience_id, scope_type, scope_id, epistemic_status) in (
    ('exp_legacy_global',  'GLOBAL_VORQUEL', 'GLOBAL',  'OBSERVADO'),
    ('exp_legacy_client',  'CLIENT',         'chaves',  'DECLARADO'),
    ('exp_legacy_project', 'PROJECT',        'proj-a',  'INFERIDO'),
    ('exp_legacy_private', 'PRIVATE_TEST',   'sandbox', 'ESTIMADO')
  );
  if found <> 4 then
    raise exception 'legacy experience rows did not survive the migration intact (found %)', found;
  end if;

  select count(*) into found
  from n8n_brain.build_runs
  where (run_id, scope_type, scope_id) in (
    ('run_legacy_global', 'GLOBAL_VORQUEL', 'GLOBAL'),
    ('run_legacy_client', 'CLIENT',         'chaves')
  );
  if found <> 2 then
    raise exception 'legacy build_run rows did not survive the migration intact (found %)', found;
  end if;
end $$;

-- Every row in the tables satisfies the new constraint. A widening cannot
-- orphan a row, and this says so with a query rather than with an argument.
do $$
declare
  bad int;
begin
  select count(*) into bad
  from n8n_brain.operational_experiences
  where scope_type not in
    ('GLOBAL_VORQUEL','VERTICAL','ENTITY','CLIENT','PROJECT','PRIVATE_TEST');
  if bad <> 0 then
    raise exception '% experience rows are invalid under the new constraint', bad;
  end if;

  select count(*) into bad
  from n8n_brain.build_runs
  where scope_type not in
    ('GLOBAL_VORQUEL','VERTICAL','ENTITY','CLIENT','PROJECT','PRIVATE_TEST');
  if bad <> 0 then
    raise exception '% build_run rows are invalid under the new constraint', bad;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 2. The constraint widened. Everything the old one admitted, the new one
--    still admits -- checked against the captured text, not against memory.
-- ---------------------------------------------------------------------------

do $$
declare
  legacy text;
  current_def text;
  value text;
begin
  select definition into legacy
  from n8n_brain._scope_migration_probe
  where table_name = 'operational_experiences';

  select pg_get_constraintdef(c.oid) into current_def
  from pg_constraint c
  join pg_class     r on r.oid = c.conrelid
  join pg_namespace n on n.oid = r.relnamespace
  where n.nspname = 'n8n_brain'
    and r.relname = 'operational_experiences'
    and c.conname = 'operational_experiences_scope_type_v1_check';

  if current_def is null then
    raise exception 'the new named scope_type constraint is missing';
  end if;

  foreach value in array array['GLOBAL_VORQUEL','CLIENT','PROJECT','PRIVATE_TEST'] loop
    if position(value in legacy) = 0 then
      raise exception 'captured pre-migration constraint did not mention %, so the capture is wrong', value;
    end if;
    if position(value in current_def) = 0 then
      raise exception 'legacy scope % was dropped by the migration', value;
    end if;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 3. Exactly six values. Each of the six is inserted for real; anything else is
--    rejected. Counting strings in the constraint text would prove the
--    constraint says six, not that the table accepts six.
-- ---------------------------------------------------------------------------

insert into n8n_brain.operational_experiences
  (experience_id, scope_type, scope_id, environment, category, observed_error)
values
  ('exp_six_global',   'GLOBAL_VORQUEL', 'GLOBAL',      'DEV', 'UNKNOWN', 'six-scope probe'),
  ('exp_six_vertical', 'VERTICAL',       'imobiliaria', 'DEV', 'UNKNOWN', 'six-scope probe'),
  ('exp_six_entity',   'ENTITY',         'chaves-hugo', 'DEV', 'UNKNOWN', 'six-scope probe'),
  ('exp_six_client',   'CLIENT',         'jacqueline',  'DEV', 'UNKNOWN', 'six-scope probe'),
  ('exp_six_project',  'PROJECT',        'proj-b',      'DEV', 'UNKNOWN', 'six-scope probe'),
  ('exp_six_private',  'PRIVATE_TEST',   'sandbox2',    'SANDBOX', 'UNKNOWN', 'six-scope probe');

insert into n8n_brain.build_runs (run_id, scope_type, scope_id, environment, goal)
values
  ('run_six_vertical', 'VERTICAL', 'clinica',     'DEV', 'six-scope probe'),
  ('run_six_entity',   'ENTITY',   'santos-corp', 'DEV', 'six-scope probe');

-- COMPANY is not a scope. A company is an ENTITY with entity_type=COMPANY, and
-- admitting both would create two ways to name the same thing.
do $$
declare
  rejected text;
begin
  foreach rejected in array array['COMPANY','PERSONAL','VERTICAL_SCOPE','entity'] loop
    begin
      insert into n8n_brain.operational_experiences
        (experience_id, scope_type, scope_id, environment, category, observed_error)
      values
        ('exp_reject_probe', rejected, 'x', 'DEV', 'UNKNOWN', 'probe');
      raise exception 'scope_type % was accepted and should not be', rejected;
    exception
      when check_violation then null;
    end;
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- 4. The new scopes cannot impersonate the global one.
-- ---------------------------------------------------------------------------

do $$
declare
  value text;
begin
  foreach value in array array['VERTICAL','ENTITY'] loop
    begin
      insert into n8n_brain.operational_experiences
        (experience_id, scope_type, scope_id, environment, category, observed_error)
      values
        ('exp_shape_probe', value, 'GLOBAL', 'DEV', 'UNKNOWN', 'probe');
      raise exception '% was allowed to borrow the GLOBAL scope id', value;
    exception
      when check_violation then null;
    end;
  end loop;

  -- ...and GLOBAL_VORQUEL still cannot be addressed as anything else.
  begin
    insert into n8n_brain.operational_experiences
      (experience_id, scope_type, scope_id, environment, category, observed_error)
    values
      ('exp_shape_probe2', 'GLOBAL_VORQUEL', 'not-global', 'DEV', 'UNKNOWN', 'probe');
    raise exception 'GLOBAL_VORQUEL was allowed a non-reserved scope_id';
  exception
    when check_violation then null;
  end;
end $$;

-- ---------------------------------------------------------------------------
-- Clean up everything this file and its seed introduced, so the migration test
-- leaves the database exactly as the other suites expect to find it.
-- ---------------------------------------------------------------------------

delete from n8n_brain.build_runs
 where run_id like 'run_legacy_%' or run_id like 'run_six_%';
delete from n8n_brain.operational_experiences
 where experience_id like 'exp_legacy_%' or experience_id like 'exp_six_%';
drop table n8n_brain._scope_migration_probe;

do $$
begin
  if (select count(*) from n8n_brain.operational_experiences) <> 0
     or (select count(*) from n8n_brain.build_runs) <> 0 then
    raise exception 'scope migration test did not clean up after itself';
  end if;
end $$;
