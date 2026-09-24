-- 20260922_006: widen the operational scope vocabulary to the six contract scopes
--
-- DIV-3 in docs/BRAIN_CONTRACT_V1_RECONCILIATION.md recorded a deliberate gap:
-- the Brain V1 contract defines six scopes, storage accepted four, and
-- Brain-V1-A ran no migration. This is the migration that gap was deferred to.
--
--   contract (Brain-V1-A):  GLOBAL_VORQUEL VERTICAL ENTITY CLIENT PROJECT PRIVATE_TEST
--   storage  (legacy):      GLOBAL_VORQUEL                 CLIENT PROJECT PRIVATE_TEST
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
--
-- WHAT THIS MIGRATION CHECKS BEFORE IT CHANGES ANYTHING
-- ----------------------------------------------------
-- It reads the **actual definition** of the constraint, via
-- pg_get_constraintdef, and classifies each of the two tables independently. A
-- constraint name is used only to confirm the expected name is also in place;
-- it is never taken as evidence of what the constraint means.
--
-- An earlier version of this migration checked that a constraint with the
-- expected *name* existed and treated that as sufficient. A database holding
--
--     operational_experiences_scope_type_v1_check
--       CHECK (scope_type IN ('GLOBAL_VORQUEL','CLIENT'))
--
-- therefore passed the preflight, and the drifted constraint was then dropped
-- and silently replaced with the six-value definition. That is silent repair of
-- a load-bearing storage contract, and refusing it is the entire point of the
-- block below.
--
-- Each table classifies as one of four states:
--
--   LEGACY_EXACT  one membership CHECK on scope_type, admitting precisely the
--                 four legacy values, under the name <table>_scope_type_check
--   V1_EXACT      one membership CHECK on scope_type, admitting precisely the
--                 six contract values, under the name <table>_scope_type_v1_check
--   MISSING       no membership CHECK on scope_type at all
--   DRIFT         anything else — a different value set, a duplicate, a shape
--                 that is not a plain membership test, or an exact value set
--                 under an unexpected name
--
-- and the pair of states decides what happens:
--
--   both LEGACY_EXACT  ->  widen
--   both V1_EXACT      ->  true no-op. No DROP, no re-create, no DDL at all.
--   anything else      ->  raise, having changed nothing
--
-- Mixed state — one table legacy, one already V1 — fails closed rather than
-- being "completed". A half-applied migration is evidence that something
-- happened outside this file, and finishing the job would destroy that evidence
-- along with any chance of understanding what it was.
--
-- Classification happens in full before the first mutation, inside one
-- transaction, so a refusal leaves every constraint, row and table exactly as
-- it found them.
--
-- Comparison is on the *value set*, not on text. The definition is normalised
-- (whitespace and casts removed) and matched against the shape of a plain
-- membership test, then the literals are extracted and compared as a sorted
-- set. Reordering the values is not drift and reformatting is not drift; a
-- negated or compound condition is drift even when it mentions the right
-- values, because it no longer means what the contract says.
--
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
-- If both are empty, drop the _v1_check constraints and restore the four-value
-- ones under their original names. If either returns rows, narrowing would
-- orphan real records: the rows must be rescoped or removed by an explicit,
-- reviewed decision first. This migration ships no automatic down-step, because
-- a down-step that deletes rows to make a constraint fit is the failure mode the
-- Brain exists to prevent.
--
-- IDEMPOTENCE
-- -----------
-- Re-running against an already-migrated database is a **true no-op**: the
-- classifier finds V1_EXACT on both tables and returns without issuing any DDL.
-- The constraints keep their original OIDs, which is what the companion test
-- checks. A drop-and-recreate of an identical constraint would look idempotent
-- from the outside while rewriting catalogue state on every run, and would give
-- a drifted database a second chance to be silently overwritten.

begin;

do $migration$
declare
  --------------------------------------------------------------------------
  -- The two value sets this migration knows about, pre-sorted so comparison is
  -- order-independent.
  --------------------------------------------------------------------------
  legacy_values constant text[] := array[
    'CLIENT', 'GLOBAL_VORQUEL', 'PRIVATE_TEST', 'PROJECT'];
  v1_values     constant text[] := array[
    'CLIENT', 'ENTITY', 'GLOBAL_VORQUEL', 'PRIVATE_TEST', 'PROJECT', 'VERTICAL'];

  -- A plain membership test on scope_type and nothing else. Anything not
  -- matching this shape is drift whatever values it mentions: a negation, an
  -- extra AND, or a test on another column all fail here rather than having
  -- their literals extracted and compared as if they meant the same thing.
  membership_shape constant text :=
    '^CHECK\(\(scope_type=ANY\(ARRAY\[(.+)\]\)\)\)$';

  target       text;
  relation     regclass;
  constraint_name text;
  definition   text;
  normalised   text;
  matched      text[];
  literals     text[];
  deduped      text[];
  literal      text;
  found_count  int;
  found_name   text;
  found_values text[];
  unparsable   boolean;

  state        text;
  detail       text;
  oe_state     text;
  oe_name      text;
  oe_detail    text;
  br_state     text;
  br_name      text;
  br_detail    text;
begin
  --------------------------------------------------------------------------
  -- Lock first, then classify.
  --
  -- Reading the catalogue takes no lock, so without this the state could change
  -- between the classification and the widening and the migration would act on
  -- a picture that was already stale — the same class of mistake as trusting a
  -- constraint name, just with a smaller window. ACCESS EXCLUSIVE is what ALTER
  -- TABLE would take anyway; taking it up front makes "classify everything
  -- before mutating anything" a guarantee rather than an intention. Both locks
  -- are held to the end of the transaction.
  --------------------------------------------------------------------------
  lock table n8n_brain.operational_experiences, n8n_brain.build_runs
    in access exclusive mode;

  --------------------------------------------------------------------------
  -- Classify both tables. Nothing is mutated anywhere in this loop.
  --------------------------------------------------------------------------
  foreach target in array array['operational_experiences', 'build_runs'] loop
    relation := to_regclass('n8n_brain.' || target);
    if relation is null then
      raise exception
        'n8n_brain.% does not exist; this migration widens an existing '
        'constraint and will not create the table', target;
    end if;

    found_count  := 0;
    found_name   := null;
    found_values := null;
    unparsable   := false;

    -- Located by *definition*, not by name. Looking the constraint up by name
    -- would make the name the authority, which is the defect this version
    -- removes. The table also carries a scope-shape CHECK mentioning
    -- scope_type, so the shape match is what tells the two apart.
    for constraint_name, definition in
      select c.conname, pg_get_constraintdef(c.oid)
      from pg_constraint c
      where c.conrelid = relation
        and c.contype = 'c'
      order by c.conname
    loop
      normalised := regexp_replace(definition, '\s+', '', 'g');
      normalised := regexp_replace(normalised, '::[a-zA-Z]+', '', 'g');
      matched := regexp_match(normalised, membership_shape);

      if matched is not null then
        found_count := found_count + 1;
        if found_count = 1 then
          found_name := constraint_name;

          -- Every literal must be a bare upper-case identifier. One that is not
          -- means the constraint is doing something this migration does not
          -- understand, and not understanding it is drift, never permission.
          literals := array[]::text[];
          foreach literal in array string_to_array(matched[1], ',') loop
            literal := btrim(literal);
            if literal !~ '^''[A-Z_]+''$' then
              unparsable := true;
              exit;
            end if;
            literals := literals || btrim(literal, '''');
          end loop;
          found_values := literals;
        end if;
      end if;
    end loop;

    if found_count = 0 then
      state  := 'MISSING';
      detail := 'no membership CHECK on scope_type';

    elsif found_count > 1 then
      state  := 'DRIFT';
      detail := format('%s membership CHECKs on scope_type; expected exactly one',
                       found_count);

    elsif unparsable then
      state  := 'DRIFT';
      detail := format('%s admits a value this migration cannot parse', found_name);

    else
      -- Compare as a sorted set. Reordering is not drift; a repeated value is,
      -- because it means the constraint was written by something other than
      -- this migration or its predecessor.
      select array_agg(v order by v) into deduped
      from (select distinct unnest(found_values) as v) d;

      if array_length(deduped, 1) is distinct from array_length(found_values, 1) then
        state  := 'DRIFT';
        detail := format('%s repeats a value', found_name);

      elsif deduped = legacy_values then
        if found_name = target || '_scope_type_check' then
          state  := 'LEGACY_EXACT';
          detail := found_name;
        else
          state  := 'DRIFT';
          detail := format(
            'the legacy four-value set is present but under the unexpected name '
            '%s (expected %s_scope_type_check)', found_name, target);
        end if;

      elsif deduped = v1_values then
        if found_name = target || '_scope_type_v1_check' then
          state  := 'V1_EXACT';
          detail := found_name;
        else
          state  := 'DRIFT';
          detail := format(
            'the six-value contract set is present but under the unexpected name '
            '%s (expected %s_scope_type_v1_check)', found_name, target);
        end if;

      else
        state  := 'DRIFT';
        detail := format(
          '%s admits {%s}; expected either the legacy {%s} or the contract {%s}',
          found_name,
          array_to_string(deduped, ','),
          array_to_string(legacy_values, ','),
          array_to_string(v1_values, ','));
      end if;
    end if;

    if target = 'operational_experiences' then
      oe_state := state; oe_name := found_name; oe_detail := detail;
    else
      br_state := state; br_name := found_name; br_detail := detail;
    end if;
  end loop;

  --------------------------------------------------------------------------
  -- Decide. Still nothing mutated.
  --------------------------------------------------------------------------

  if oe_state = 'V1_EXACT' and br_state = 'V1_EXACT' then
    -- True no-op: no DDL is issued at all, so the constraints keep their OIDs.
    raise notice
      'scope_type already admits the six contract scopes on both tables; '
      'no changes made (%, %)', oe_name, br_name;
    return;
  end if;

  if oe_state is distinct from 'LEGACY_EXACT'
     or br_state is distinct from 'LEGACY_EXACT' then
    raise exception
      'refusing to migrate: storage is not in a state this migration can widen. '
      'n8n_brain.operational_experiences: % (%). n8n_brain.build_runs: % (%). '
      'Both tables must hold exactly the legacy four-value scope_type CHECK, to '
      'widen, or both must already hold exactly the six-value contract CHECK, '
      'which is a no-op. A mixed, drifted or missing state is never repaired '
      'automatically: silently rewriting a load-bearing constraint would destroy '
      'the evidence of how it came to be wrong. Reconcile by hand, then re-run.',
      oe_state, oe_detail, br_state, br_detail;
  end if;

  --------------------------------------------------------------------------
  -- Widen. Reached only when both tables are exactly legacy.
  --------------------------------------------------------------------------

  -- Dropped by the name the classifier actually found, not by an assumed one.
  execute format(
    'alter table n8n_brain.operational_experiences drop constraint %I', oe_name);

  -- Dollar-quoted so the value list reads exactly as it would in a plain
  -- statement. Doubling every quote to embed it in an ordinary string literal
  -- would leave the list unreadable here and, worse, unparseable by the enum
  -- parity check in packages/brain-retrieval, which reads these migrations as
  -- the third layer it compares. The DDL has to be built dynamically because it
  -- runs conditionally; it does not have to become unreadable to do so.
  execute $ddl$
    alter table n8n_brain.operational_experiences
      add constraint operational_experiences_scope_type_v1_check
      check (scope_type in (
        'GLOBAL_VORQUEL','VERTICAL','ENTITY','CLIENT','PROJECT','PRIVATE_TEST'))
  $ddl$;

  execute format(
    'alter table n8n_brain.build_runs drop constraint %I', br_name);
  execute $ddl$
    alter table n8n_brain.build_runs
      add constraint build_runs_scope_type_v1_check
      check (scope_type in (
        'GLOBAL_VORQUEL','VERTICAL','ENTITY','CLIENT','PROJECT','PRIVATE_TEST'))
  $ddl$;

  -- The scope-shape rule is untouched and still holds: GLOBAL_VORQUEL is
  -- addressable only as 'GLOBAL', and 'GLOBAL' is reserved for it. VERTICAL and
  -- ENTITY therefore carry ordinary scope_ids and cannot impersonate the global
  -- scope. It is not re-added here, so there stays exactly one definition of it.

  execute $ddl$
    comment on constraint operational_experiences_scope_type_v1_check
      on n8n_brain.operational_experiences is
      'Brain V1 contract scopes (DIV-3). Widened from four values by 20260922_006; no value was removed or redefined.'
  $ddl$;

  execute $ddl$
    comment on constraint build_runs_scope_type_v1_check
      on n8n_brain.build_runs is
      'Brain V1 contract scopes (DIV-3). Widened from four values by 20260922_006; no value was removed or redefined.'
  $ddl$;

  raise notice
    'scope_type widened to the six contract scopes on both tables (was %, %)',
    oe_name, br_name;
end
$migration$;

commit;
