# n8n Controlled Ingest V0.1

Human-gated orchestration for the n8n Brain.

The planner may discover strict-safe candidates, but it **cannot persist** anything.
The ingestor may persist only workflows explicitly listed in a reviewed manifest.

## First-ingestion policy

`STRICT_REFERENCE_V01` accepts only workflows that compile to:

- `SAFE_FOR_LEARNING`
- `REFERENCE_PATTERN`
- zero security findings
- zero `UNTRUSTED_TEXT`
- zero executable snippet metadata
- zero credential types
- at least one node

This policy is intentionally narrower than `SAFE_FOR_LEARNING`.

## Plan

```bash
vorquel-n8n-plan /path/to/pinned/corpus \
  --source-repo JustInCache/n8n-workflows \
  --source-commit 5a7864987c22930521382b597873b713cc830dac \
  --count 4 \
  --output manifest.json
```

Planning never connects to PostgreSQL.

## Dry-run ingestion

```bash
vorquel-n8n-ingest /path/to/pinned/corpus manifest.json
```

Dry-run is the default.

## Persist

```bash
export N8N_BRAIN_DATABASE_URL='postgresql://...'
vorquel-n8n-ingest /path/to/pinned/corpus manifest.json --persist
```

The ingestor re-reads, re-hashes, re-analyzes, re-compiles and re-validates every manifest entry before opening the database connection.

V0.1 hard cap: 4 items per manifest.
