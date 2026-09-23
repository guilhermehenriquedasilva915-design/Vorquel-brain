-- 20260922_006: widen the operational scope vocabulary to the six contract scopes
--
-- DIV-3 in docs/BRAIN_CONTRACT_V1_RECONCILIATION.md recorded a deliberate gap:
-- the Brain V1 contract defines six scopes, storage accepted four, and
-- Brain-V1-A ran no migration. This is the migration that gap was deferred to.
--
--   contract (Brain-V1-A):  GLOBAL_VORQUEL VERTICAL ENTITY CLIENT PROJECT PRIVATE_TEST
--   storage  (before this): GLOBAL_VORQUEL                 CLIENT PROJECT PRIVATE_TEST
--   storage  (after this):  GLOBAL_VORQUEL VERTICAL ENTITY CLIENT PROJECT PRIVATE_TEST
--
-- The change is strictly a widening. Two values are added to a CHECK; none is
-- removed, renamed or redefined. CLIENT and PROJECT keep exactly the meaning
-- they had. No row is read, rewritten or reclassified: a widening cannot
-- invalidate a row that already satisfied the narrower constraint, which is why
-- this migration touches no data at all.
--
-- A company is an ENTITY with entity_type=COMPANY. COMPANY is not a scope, and
-- adding one would create two ways to name the same thing.
--
-- ROLLBACK
-- --------
-- Reversible only while no row uses a new value. To roll back:
--
--   select scope_type, count(*) from n8n_brain.operational_experiences
--     where scope_type in ('VERTICAL','ENTITY') group by 1;
--   select scope_type, count(*) from n8n_brain.build_runs
--     where scope_type in ('VERTICAL','ENTITY') group by 1;
--
-- If both are empty, re-run the two ALTERs below with the four-value list. If
-- either returns rows, narrowing would orphan real records: the rows must be
-- rescoped or removed by an explicit, reviewed decision first. This migration
-- does not ship an automatic down-step, because a down-step that silently
-- deletes rows to make a constraint fit is the failure mode the Brain exists to
-- prevent.
--
-- IDEMPOTENCE
-- -----------
-- Re-running is a no-op: each constraint is dropped by name if present and
-- recreated with the same definition, in one transaction.

begin;

-- ---------------------------------------------------------------------------
-- The constraint as it stands before this migration, asserted rather than
-- assumed. If storage has drifted from what Brain-V1-A recorded, this fails
-- loudly here instead of being papered over by the DROP below.
-- ---------------------------------------------------------------------------

do $pre$
declare
  missing text;
begin
  select string_agg(t.name, ', ' order by t.name)
    into missing
  from (values ('operational_experiences'), ('build_runs')) as t(name)
  where not exists (
    select 1
    from pg_constraint c
    join pg_class      r on r.oid = c.conrelid
    join pg_namespace  n on n.oid = r.relnamespace
    where n.nspname = 'n8n_brain'
      and r.relname = t.name
      and c.conname = t.name || '_scope_type_check'
  )
  -- Already migrated is not drift: a second run finds the new constraint under
  -- the same name and must still be a no-op.
  and not exists (
    select 1
    from pg_constraint c
    join pg_class      r on r.oid = c.conrelid
    join pg_namespace  n on n.oid = r.relnamespace
    where n.nspname = 'n8n_brain'
      and r.relname = t.name
      and c.conname = t.name || '_scope_type_v1_check'
  );

  if missing is not null then
    raise exception
      'expected pre-migration scope_type CHECK missing on: % — storage has drifted from Brain-V1-A; stop and reconcile',
      missing;
  end if;
end
$pre$;

-- ---------------------------------------------------------------------------
-- operational_experiences
-- ---------------------------------------------------------------------------

alter table n8n_brain.operational_experiences
  drop constraint if exists operational_experiences_scope_type_check;
alter table n8n_brain.operational_experiences
  drop constraint if exists operational_experiences_scope_type_v1_check;

-- Named explicitly. The inline CHECK this replaces carried a Postgres-generated
-- name, which is not something a later migration should have to guess at.
alter table n8n_brain.operational_experiences
  add constraint operational_experiences_scope_type_v1_check
  check (scope_type in (
    'GLOBAL_VORQUEL','VERTICAL','ENTITY','CLIENT','PROJECT','PRIVATE_TEST'));

-- ---------------------------------------------------------------------------
-- build_runs
-- ---------------------------------------------------------------------------

alter table n8n_brain.build_runs
  drop constraint if exists build_runs_scope_type_check;
alter table n8n_brain.build_runs
  drop constraint if exists build_runs_scope_type_v1_check;

alter table n8n_brain.build_runs
  add constraint build_runs_scope_type_v1_check
  check (scope_type in (
    'GLOBAL_VORQUEL','VERTICAL','ENTITY','CLIENT','PROJECT','PRIVATE_TEST'));

-- ---------------------------------------------------------------------------
-- The scope-shape rule is unchanged and still holds: GLOBAL_VORQUEL is
-- addressable only as 'GLOBAL', and 'GLOBAL' is reserved for it. VERTICAL and
-- ENTITY therefore carry ordinary scope_ids and cannot impersonate the global
-- scope. Restated here as a comment, not re-added, so there is exactly one
-- definition of it in the schema.
-- ---------------------------------------------------------------------------

comment on constraint operational_experiences_scope_type_v1_check
  on n8n_brain.operational_experiences is
  'Brain V1 contract scopes (DIV-3). Widened from four values by 20260922_006; no value was removed or redefined.';

comment on constraint build_runs_scope_type_v1_check
  on n8n_brain.build_runs is
  'Brain V1 contract scopes (DIV-3). Widened from four values by 20260922_006; no value was removed or redefined.';

commit;
