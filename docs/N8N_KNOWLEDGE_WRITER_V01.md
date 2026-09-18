# n8n Knowledge Writer V0.1

## Purpose

The writer is the only application component in V0.1 allowed to turn a validated `N8N_KNOWLEDGE_ITEM` into database rows.

It is deliberately **not** an LLM tool.

## Data flow

```text
RAW_UNTRUSTED workflow
        ↓
Static Analyzer
        ↓
Knowledge Compiler
        ↓
N8N_KNOWLEDGE_ITEM
        ↓
Writer validation gate
        ↓
append-only transaction
        ↓
n8n_brain.source_snapshots
n8n_brain.workflow_analyses
n8n_brain.knowledge_items
```

## Immutability

The writer uses `INSERT ... ON CONFLICT DO NOTHING` plus a deterministic read-back.

If an immutable key already exists:

- semantically equal content = idempotent success;
- different content under the same analyzer/compiler version = fail closed with `ImmutableDriftError`.

There is no UPDATE or DELETE path.

## Secret handling

The database DSN is read only from `N8N_BRAIN_DATABASE_URL`.

It is not accepted as a CLI argument and is never included in normal output or database error messages.

## V0.1 restrictions

- no raw workflow input;
- no execution;
- no RAG;
- no embeddings;
- no FTS;
- no production n8n access;
- no LLM write access;
- no promotion to `VORQUEL_VALIDATED`;
- no implementation authorization.

## Next gate

After unit/integration CI is green, perform a tiny controlled live ingestion and verify database rows contain only compiled/sanitized material.


## Database-enforced least privilege

Migration `20260918_002_n8n_brain_writer_role_v01.sql` creates the NOLOGIN role `n8n_brain_writer`.

The role:

- does not bypass RLS;
- has schema `USAGE` only;
- has `SELECT` + `INSERT` on the three V0.1 tables;
- has no `UPDATE`, `DELETE`, or `TRUNCATE` privilege;
- is covered by explicit RLS policies for SELECT and INSERT only.

Every writer transaction executes `SET LOCAL ROLE n8n_brain_writer` before accessing data. Therefore an admin-capable DSN is reduced to the writer capability set for the duration of the transaction, and a DSN that cannot assume the role fails closed.
