\set ON_ERROR_STOP on

-- Invariants of 20260920_004. These are the constraints that keep a secret, a
-- production claim or a runaway debug loop out of the Brain, so they are
-- asserted rather than assumed.

do $$
begin
  if to_regclass('n8n_brain.operational_experiences') is null
     or to_regclass('n8n_brain.build_runs') is null then
    raise exception 'experience/run tables are missing';
  end if;

  if has_schema_privilege('anon', 'n8n_brain', 'USAGE')
     or has_schema_privilege('authenticated', 'n8n_brain', 'USAGE') then
    raise exception 'client role unexpectedly has n8n_brain schema usage';
  end if;
end $$;

-- A well-formed experience is accepted.
insert into n8n_brain.operational_experiences
  (experience_id, environment, category, observed_error, epistemic_status)
values
  ('exp_baseline_ok', 'DEV', 'EXPRESSION', 'expressao retornou undefined', 'MEDIDO');

-- ...and reads back.
do $$
begin
  if (select count(*) from n8n_brain.operational_experiences) <> 1 then
    raise exception 'baseline experience was not persisted';
  end if;
end $$;

-- A secret must never be representable, even nested under a benign name.
do $$
begin
  begin
    insert into n8n_brain.operational_experiences
      (experience_id, environment, category, observed_error, sanitized_context)
    values
      ('exp_secret_leak', 'DEV', 'CREDENTIAL', 'auth falhou',
       '{"token": "abc123"}'::jsonb);
    raise exception 'secret key was accepted in sanitized_context';
  exception
    when check_violation then null;
  end;
end $$;

-- A measured production run would mean the V1 boundary was crossed.
do $$
begin
  begin
    insert into n8n_brain.operational_experiences
      (experience_id, environment, category, observed_error, epistemic_status)
    values
      ('exp_prod_measured', 'PRODUCTION', 'EXTERNAL_API', 'timeout', 'MEDIDO');
    raise exception 'measured production experience was accepted';
  exception
    when check_violation then null;
  end;
end $$;

-- Scope shape: GLOBAL_VORQUEL owns the reserved id, and nothing else may claim it.
do $$
begin
  begin
    insert into n8n_brain.operational_experiences
      (experience_id, scope_type, scope_id, environment, category, observed_error)
    values
      ('exp_bad_scope', 'CLIENT', 'GLOBAL', 'DEV', 'MAPPING', 'x');
    raise exception 'CLIENT was allowed to borrow the GLOBAL scope id';
  exception
    when check_violation then null;
  end;
end $$;

-- Experiences are append-only: the runtime role gets no UPDATE or DELETE.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'n8n_brain_writer') then
    return;
  end if;
  if not has_table_privilege('n8n_brain_writer', 'n8n_brain.operational_experiences', 'INSERT')
     or not has_table_privilege('n8n_brain_writer', 'n8n_brain.operational_experiences', 'SELECT')
  then
    raise exception 'writer lacks append-only grants on operational_experiences';
  end if;
  if has_table_privilege('n8n_brain_writer', 'n8n_brain.operational_experiences', 'UPDATE')
     or has_table_privilege('n8n_brain_writer', 'n8n_brain.operational_experiences', 'DELETE')
  then
    raise exception 'operational_experiences is not append-only for the writer';
  end if;
end $$;

-- Debug budget is enforced by the database, so a restarted agent cannot reset it.
insert into n8n_brain.build_runs (run_id, goal, attempts)
values ('run_budget_probe', 'provar o orcamento de debug', 4);

do $$
begin
  begin
    update n8n_brain.build_runs set attempts = 5 where run_id = 'run_budget_probe';
    raise exception 'debug budget above 4 was accepted';
  exception
    when check_violation then null;
  end;
end $$;

-- A build run can never target production.
do $$
begin
  begin
    insert into n8n_brain.build_runs (run_id, goal, environment)
    values ('run_prod', 'x', 'PRODUCTION');
    raise exception 'production build run was accepted';
  exception
    when check_violation then null;
  end;
end $$;

-- updated_at moves on its own.
do $$
declare
  before_ts timestamptz;
  after_ts  timestamptz;
begin
  select updated_at into before_ts from n8n_brain.build_runs where run_id = 'run_budget_probe';
  perform pg_sleep(0.01);
  update n8n_brain.build_runs set phase = 'DEBUGGING' where run_id = 'run_budget_probe';
  select updated_at into after_ts from n8n_brain.build_runs where run_id = 'run_budget_probe';
  if after_ts <= before_ts then
    raise exception 'build_runs.updated_at did not advance';
  end if;
end $$;

-- Leave the disposable database clean for any job that reuses it.
delete from n8n_brain.build_runs where run_id = 'run_budget_probe';
delete from n8n_brain.operational_experiences where experience_id = 'exp_baseline_ok';

-- The trigger helper must resolve objects through a fixed search_path.
do $$
declare
  v_config text[];
begin
  select p.proconfig into v_config
  from pg_proc p
  join pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'n8n_brain'
    and p.proname = 'touch_build_run';

  if v_config is null or not exists (
    select 1 from unnest(v_config) x
    where x = 'search_path=pg_catalog, n8n_brain'
  ) then
    raise exception 'touch_build_run must pin search_path to pg_catalog, n8n_brain';
  end if;
end $$;
