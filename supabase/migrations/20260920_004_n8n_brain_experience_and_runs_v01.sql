-- 20260920_004: operational experience + build run journal
--
-- Two things the Brain cannot do today:
--   * remember what actually happened when a workflow ran, so the next task can
--     reuse it instead of rediscovering it;
--   * survive the chat session, so a build started today can continue tomorrow.
--
-- Both live in n8n_brain rather than vorquel_knowledge: they are operational
-- records, not reviewed semantic knowledge. An experience only becomes
-- knowledge by passing through a candidate and a human review.
--
-- Append-only by construction: no UPDATE or DELETE grant is issued for
-- operational_experiences. build_runs is mutable by design (it is a journal of
-- current state), but only for the runtime role.

begin;

-- ---------------------------------------------------------------------------
-- Operational experience
-- ---------------------------------------------------------------------------

create table if not exists n8n_brain.operational_experiences (
  experience_id     text primary key
                    check (experience_id ~ '^exp_[a-z0-9][a-z0-9_-]{2,80}$'),

  scope_type        text not null default 'GLOBAL_VORQUEL'
                    check (scope_type in ('GLOBAL_VORQUEL','CLIENT','PROJECT','PRIVATE_TEST')),
  scope_id          text not null default 'GLOBAL'
                    check (scope_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'),

  environment       text not null
                    check (environment in ('DEV','SANDBOX','STAGING','PRODUCTION')),

  workflow_id       text,
  workflow_hash     text check (workflow_hash is null or workflow_hash ~ '^[0-9a-f]{64}$'),
  node              text,

  category          text not null check (category in (
                      'WORKFLOW_LOGIC','EXPRESSION','MAPPING','NODE_CONFIGURATION',
                      'NODE_VERSION','CREDENTIAL','AUTH_OAUTH','EXTERNAL_API',
                      'RATE_LIMIT','DATA_SHAPE','DATABASE_SCHEMA','ENVIRONMENT',
                      'TRANSIENT','UNKNOWN')),

  -- Sanitized only. The raw payload of a failing run is not stored: it is the
  -- most likely place for a client's personal data or a secret to hide.
  observed_error    text not null check (char_length(observed_error) between 1 and 4000),
  sanitized_context jsonb not null default '{}'::jsonb
                    check (jsonb_typeof(sanitized_context) = 'object'
                           and pg_column_size(sanitized_context) <= 8192),
  hypothesis        text check (hypothesis is null or char_length(hypothesis) <= 4000),
  change_summary    text check (change_summary is null or char_length(change_summary) <= 4000),
  result_before     text check (result_before is null or char_length(result_before) <= 2000),
  result_after      text check (result_after is null or char_length(result_after) <= 2000),
  execution_ids     text[] not null default '{}',

  n8n_version       text,

  -- An outcome can be MEDIDO while its explanation stays INFERIDO. Recording
  -- one number for both is how a single fix turns into a false universal rule.
  epistemic_status  text not null default 'OBSERVADO'
                    check (epistemic_status in (
                      'OBSERVADO','DECLARADO','MEDIDO','INFERIDO','HIPOTESE',
                      'ESTIMADO','DESCONHECIDO','CONFLITANTE','INVALIDADO')),

  instruction_authority text not null default 'NONE'
                        check (instruction_authority = 'NONE'),

  created_at        timestamptz not null default now(),

  constraint operational_experiences_scope_shape_check
    check ((scope_type = 'GLOBAL_VORQUEL') = (scope_id = 'GLOBAL')),

  -- A secret must never be representable here, same rule as knowledge.
  constraint operational_experiences_no_secret_keys_check
    check (not (sanitized_context ?| array[
      'secret','token','password','api_key','apiKey','authorization',
      'credential','credentials','cookie','private_key'])),

  -- Production is outside V1 autonomy; a row claiming a measured production run
  -- would mean the boundary was crossed.
  constraint operational_experiences_no_measured_production_check
    check (not (environment = 'PRODUCTION' and epistemic_status = 'MEDIDO'))
);

alter table n8n_brain.operational_experiences
  add column if not exists search_vector tsvector
  generated always as (
    to_tsvector('simple',
      coalesce(observed_error,'') || ' ' ||
      coalesce(category,'') || ' ' ||
      coalesce(node,'') || ' ' ||
      coalesce(hypothesis,'') || ' ' ||
      coalesce(change_summary,''))
  ) stored;

create index if not exists operational_experiences_fts_idx
  on n8n_brain.operational_experiences using gin (search_vector);
create index if not exists operational_experiences_scope_idx
  on n8n_brain.operational_experiences (scope_type, scope_id, environment, created_at desc);
create index if not exists operational_experiences_category_idx
  on n8n_brain.operational_experiences (category, created_at desc);

-- ---------------------------------------------------------------------------
-- Build run journal
-- ---------------------------------------------------------------------------
-- State of work lives here, not in the chat. Closing Claude must not lose a
-- half-finished build.

create table if not exists n8n_brain.build_runs (
  run_id            text primary key
                    check (run_id ~ '^run_[a-z0-9][a-z0-9_-]{2,80}$'),

  scope_type        text not null default 'GLOBAL_VORQUEL'
                    check (scope_type in ('GLOBAL_VORQUEL','CLIENT','PROJECT','PRIVATE_TEST')),
  scope_id          text not null default 'GLOBAL'
                    check (scope_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'),

  environment       text not null default 'DEV'
                    check (environment in ('DEV','SANDBOX','STAGING','PRODUCTION')),

  goal              text not null check (char_length(goal) between 1 and 4000),
  workflow_id       text,
  current_workflow_hash text
                    check (current_workflow_hash is null
                           or current_workflow_hash ~ '^[0-9a-f]{64}$'),
  snapshot_ref      text,

  phase             text not null default 'PLANNING' check (phase in (
                      'PLANNING','DRAFT','VALIDATING','AWAITING_APPROVAL','TESTING',
                      'DEBUGGING','PASSED','BLOCKED','ABORTED')),

  context_sources   jsonb not null default '[]'::jsonb
                    check (jsonb_typeof(context_sources) = 'array'),
  test_spec         jsonb not null default '{}'::jsonb
                    check (jsonb_typeof(test_spec) = 'object'),

  -- Debug budget. Four automatic attempts, then a human is required. Enforced
  -- here so a crashed or restarted agent cannot reset its own budget.
  attempts          integer not null default 0 check (attempts between 0 and 4),
  last_execution_id text,
  pending_approval  text,
  status_note       text check (status_note is null or char_length(status_note) <= 4000),

  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),

  constraint build_runs_scope_shape_check
    check ((scope_type = 'GLOBAL_VORQUEL') = (scope_id = 'GLOBAL')),
  constraint build_runs_no_production_mutation_check
    check (environment <> 'PRODUCTION')
);

create index if not exists build_runs_open_idx
  on n8n_brain.build_runs (scope_type, scope_id, phase, updated_at desc);

create or replace function n8n_brain.touch_build_run()
returns trigger language plpgsql as $fn$
begin
  new.updated_at := now();
  return new;
end
$fn$;

drop trigger if exists build_runs_touch on n8n_brain.build_runs;
create trigger build_runs_touch
  before update on n8n_brain.build_runs
  for each row execute function n8n_brain.touch_build_run();

-- ---------------------------------------------------------------------------
-- Grants: same least-privilege posture as the rest of n8n_brain.
-- No anon, no authenticated. Experiences are insert + select only.
-- ---------------------------------------------------------------------------

revoke all on n8n_brain.operational_experiences from public;
revoke all on n8n_brain.build_runs from public;

do $grants$
begin
  if exists (select 1 from pg_roles where rolname = 'n8n_brain_writer') then
    grant usage on schema n8n_brain to n8n_brain_writer;
    grant select, insert on n8n_brain.operational_experiences to n8n_brain_writer;
    grant select, insert, update on n8n_brain.build_runs to n8n_brain_writer;
  end if;
end
$grants$;

commit;
