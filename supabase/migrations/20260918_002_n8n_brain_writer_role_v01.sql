begin;

do $$
begin
  if not exists (
    select 1
    from pg_roles
    where rolname = 'n8n_brain_writer'
  ) then
    create role n8n_brain_writer
      nologin
      noinherit
      nobypassrls;
  end if;
end
$$;

revoke all on schema n8n_brain from n8n_brain_writer;
grant usage on schema n8n_brain to n8n_brain_writer;

revoke all on all tables in schema n8n_brain from n8n_brain_writer;
grant select, insert on n8n_brain.source_snapshots to n8n_brain_writer;
grant select, insert on n8n_brain.workflow_analyses to n8n_brain_writer;
grant select, insert on n8n_brain.knowledge_items to n8n_brain_writer;

drop policy if exists n8n_brain_writer_select
  on n8n_brain.source_snapshots;
create policy n8n_brain_writer_select
  on n8n_brain.source_snapshots
  for select
  to n8n_brain_writer
  using (true);

drop policy if exists n8n_brain_writer_insert
  on n8n_brain.source_snapshots;
create policy n8n_brain_writer_insert
  on n8n_brain.source_snapshots
  for insert
  to n8n_brain_writer
  with check (true);

drop policy if exists n8n_brain_writer_select
  on n8n_brain.workflow_analyses;
create policy n8n_brain_writer_select
  on n8n_brain.workflow_analyses
  for select
  to n8n_brain_writer
  using (true);

drop policy if exists n8n_brain_writer_insert
  on n8n_brain.workflow_analyses;
create policy n8n_brain_writer_insert
  on n8n_brain.workflow_analyses
  for insert
  to n8n_brain_writer
  with check (true);

drop policy if exists n8n_brain_writer_select
  on n8n_brain.knowledge_items;
create policy n8n_brain_writer_select
  on n8n_brain.knowledge_items
  for select
  to n8n_brain_writer
  using (true);

drop policy if exists n8n_brain_writer_insert
  on n8n_brain.knowledge_items;
create policy n8n_brain_writer_insert
  on n8n_brain.knowledge_items
  for insert
  to n8n_brain_writer
  with check (true);

commit;
