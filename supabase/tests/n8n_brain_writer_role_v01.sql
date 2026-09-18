\set ON_ERROR_STOP on

do $$
declare
  role_exists boolean;
  policy_count integer;
  postgres_can_set_writer boolean;
begin
  select exists(
    select 1 from pg_roles where rolname = 'n8n_brain_writer'
  ) into role_exists;

  if not role_exists then
    raise exception 'n8n_brain_writer role is missing';
  end if;

  select exists(
    select 1
    from pg_auth_members m
    join pg_roles granted_role on granted_role.oid = m.roleid
    join pg_roles member_role on member_role.oid = m.member
    where granted_role.rolname = 'n8n_brain_writer'
      and member_role.rolname = 'postgres'
      and m.set_option
      and not m.inherit_option
  ) into postgres_can_set_writer;

  if not postgres_can_set_writer then
    raise exception 'postgres must have SET TRUE / INHERIT FALSE membership';
  end if;

  if not has_schema_privilege(
    'n8n_brain_writer',
    'n8n_brain',
    'USAGE'
  ) then
    raise exception 'writer role lacks schema usage';
  end if;

  if not has_table_privilege(
    'n8n_brain_writer',
    'n8n_brain.source_snapshots',
    'SELECT'
  ) or not has_table_privilege(
    'n8n_brain_writer',
    'n8n_brain.source_snapshots',
    'INSERT'
  ) then
    raise exception 'writer role lacks required source privileges';
  end if;

  if has_table_privilege(
    'n8n_brain_writer',
    'n8n_brain.source_snapshots',
    'UPDATE'
  ) or has_table_privilege(
    'n8n_brain_writer',
    'n8n_brain.source_snapshots',
    'DELETE'
  ) or has_table_privilege(
    'n8n_brain_writer',
    'n8n_brain.source_snapshots',
    'TRUNCATE'
  ) then
    raise exception 'writer role has forbidden source privileges';
  end if;

  if has_table_privilege(
    'n8n_brain_writer',
    'n8n_brain.workflow_analyses',
    'UPDATE'
  ) or has_table_privilege(
    'n8n_brain_writer',
    'n8n_brain.workflow_analyses',
    'DELETE'
  ) or has_table_privilege(
    'n8n_brain_writer',
    'n8n_brain.knowledge_items',
    'UPDATE'
  ) or has_table_privilege(
    'n8n_brain_writer',
    'n8n_brain.knowledge_items',
    'DELETE'
  ) then
    raise exception 'writer role has forbidden mutation privileges';
  end if;

  select count(*)
  from pg_policies
  where schemaname = 'n8n_brain'
    and policyname in (
      'n8n_brain_writer_select',
      'n8n_brain_writer_insert'
    )
    and tablename in (
      'source_snapshots',
      'workflow_analyses',
      'knowledge_items'
    )
  into policy_count;

  if policy_count <> 6 then
    raise exception 'expected 6 writer RLS policies, got %', policy_count;
  end if;

  if (
    select rolbypassrls
    from pg_roles
    where rolname = 'n8n_brain_writer'
  ) then
    raise exception 'writer role must not bypass RLS';
  end if;
end
$$;

begin;
set local role n8n_brain_writer;

insert into n8n_brain.source_snapshots (
  source_repo,
  source_commit,
  source_path,
  content_sha256
) values (
  'vorquel/security-role-test',
  repeat('a', 40),
  'fixtures/role-smoke.json',
  repeat('b', 64)
);

select count(*)
from n8n_brain.source_snapshots
where source_repo = 'vorquel/security-role-test';

rollback;

select 'n8n_brain writer role V0.1 tests passed' as result;
