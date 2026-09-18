# n8n Controlled Ingest V0.1

## Purpose

Create a human-gated path from a pinned third-party workflow snapshot into the n8n Brain without allowing discovery to become persistence automatically.

## Flow

```text
Pinned corpus
    |
    v
Planner (read-only)
    |
    | strict policy only
    v
Manifest with path + SHA-256 + risk metadata
    |
    | explicit review boundary
    v
Ingestor
    |
    +--> re-read
    +--> re-hash
    +--> re-analyze
    +--> re-compile
    +--> re-validate
    |
    +--> dry-run by default
    |
    '--> --persist only
            |
            v
       Knowledge Writer
            |
            v
       restricted DB role
```

## Why the manifest exists

The planner and writer are intentionally disconnected by a file boundary. A workflow merely being discovered cannot cause a database write.

The manifest contains only provenance and safety metadata. It does not contain workflow code, prompts, credentials, or raw analyzer evidence.

## Strict first-ingestion policy

Only `REFERENCE_PATTERN` items with INFO severity, no findings, no text previews, no executable metadata and no credential references are eligible.

This is a bootstrap policy, not a claim that the selected workflows are correct or recommended n8n designs.

They remain third-party `RAW_UNTRUSTED` / `UNTRUSTED_SOURCE_DATA` references and are not `VORQUEL_VALIDATED`.

## Hard limits

- max 4 items per manifest;
- max 5 MiB per workflow;
- symlinks forbidden;
- path traversal forbidden;
- source snapshot commit required;
- persistence is explicit;
- database secret only from environment.

## Next gate

After the strict 4-item real-corpus path passes in disposable PostgreSQL, run the same reviewed manifest against the canonical database, verify the 12 resulting rows (4 source + 4 analysis + 4 knowledge), then stop. Do not expand to the full corpus until retrieval/evaluation strategy is defined.
