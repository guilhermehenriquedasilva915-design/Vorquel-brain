begin;

create schema if not exists n8n_brain;

revoke all on schema n8n_brain from public;
revoke all on schema n8n_brain from anon;
revoke all on schema n8n_brain from authenticated;
grant usage on schema n8n_brain to service_role;

alter default privileges for role postgres in schema n8n_brain
  revoke all on tables from public, anon, authenticated;
alter default privileges for role postgres in schema n8n_brain
  revoke all on sequences from public, anon, authenticated;
alter default privileges for role postgres in schema n8n_brain
  revoke execute on functions from public, anon, authenticated;

alter default privileges for role postgres in schema n8n_brain
  grant select, insert on tables to service_role;
alter default privileges for role postgres in schema n8n_brain
  grant usage, select on sequences to service_role;

create table n8n_brain.source_snapshots (
  id uuid primary key default gen_random_uuid(),
  source_repo text not null,
  source_commit text not null,
  source_path text not null,
  content_sha256 text not null,
  source_kind text not null default 'N8N_WORKFLOW_JSON',
  trust_level text not null default 'RAW_UNTRUSTED',
  created_at timestamptz not null default now(),

  constraint source_repo_nonempty
    check (length(source_repo) between 1 and 512),
  constraint source_commit_is_git_hash
    check (source_commit ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'),
  constraint source_path_nonempty
    check (length(source_path) between 1 and 2048),
  constraint content_sha256_is_hex
    check (content_sha256 ~ '^[0-9a-f]{64}$'),
  constraint source_kind_v01
    check (source_kind = 'N8N_WORKFLOW_JSON'),
  constraint trust_level_v01
    check (trust_level = 'RAW_UNTRUSTED'),
  constraint source_snapshot_idempotency
    unique (source_repo, source_commit, source_path, content_sha256)
);

create table n8n_brain.workflow_analyses (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null
    references n8n_brain.source_snapshots(id) on delete restrict,
  analyzer_version text not null,
  risk_decision text not null,
  max_severity text not null,
  findings jsonb not null default '[]'::jsonb,
  analyzed_at timestamptz not null default now(),

  constraint analyzer_version_nonempty
    check (length(analyzer_version) between 1 and 128),
  constraint risk_decision_v01
    check (risk_decision in ('SAFE_FOR_LEARNING', 'REVIEW_REQUIRED', 'BLOCKED')),
  constraint max_severity_v01
    check (max_severity in ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
  constraint findings_is_array
    check (jsonb_typeof(findings) = 'array'),
  constraint findings_no_raw_evidence
    check (not jsonb_path_exists(findings, '$.**.evidence')),
  constraint workflow_analysis_idempotency
    unique (source_id, analyzer_version)
);

create table n8n_brain.knowledge_items (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid not null
    references n8n_brain.workflow_analyses(id) on delete restrict,
  compiler_schema_version text not null,
  source_content_trust text not null default 'UNTRUSTED_SOURCE_DATA',
  knowledge_role text not null,
  learning_scope text not null,
  structure jsonb not null,
  untrusted_text jsonb not null default '[]'::jsonb,
  executable_metadata jsonb not null default '[]'::jsonb,
  security_findings jsonb not null default '[]'::jsonb,
  implementation_reference_allowed boolean not null default false,
  vorquel_validated boolean not null default false,
  compiled_at timestamptz not null default now(),

  constraint compiler_schema_version_nonempty
    check (length(compiler_schema_version) between 1 and 128),
  constraint source_content_trust_v01
    check (source_content_trust = 'UNTRUSTED_SOURCE_DATA'),
  constraint knowledge_role_v01
    check (
      knowledge_role in (
        'REFERENCE_PATTERN',
        'STRUCTURE_REFERENCE_RESTRICTED',
        'QUARANTINED_REFERENCE',
        'SECURITY_EXAMPLE'
      )
    ),
  constraint learning_scope_v01
    check (
      (knowledge_role = 'REFERENCE_PATTERN'
        and learning_scope = 'structure_and_metadata')
      or
      (knowledge_role = 'STRUCTURE_REFERENCE_RESTRICTED'
        and learning_scope = 'structure_only')
      or
      (knowledge_role = 'QUARANTINED_REFERENCE'
        and learning_scope = 'review_only')
      or
      (knowledge_role = 'SECURITY_EXAMPLE'
        and learning_scope = 'security_only')
    ),
  constraint structure_is_object
    check (jsonb_typeof(structure) = 'object'),
  constraint untrusted_text_is_array
    check (jsonb_typeof(untrusted_text) = 'array'),
  constraint executable_metadata_is_array
    check (jsonb_typeof(executable_metadata) = 'array'),
  constraint security_findings_is_array
    check (jsonb_typeof(security_findings) = 'array'),
  constraint security_findings_no_raw_evidence
    check (not jsonb_path_exists(security_findings, '$.**.evidence')),
  constraint executable_metadata_no_content
    check (not jsonb_path_exists(executable_metadata, '$.**.content')),
  constraint executable_metadata_no_code
    check (not jsonb_path_exists(executable_metadata, '$.**.code')),
  constraint executable_metadata_no_command
    check (not jsonb_path_exists(executable_metadata, '$.**.command')),
  constraint no_implementation_reference_v01
    check (implementation_reference_allowed = false),
  constraint not_validated_v01
    check (vorquel_validated = false),
  constraint knowledge_item_idempotency
    unique (analysis_id, compiler_schema_version)
);

alter table n8n_brain.source_snapshots enable row level security;
alter table n8n_brain.workflow_analyses enable row level security;
alter table n8n_brain.knowledge_items enable row level security;

revoke all on all tables in schema n8n_brain from public, anon, authenticated;
revoke all on all sequences in schema n8n_brain from public, anon, authenticated;

grant select, insert on n8n_brain.source_snapshots to service_role;
grant select, insert on n8n_brain.workflow_analyses to service_role;
grant select, insert on n8n_brain.knowledge_items to service_role;

create index source_snapshots_repo_commit_idx
  on n8n_brain.source_snapshots (source_repo, source_commit);

create index workflow_analyses_risk_idx
  on n8n_brain.workflow_analyses (risk_decision, max_severity);

create index knowledge_items_role_idx
  on n8n_brain.knowledge_items (knowledge_role, learning_scope);

create index knowledge_items_structure_gin_idx
  on n8n_brain.knowledge_items using gin (structure jsonb_path_ops);

commit;
