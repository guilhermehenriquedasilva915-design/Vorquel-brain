# n8n Knowledge Writer

Append-only persistence boundary for `N8N_KNOWLEDGE_ITEM` V0.1.

The writer accepts only the **compiled knowledge representation**. It does not accept or execute raw n8n workflows.

## Trust boundary

The writer:

- validates the compiler contract again before touching the database;
- rejects trusted/validated/implementation-authorized states in V0.1;
- rejects raw `evidence` in findings;
- rejects raw `content`, `code`, or `command` inside executable metadata;
- never evaluates expressions, JavaScript, shell, SSH, URLs, or node parameters;
- writes with `SELECT` + `INSERT` only;
- treats version conflicts as immutable-data drift instead of updating rows;
- reads the database connection only from `N8N_BRAIN_DATABASE_URL`.

## Dry run

```bash
vorquel-n8n-write knowledge-item.json \
  --analyzer-version 0.1 \
  --dry-run
```

## Persist

```bash
export N8N_BRAIN_DATABASE_URL='postgresql://...'
vorquel-n8n-write knowledge-item.json --analyzer-version 0.1
```

The CLI never prints the database URL.

Use a minimally privileged backend database role in deployed environments. The application code itself issues no UPDATE or DELETE statements.


## Database privilege drop

Every write transaction begins with:

```sql
SET LOCAL ROLE n8n_brain_writer;
```

The database role is `NOLOGIN`, does not bypass RLS, and has only `USAGE` on the private schema plus `SELECT` and `INSERT` on the V0.1 tables.

The DSN role must therefore be allowed to assume `n8n_brain_writer`. If it cannot, the write fails closed before any source row is inserted.
