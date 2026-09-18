\set ON_ERROR_STOP on

select plan(25);

select has_schema('n8n_brain', 'n8n_brain schema exists');
select has_table('n8n_brain', 'source_snapshots', 'source snapshots table exists');
select has_table('n8n_brain', 'workflow_analyses', 'workflow analyses table exists');
select has_table('n8n_brain', 'knowledge_items', 'knowledge items table exists');

select is(
  has_schema_privilege('anon', 'n8n_brain', 'USAGE'),
  false,
  'anon has no schema usage'
);
select is(
  has_schema_privilege('authenticated', 'n8n_brain', 'USAGE'),
  false,
  'authenticated has no schema usage'
);
select is(
  has_schema_privilege('service_role', 'n8n_brain', 'USAGE'),
  true,
  'service_role has schema usage'
);

select is(
  has_table_privilege('service_role', 'n8n_brain.source_snapshots', 'SELECT'),
  true,
  'service_role can select sources'
);
select is(
  has_table_privilege('service_role', 'n8n_brain.source_snapshots', 'INSERT'),
  true,
  'service_role can insert sources'
);
select is(
  has_table_privilege('service_role', 'n8n_brain.source_snapshots', 'UPDATE'),
  false,
  'service_role cannot update sources'
);
select is(
  has_table_privilege('service_role', 'n8n_brain.source_snapshots', 'DELETE'),
  false,
  'service_role cannot delete sources'
);

select is(
  (select relrowsecurity from pg_class c
   join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'n8n_brain' and c.relname = 'source_snapshots'),
  true,
  'RLS enabled on source_snapshots'
);
select is(
  (select relrowsecurity from pg_class c
   join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'n8n_brain' and c.relname = 'workflow_analyses'),
  true,
  'RLS enabled on workflow_analyses'
);
select is(
  (select relrowsecurity from pg_class c
   join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'n8n_brain' and c.relname = 'knowledge_items'),
  true,
  'RLS enabled on knowledge_items'
);

insert into n8n_brain.source_snapshots (
  source_repo,
  source_commit,
  source_path,
  content_sha256
) values (
  'JustInCache/n8n-workflows',
  '5a7864987c22930521382b597873b713cc830dac',
  'workflows/Example/0001.json',
  repeat('a', 64)
);

select is(
  (select count(*)::integer from n8n_brain.source_snapshots),
  1,
  'valid source insert succeeds'
);

insert into n8n_brain.workflow_analyses (
  source_id,
  analyzer_version,
  risk_decision,
  max_severity,
  findings
) select
  id,
  '0.1.0',
  'SAFE_FOR_LEARNING',
  'MEDIUM',
  '[{"rule_id":"NETWORK_REQUEST","severity":"MEDIUM"}]'::jsonb
from n8n_brain.source_snapshots
limit 1;

select is(
  (select count(*)::integer from n8n_brain.workflow_analyses),
  1,
  'valid analysis insert succeeds'
);

insert into n8n_brain.knowledge_items (
  analysis_id,
  compiler_schema_version,
  source_content_trust,
  knowledge_role,
  learning_scope,
  structure,
  untrusted_text,
  executable_metadata,
  security_findings
) select
  id,
  '0.1',
  'UNTRUSTED_SOURCE_DATA',
  'STRUCTURE_REFERENCE_RESTRICTED',
  'structure_only',
  '{"node_count":2,"node_types":{"n8n-nodes-base.httpRequest":1}}'::jsonb,
  '[{"kind":"UNTRUSTED_TEXT","sha256":"abc"}]'::jsonb,
  '[{"kind":"EXECUTABLE_SNIPPET_UNTRUSTED","content_persisted":false,"sha256":"def"}]'::jsonb,
  '[{"rule_id":"NETWORK_REQUEST","severity":"MEDIUM"}]'::jsonb
from n8n_brain.workflow_analyses
limit 1;

select is(
  (select count(*)::integer from n8n_brain.knowledge_items),
  1,
  'valid knowledge item insert succeeds'
);

select throws_ok(
  $$insert into n8n_brain.source_snapshots
    (source_repo, source_commit, source_path, content_sha256, trust_level)
    values ('repo/name', repeat('b', 40), 'x.json', repeat('c', 64), 'TRUSTED')$$,
  '23514',
  null,
  'non-RAW source is rejected'
);

select throws_ok(
  $$insert into n8n_brain.workflow_analyses
    (source_id, analyzer_version, risk_decision, max_severity, findings)
    select id, 'bad-evidence', 'REVIEW_REQUIRED', 'HIGH',
      '[{"rule_id":"X","evidence":"raw-secret"}]'::jsonb
    from n8n_brain.source_snapshots limit 1$$,
  '23514',
  null,
  'raw finding evidence is rejected'
);

select throws_ok(
  $$insert into n8n_brain.knowledge_items
    (analysis_id, compiler_schema_version, knowledge_role, learning_scope, structure,
     implementation_reference_allowed)
    select id, 'bad-impl', 'STRUCTURE_REFERENCE_RESTRICTED', 'structure_only',
      '{}'::jsonb, true
    from n8n_brain.workflow_analyses limit 1$$,
  '23514',
  null,
  'implementation authorization is rejected in V0.1'
);

select throws_ok(
  $$insert into n8n_brain.knowledge_items
    (analysis_id, compiler_schema_version, knowledge_role, learning_scope, structure,
     vorquel_validated)
    select id, 'bad-validation', 'STRUCTURE_REFERENCE_RESTRICTED', 'structure_only',
      '{}'::jsonb, true
    from n8n_brain.workflow_analyses limit 1$$,
  '23514',
  null,
  'VORQUEL_VALIDATED cannot be set in V0.1'
);

select throws_ok(
  $$insert into n8n_brain.knowledge_items
    (analysis_id, compiler_schema_version, knowledge_role, learning_scope, structure,
     executable_metadata)
    select id, 'bad-command', 'STRUCTURE_REFERENCE_RESTRICTED', 'structure_only',
      '{}'::jsonb, '[{"command":"rm -rf /"}]'::jsonb
    from n8n_brain.workflow_analyses limit 1$$,
  '23514',
  null,
  'raw command field is rejected'
);

select throws_ok(
  $$insert into n8n_brain.knowledge_items
    (analysis_id, compiler_schema_version, knowledge_role, learning_scope, structure,
     executable_metadata)
    select id, 'bad-code', 'STRUCTURE_REFERENCE_RESTRICTED', 'structure_only',
      '{}'::jsonb, '[{"code":"eval(input)"}]'::jsonb
    from n8n_brain.workflow_analyses limit 1$$,
  '23514',
  null,
  'raw code field is rejected'
);

select throws_ok(
  $$insert into n8n_brain.knowledge_items
    (analysis_id, compiler_schema_version, knowledge_role, learning_scope, structure,
     security_findings)
    select id, 'bad-security-evidence', 'STRUCTURE_REFERENCE_RESTRICTED', 'structure_only',
      '{}'::jsonb, '[{"rule_id":"X","evidence":"raw"}]'::jsonb
    from n8n_brain.workflow_analyses limit 1$$,
  '23514',
  null,
  'raw security finding evidence is rejected'
);

select throws_ok(
  $$insert into n8n_brain.knowledge_items
    (analysis_id, compiler_schema_version, knowledge_role, learning_scope, structure)
    select id, 'bad-role-pair', 'SECURITY_EXAMPLE', 'structure_only', '{}'::jsonb
    from n8n_brain.workflow_analyses limit 1$$,
  '23514',
  null,
  'invalid role/scope pair is rejected'
);

select lives_ok(
  $$insert into n8n_brain.source_snapshots
    (source_repo, source_commit, source_path, content_sha256)
    values (
      'JustInCache/n8n-workflows',
      '5a7864987c22930521382b597873b713cc830dac',
      'workflows/Example/0001.json',
      repeat('a', 64)
    )
    on conflict (source_repo, source_commit, source_path, content_sha256) do nothing$$,
  'source ingestion is idempotent with ON CONFLICT'
);

select is(
  (select count(*)::integer from n8n_brain.source_snapshots),
  1,
  'idempotent source ingestion does not duplicate'
);

select * from finish();
