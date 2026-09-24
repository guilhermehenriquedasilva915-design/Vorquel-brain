\set ON_ERROR_STOP on

-- Negative cases for 20260922_006.
--
-- The happy-path test proves the migration can widen a legacy database and
-- re-run against its own output. That is not enough: it only ever shows the
-- migration agreeing with a state it produced itself. These cases put the
-- database into states the migration must *refuse*, and then prove it refused
-- without changing anything.
--
-- The case that matters most is DRIFT_UNDER_V1_NAME. Before this file existed,
-- a constraint carrying the expected name and the wrong definition passed the
-- preflight and was silently overwritten.
--
-- How each case runs
-- ------------------
-- The migration is read from disk and executed inside a savepoint, so a case
-- can provoke the exception, catch it, roll back to the savepoint and carry on.
-- The migration's own BEGIN/COMMIT are stripped for this: psql would otherwise
-- close the surrounding transaction. What is executed is the DO block itself,
-- which is where every decision this file tests is made.
--
-- Run AFTER the database has been migrated to V1 by the main test sequence.

-- ---------------------------------------------------------------------------
-- Load the migration's DO block into a table, once.
-- ---------------------------------------------------------------------------

create temporary table migration_body (body text);

\set migration_path `echo "${MIGRATION_006_PATH:-supabase/migrations/20260922_006_brain_scope_vertical_entity_v01.sql}"`
\set migration_sql `cat "${MIGRATION_006_PATH:-supabase/migrations/20260922_006_brain_scope_vertical_entity_v01.sql}"`

insert into migration_body (body) values (:'migration_sql');

-- Keep only the DO block, dropping the file's own BEGIN/COMMIT. psql would
-- otherwise close the surrounding transaction and the savepoints below with it.
-- What remains is the classifier and the widening, byte for byte as they ship.
update migration_body
   set body = substring(body from 'do \$migration\$.*\$migration\$');

do $$
declare
  loaded text := (select body from migration_body);
begin
  if loaded is null or loaded = '' then
    raise exception 'migration DO block was not extracted; the drift cases would test nothing';
  end if;
  -- Guard against extracting a fragment: the classifier and both outcomes must
  -- be present, or a case could "pass" by exercising nothing.
  if loaded not like '%pg_get_constraintdef%'
     or loaded not like '%LEGACY_EXACT%'
     or loaded not like '%V1_EXACT%'
     or loaded not like '%refusing to migrate%' then
    raise exception 'extracted migration body is incomplete; refusing to test a fragment';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- Helpers. Temporary, so nothing persists past this session.
-- ---------------------------------------------------------------------------

-- Run the migration, returning the SQLSTATE and message rather than aborting,
-- so a case can assert on the refusal.
create function pg_temp.run_migration()
returns table (sqlstate_out text, message_out text)
language plpgsql as $fn$
begin
  begin
    execute (select body from migration_body);
    return query select null::text, null::text;
  exception when others then
    return query select SQLSTATE::text, SQLERRM::text;
  end;
end
$fn$;

-- A stable fingerprint of everything this migration is allowed to touch:
-- constraint identity, definition and row content, on both tables. Compared
-- before and after a refusal to prove nothing moved.
create function pg_temp.storage_fingerprint()
returns text language sql as $fn$
  select md5(string_agg(entry, '|' order by entry))
  from (
    select format('%s:%s:%s:%s',
                  r.relname, c.conname, c.oid, pg_get_constraintdef(c.oid)) as entry
    from pg_constraint c
    join pg_class r on r.oid = c.conrelid
    join pg_namespace n on n.oid = r.relnamespace
    where n.nspname = 'n8n_brain'
      and r.relname in ('operational_experiences', 'build_runs')
    union all
    select format('exp:%s:%s:%s', experience_id, scope_type, scope_id)
    from n8n_brain.operational_experiences
    union all
    select format('run:%s:%s:%s', run_id, scope_type, scope_id)
    from n8n_brain.build_runs
  ) s;
$fn$;

-- Replace a table's scope_type membership CHECK with an arbitrary one, to build
-- a drifted state. Only ever used inside a savepoint that is rolled back.
create procedure pg_temp.set_scope_constraint(
  table_name text, constraint_name text, values_list text)
language plpgsql as $fn$
declare
  existing text;
begin
  select c.conname into existing
  from pg_constraint c
  where c.conrelid = ('n8n_brain.' || table_name)::regclass
    and c.contype = 'c'
    and regexp_replace(
          regexp_replace(pg_get_constraintdef(c.oid), '\s+', '', 'g'),
          '::[a-zA-Z]+', '', 'g')
        ~ '^CHECK\(\(scope_type=ANY\(ARRAY\[.+\]\)\)\)$';

  if existing is not null then
    execute format('alter table n8n_brain.%I drop constraint %I', table_name, existing);
  end if;

  if constraint_name is not null then
    execute format('alter table n8n_brain.%I add constraint %I check (scope_type in (%s))',
                   table_name, constraint_name, values_list);
  end if;
end
$fn$;

-- One case: set up a drifted state, run the migration, require it to fail, and
-- require the database to be untouched.
create procedure pg_temp.expect_refusal(case_name text)
language plpgsql as $fn$
declare
  before_fp text;
  after_fp  text;
  result    record;
begin
  before_fp := pg_temp.storage_fingerprint();
  select * into result from pg_temp.run_migration();

  if result.sqlstate_out is null then
    raise exception '[%] migration SUCCEEDED and should have refused', case_name;
  end if;

  after_fp := pg_temp.storage_fingerprint();
  if before_fp is distinct from after_fp then
    raise exception
      '[%] migration refused but mutated storage anyway (fingerprint % -> %)',
      case_name, before_fp, after_fp;
  end if;

  raise notice '[%] refused as required: %', case_name, result.message_out;
end
$fn$;

-- ---------------------------------------------------------------------------
-- Baseline. The database arrives here already migrated to V1.
-- ---------------------------------------------------------------------------

-- Everything below runs in one transaction, because each case rolls back to a
-- savepoint after provoking a refusal. The migration's own BEGIN/COMMIT was
-- removed above precisely so it can run inside this block.
begin;

do $$
begin
  if not exists (
    select 1 from pg_constraint c
    join pg_class r on r.oid = c.conrelid
    join pg_namespace n on n.oid = r.relnamespace
    where n.nspname = 'n8n_brain'
      and r.relname = 'operational_experiences'
      and c.conname = 'operational_experiences_scope_type_v1_check'
  ) then
    raise exception 'expected a V1-migrated database before the drift cases run';
  end if;
end $$;

-- Rows that must survive every refusal below. Cleared first so the file can be
-- re-run against a database where an earlier attempt aborted part-way.
delete from n8n_brain.operational_experiences where experience_id like 'exp_drift_guard_%';
delete from n8n_brain.build_runs where run_id like 'run_drift_guard_%';

insert into n8n_brain.operational_experiences
  (experience_id, scope_type, scope_id, environment, category, observed_error)
values
  ('exp_drift_guard_a', 'CLIENT',         'chaves', 'DEV', 'UNKNOWN', 'drift guard'),
  ('exp_drift_guard_b', 'GLOBAL_VORQUEL', 'GLOBAL', 'DEV', 'UNKNOWN', 'drift guard');
insert into n8n_brain.build_runs (run_id, scope_type, scope_id, environment, goal)
values
  ('run_drift_guard_a', 'CLIENT', 'chaves', 'DEV', 'drift guard');

-- These use only CLIENT and GLOBAL_VORQUEL, which every constraint installed
-- below admits. The point here is that a refusal changes nothing, so the rows
-- must survive each case being *set up* as well as each case being refused; a
-- guard row that blocked the drifted constraint from being installed would stop
-- the case running at all. That VERTICAL and ENTITY rows are accepted after the
-- widening is proven separately, in brain_scope_vertical_entity_v01.sql.

-- ---------------------------------------------------------------------------
-- CASE 2 — V1 -> V1 is a TRUE no-op.
--
-- Not "produces the same text": no DDL is issued, so the constraint OIDs are
-- unchanged. A drop-and-recreate would pass a text comparison while rewriting
-- catalogue state on every run, and would give a drifted database a second
-- chance to be overwritten.
-- ---------------------------------------------------------------------------

do $$
declare
  before_oids text;
  after_oids  text;
  before_fp   text;
  result      record;
begin
  select string_agg(c.oid::text, ',' order by c.conname) into before_oids
  from pg_constraint c
  join pg_class r on r.oid = c.conrelid
  join pg_namespace n on n.oid = r.relnamespace
  where n.nspname = 'n8n_brain'
    and r.relname in ('operational_experiences', 'build_runs')
    and c.conname like '%scope_type_v1_check';

  before_fp := pg_temp.storage_fingerprint();

  select * into result from pg_temp.run_migration();
  if result.sqlstate_out is not null then
    raise exception 'V1 -> V1 re-apply failed: %', result.message_out;
  end if;

  select string_agg(c.oid::text, ',' order by c.conname) into after_oids
  from pg_constraint c
  join pg_class r on r.oid = c.conrelid
  join pg_namespace n on n.oid = r.relnamespace
  where n.nspname = 'n8n_brain'
    and r.relname in ('operational_experiences', 'build_runs')
    and c.conname like '%scope_type_v1_check';

  if before_oids is distinct from after_oids then
    raise exception
      'V1 re-apply dropped and recreated the constraints (oids % -> %); '
      'it must be a true no-op', before_oids, after_oids;
  end if;

  if before_fp is distinct from pg_temp.storage_fingerprint() then
    raise exception 'V1 re-apply changed storage';
  end if;

  raise notice '[V1_NOOP] re-apply issued no DDL; constraint oids unchanged';
end $$;

-- ---------------------------------------------------------------------------
-- CASE 3 — drift under the LEGACY name.
--
-- Correct legacy name, wrong definition.
-- ---------------------------------------------------------------------------

savepoint case_drift_legacy_name;
call pg_temp.set_scope_constraint(
  'operational_experiences', 'operational_experiences_scope_type_check',
  '''GLOBAL_VORQUEL'',''CLIENT''');
call pg_temp.set_scope_constraint(
  'build_runs', 'build_runs_scope_type_check',
  '''GLOBAL_VORQUEL'',''CLIENT'',''PROJECT'',''PRIVATE_TEST''');
call pg_temp.expect_refusal('DRIFT_UNDER_LEGACY_NAME');
rollback to savepoint case_drift_legacy_name;

-- ---------------------------------------------------------------------------
-- CASE 4 — drift under the V1 name.
--
-- The case the review found. Expected name, incomplete definition. Before the
-- fix this passed the preflight and was silently overwritten.
-- ---------------------------------------------------------------------------

savepoint case_drift_v1_name;
call pg_temp.set_scope_constraint(
  'operational_experiences', 'operational_experiences_scope_type_v1_check',
  '''GLOBAL_VORQUEL'',''CLIENT''');
call pg_temp.expect_refusal('DRIFT_UNDER_V1_NAME_INCOMPLETE');
rollback to savepoint case_drift_v1_name;

savepoint case_drift_v1_extra;
call pg_temp.set_scope_constraint(
  'build_runs', 'build_runs_scope_type_v1_check',
  '''GLOBAL_VORQUEL'',''VERTICAL'',''ENTITY'',''CLIENT'',''PROJECT'','
  '''PRIVATE_TEST'',''SOMETHING_ELSE''');
call pg_temp.expect_refusal('DRIFT_UNDER_V1_NAME_EXTRA');
rollback to savepoint case_drift_v1_extra;

-- ---------------------------------------------------------------------------
-- CASE 5 — MISSING.
-- ---------------------------------------------------------------------------

savepoint case_missing;
call pg_temp.set_scope_constraint('operational_experiences', null, null);
call pg_temp.expect_refusal('MISSING_ON_ONE_TABLE');
rollback to savepoint case_missing;

savepoint case_missing_both;
call pg_temp.set_scope_constraint('operational_experiences', null, null);
call pg_temp.set_scope_constraint('build_runs', null, null);
call pg_temp.expect_refusal('MISSING_ON_BOTH_TABLES');
rollback to savepoint case_missing_both;

-- ---------------------------------------------------------------------------
-- CASE 6 — MIXED STATE.
--
-- One table legacy, one already V1. Fails closed rather than "completing" the
-- half-applied migration: a partial application is evidence that something
-- happened outside this file, and finishing the job would destroy it.
-- ---------------------------------------------------------------------------

savepoint case_mixed;
call pg_temp.set_scope_constraint(
  'build_runs', 'build_runs_scope_type_check',
  '''GLOBAL_VORQUEL'',''CLIENT'',''PROJECT'',''PRIVATE_TEST''');
call pg_temp.expect_refusal('MIXED_V1_AND_LEGACY');
rollback to savepoint case_mixed;

savepoint case_mixed_reverse;
call pg_temp.set_scope_constraint(
  'operational_experiences', 'operational_experiences_scope_type_check',
  '''GLOBAL_VORQUEL'',''CLIENT'',''PROJECT'',''PRIVATE_TEST''');
call pg_temp.expect_refusal('MIXED_LEGACY_AND_V1');
rollback to savepoint case_mixed_reverse;

-- ---------------------------------------------------------------------------
-- CASE 7 — EXTRA VALUE.
--
-- COMPANY is the value DIV-3 explicitly refused to make a scope, so it is the
-- one most likely to be added by someone acting in good faith.
-- ---------------------------------------------------------------------------

savepoint case_extra_value;
call pg_temp.set_scope_constraint(
  'operational_experiences', 'operational_experiences_scope_type_v1_check',
  '''GLOBAL_VORQUEL'',''VERTICAL'',''ENTITY'',''CLIENT'',''PROJECT'','
  '''PRIVATE_TEST'',''COMPANY''');
call pg_temp.expect_refusal('EXTRA_VALUE_COMPANY');
rollback to savepoint case_extra_value;

-- ---------------------------------------------------------------------------
-- CASE 8 — NARROWED VALUE SET.
-- ---------------------------------------------------------------------------

savepoint case_narrowed;
call pg_temp.set_scope_constraint(
  'operational_experiences', 'operational_experiences_scope_type_v1_check',
  '''GLOBAL_VORQUEL'',''VERTICAL'',''ENTITY'',''CLIENT'',''PRIVATE_TEST''');
call pg_temp.expect_refusal('NARROWED_MISSING_PROJECT');
rollback to savepoint case_narrowed;

savepoint case_narrowed_legacy;
call pg_temp.set_scope_constraint(
  'operational_experiences', 'operational_experiences_scope_type_check',
  '''GLOBAL_VORQUEL'',''CLIENT'',''PROJECT''');
call pg_temp.set_scope_constraint(
  'build_runs', 'build_runs_scope_type_check',
  '''GLOBAL_VORQUEL'',''CLIENT'',''PROJECT'',''PRIVATE_TEST''');
call pg_temp.expect_refusal('NARROWED_LEGACY_MISSING_PRIVATE_TEST');
rollback to savepoint case_narrowed_legacy;

-- ---------------------------------------------------------------------------
-- CASE — RIGHT VALUES, WRONG NAME.
--
-- The name is not semantic authority, but it is still part of the expected
-- state. An exact value set under an unexpected name means someone rebuilt the
-- constraint by hand, which is a reconciliation question rather than something
-- to adopt silently.
-- ---------------------------------------------------------------------------

savepoint case_wrong_name_v1;
call pg_temp.set_scope_constraint(
  'operational_experiences', 'operational_experiences_scope_type_custom',
  '''GLOBAL_VORQUEL'',''VERTICAL'',''ENTITY'',''CLIENT'',''PROJECT'',''PRIVATE_TEST''');
call pg_temp.expect_refusal('V1_VALUES_UNDER_UNEXPECTED_NAME');
rollback to savepoint case_wrong_name_v1;

savepoint case_wrong_name_legacy;
call pg_temp.set_scope_constraint(
  'operational_experiences', 'operational_experiences_scope_legacy',
  '''GLOBAL_VORQUEL'',''CLIENT'',''PROJECT'',''PRIVATE_TEST''');
call pg_temp.set_scope_constraint(
  'build_runs', 'build_runs_scope_type_check',
  '''GLOBAL_VORQUEL'',''CLIENT'',''PROJECT'',''PRIVATE_TEST''');
call pg_temp.expect_refusal('LEGACY_VALUES_UNDER_UNEXPECTED_NAME');
rollback to savepoint case_wrong_name_legacy;

-- ---------------------------------------------------------------------------
-- CASE — DUPLICATE MEMBERSHIP CONSTRAINTS.
--
-- Two membership CHECKs on scope_type is ambiguous: the migration cannot know
-- which one is authoritative, so it does not guess.
-- ---------------------------------------------------------------------------

savepoint case_duplicate;
alter table n8n_brain.operational_experiences
  add constraint operational_experiences_scope_type_shadow
  check (scope_type in ('GLOBAL_VORQUEL','VERTICAL','ENTITY','CLIENT','PROJECT','PRIVATE_TEST'));
call pg_temp.expect_refusal('TWO_MEMBERSHIP_CONSTRAINTS');
rollback to savepoint case_duplicate;

-- ---------------------------------------------------------------------------
-- CASE — RIGHT VALUES, WRONG MEANING.
--
-- A negated membership test mentions exactly the six contract values and admits
-- precisely the opposite of what the contract says. Extracting literals without
-- first checking the shape would classify this as V1_EXACT and then "widen" a
-- constraint that already permits everything.
--
-- It is reported as MISSING rather than DRIFT, and that is accurate to the
-- definition rather than a near miss: there is no plain membership CHECK on
-- scope_type on this table. Either way the migration refuses and changes
-- nothing, which is the property under test.

savepoint case_negated;
call pg_temp.set_scope_constraint('operational_experiences', null, null);
alter table n8n_brain.operational_experiences
  add constraint operational_experiences_scope_type_v1_check
  check (scope_type not in
    ('GLOBAL_VORQUEL','VERTICAL','ENTITY','CLIENT','PROJECT','PRIVATE_TEST')
    or scope_type is not null);
call pg_temp.expect_refusal('NEGATED_MEMBERSHIP_TEST');
rollback to savepoint case_negated;

-- ---------------------------------------------------------------------------
-- The database is back exactly where it started, and the guard rows are intact.
-- ---------------------------------------------------------------------------

do $$
declare
  definition text;
begin
  foreach definition in array array['operational_experiences', 'build_runs'] loop
    if not exists (
      select 1 from pg_constraint c
      where c.conrelid = ('n8n_brain.' || definition)::regclass
        and c.conname = definition || '_scope_type_v1_check'
    ) then
      raise exception 'the drift cases left %s without its V1 constraint', definition;
    end if;
  end loop;

  if (select count(*) from n8n_brain.operational_experiences
      where experience_id like 'exp_drift_guard_%') <> 2 then
    raise exception 'guard rows did not survive the drift cases';
  end if;
  if (select count(*) from n8n_brain.build_runs
      where run_id like 'run_drift_guard_%') <> 1 then
    raise exception 'guard build_run did not survive the drift cases';
  end if;
end $$;

-- Clean up, so the suites that run after this find the database as they expect.
delete from n8n_brain.operational_experiences where experience_id like 'exp_drift_guard_%';
delete from n8n_brain.build_runs where run_id like 'run_drift_guard_%';

do $$
begin
  if (select count(*) from n8n_brain.operational_experiences) <> 0
     or (select count(*) from n8n_brain.build_runs) <> 0 then
    raise exception 'drift cases did not clean up after themselves';
  end if;
  raise notice 'all drift cases refused as required, with no mutation';
end $$;

commit;
