\set ON_ERROR_STOP on

do $$
declare
  source_uuid uuid;
  analysis_uuid uuid;
begin
  if to_regnamespace('n8n_brain') is null then
    raise exception 'n8n_brain schema missing';
  end if;

  if to_regclass('n8n_brain.source_snapshots') is null
     or to_regclass('n8n_brain.workflow_analyses') is null
     or to_regclass('n8n_brain.knowledge_items') is null then
    raise exception 'one or more n8n_brain tables are missing';
  end if;

  if has_schema_privilege('anon', 'n8n_brain', 'USAGE')
     or has_schema_privilege('authenticated', 'n8n_brain', 'USAGE') then
    raise exception 'client role unexpectedly has n8n_brain schema usage';
  end if;

  if not has_schema_privilege('service_role', 'n8n_brain', 'USAGE') then
    raise exception 'service_role lacks n8n_brain schema usage';
  end if;

  if not has_table_privilege(
      'service_role', 'n8n_brain.source_snapshots', 'SELECT'
    )
    or not has_table_privilege(
      'service_role', 'n8n_brain.source_snapshots', 'INSERT'
    )
    or has_table_privilege(
      'service_role', 'n8n_brain.source_snapshots', 'UPDATE'
    )
    or has_table_privilege(
      'service_role', 'n8n_brain.source_snapshots', 'DELETE'
    ) then
    raise exception 'service_role source_snapshots grants are incorrect';
  end if;

  if (
    select count(*)
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'n8n_brain'
      and c.relname in (
        'source_snapshots',
        'workflow_analyses',
        'knowledge_items'
      )
      and c.relrowsecurity
  ) <> 3 then
    raise exception 'RLS is not enabled on all n8n_brain tables';
  end if;

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
  )
  returning id into source_uuid;

  insert into n8n_brain.workflow_analyses (
    source_id,
    analyzer_version,
    risk_decision,
    max_severity,
    findings
  ) values (
    source_uuid,
    '0.1.0',
    'SAFE_FOR_LEARNING',
    'MEDIUM',
    '[{"rule_id":"NETWORK_REQUEST","severity":"MEDIUM"}]'::jsonb
  )
  returning id into analysis_uuid;

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
  ) values (
    analysis_uuid,
    '0.1',
    'UNTRUSTED_SOURCE_DATA',
    'STRUCTURE_REFERENCE_RESTRICTED',
    'structure_only',
    '{"node_count":2,"node_types":{"n8n-nodes-base.httpRequest":1}}'::jsonb,
    '[{"kind":"UNTRUSTED_TEXT","sha256":"abc"}]'::jsonb,
    '[{"kind":"EXECUTABLE_SNIPPET_UNTRUSTED","content_persisted":false,"sha256":"def"}]'::jsonb,
    '[{"rule_id":"NETWORK_REQUEST","severity":"MEDIUM"}]'::jsonb
  );

  if (select count(*) from n8n_brain.source_snapshots) <> 1
     or (select count(*) from n8n_brain.workflow_analyses) <> 1
     or (select count(*) from n8n_brain.knowledge_items) <> 1 then
    raise exception 'valid inserts did not persist exactly one row each';
  end if;

  begin
    insert into n8n_brain.source_snapshots (
      source_repo, source_commit, source_path, content_sha256, trust_level
    ) values (
      'repo/name', repeat('b', 40), 'x.json', repeat('c', 64), 'TRUSTED'
    );
    raise exception 'expected trust_level constraint failure';
  exception
    when check_violation then null;
  end;

  begin
    insert into n8n_brain.workflow_analyses (
      source_id, analyzer_version, risk_decision, max_severity, findings
    ) values (
      source_uuid, 'bad-evidence', 'REVIEW_REQUIRED', 'HIGH',
      '[{"rule_id":"X","evidence":"raw-secret"}]'::jsonb
    );
    raise exception 'expected raw evidence constraint failure';
  exception
    when check_violation then null;
  end;

  begin
    insert into n8n_brain.knowledge_items (
      analysis_id, compiler_schema_version, knowledge_role, learning_scope,
      structure, implementation_reference_allowed
    ) values (
      analysis_uuid, 'bad-impl', 'STRUCTURE_REFERENCE_RESTRICTED',
      'structure_only', '{}'::jsonb, true
    );
    raise exception 'expected implementation authorization constraint failure';
  exception
    when check_violation then null;
  end;

  begin
    insert into n8n_brain.knowledge_items (
      analysis_id, compiler_schema_version, knowledge_role, learning_scope,
      structure, vorquel_validated
    ) values (
      analysis_uuid, 'bad-validation', 'STRUCTURE_REFERENCE_RESTRICTED',
      'structure_only', '{}'::jsonb, true
    );
    raise exception 'expected validation constraint failure';
  exception
    when check_violation then null;
  end;

  begin
    insert into n8n_brain.knowledge_items (
      analysis_id, compiler_schema_version, knowledge_role, learning_scope,
      structure, executable_metadata
    ) values (
      analysis_uuid, 'bad-command', 'STRUCTURE_REFERENCE_RESTRICTED',
      'structure_only', '{}'::jsonb, '[{"command":"rm -rf /"}]'::jsonb
    );
    raise exception 'expected raw command constraint failure';
  exception
    when check_violation then null;
  end;

  begin
    insert into n8n_brain.knowledge_items (
      analysis_id, compiler_schema_version, knowledge_role, learning_scope,
      structure, executable_metadata
    ) values (
      analysis_uuid, 'bad-code', 'STRUCTURE_REFERENCE_RESTRICTED',
      'structure_only', '{}'::jsonb, '[{"code":"eval(input)"}]'::jsonb
    );
    raise exception 'expected raw code constraint failure';
  exception
    when check_violation then null;
  end;

  begin
    insert into n8n_brain.knowledge_items (
      analysis_id, compiler_schema_version, knowledge_role, learning_scope,
      structure, security_findings
    ) values (
      analysis_uuid, 'bad-security-evidence',
      'STRUCTURE_REFERENCE_RESTRICTED', 'structure_only', '{}'::jsonb,
      '[{"rule_id":"X","evidence":"raw"}]'::jsonb
    );
    raise exception 'expected raw security evidence constraint failure';
  exception
    when check_violation then null;
  end;

  begin
    insert into n8n_brain.knowledge_items (
      analysis_id, compiler_schema_version, knowledge_role, learning_scope,
      structure
    ) values (
      analysis_uuid, 'bad-role-pair', 'SECURITY_EXAMPLE',
      'structure_only', '{}'::jsonb
    );
    raise exception 'expected role/scope constraint failure';
  exception
    when check_violation then null;
  end;

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
  )
  on conflict (
    source_repo, source_commit, source_path, content_sha256
  ) do nothing;

  if (select count(*) from n8n_brain.source_snapshots) <> 1 then
    raise exception 'idempotent source insert created a duplicate';
  end if;
end
$$;

select 'n8n_brain knowledge store V0.1 migration tests passed' as result;
