# BRAIN CONTRACT V1 — reconciliation

Decided 2026-09-22, after PR #24 (PR2 BUILD + SAFE TEST) merged as `97331e2`.

Four divergences were found between the sources of authority for Brain V1. This
file records each one as it actually happened: what the earlier contract said,
what disagreed with it, what was decided, and what the decision costs. It is not
a restatement of the contract as though it had always read this way. The earlier
text was wrong on four points and this is the record of it being corrected.

## Sources, and what each one could actually be checked against

| Source | Status when this was decided |
|---|---|
| Issue #22 | read in full from GitHub — **verifiable** |
| Live SQL (`supabase/migrations/20260920_004…`) | read from the repo — **verifiable** |
| `BRAIN CONTRACT V1 — 2026-09-21` | **not in the repo**, Drive-only — quoted by the operator, *not* independently verified |
| `00 — ESTADO ATUAL — 2026-09-21` | **not in the repo**, Drive-only — same |

DIV-1 rests on the operator's quotation of a document this repository cannot
see. That is recorded here as a limitation of the evidence, not smoothed over.
Landing the contract in-repo would make it verifiable authority instead of an
external claim.

---

## DIV-1 — `get_entity`

**Previous contract.** `BRAIN CONTRACT V1` listed seven minimal interfaces:
`resolve_entity`, `get_state`, `get_delta`, `search_evidence`,
`get_context_pack`, `record_candidate`, `record_event`.

**Divergence.** Issue #22 — the implementation contract — lists **eight**:
six reads including `get_entity`, plus two controlled writes. `00 — ESTADO
ATUAL` also says 6 reads + 2 writes. The seven-interface list was the outlier.

**Decision — APPROVED: keep `get_entity`. The contract is 8 tools.**

| # | Tool | Kind |
|---|---|---|
| 1 | `resolve_entity` | read |
| 2 | `get_entity` | read |
| 3 | `get_state` | read |
| 4 | `get_delta` | read |
| 5 | `get_context_pack` | read |
| 6 | `search_evidence` | read |
| 7 | `record_candidate` | controlled write |
| 8 | `record_event` | controlled write |

**Rationale.** The three reads answer three different questions and collapsing
them is an epistemic error, not merely an ergonomic one.

- `resolve_entity` answers *which entity is this string* — a pointer plus ranked
  candidates. Making it return full records would force full records **for every
  candidate**, which is a scope-leak surface: an entity the caller is not
  entitled to would expose its attributes merely by being a near-match.
- `get_state` returns a `STATE_PROJECTION`, which is a **read model** —
  recomputable and staleness-bearing. Canonical entity identity is much closer
  to source of truth. Routing canonical attributes through a derived, staleable
  channel contradicts the project's own rule that state and ContextPack are not
  sources of truth.
- `RELATION` is in the V1 ontology. Without `get_entity` there is **no non-pack
  way to read an entity's relations at all**.
- `get_context_pack` is mode-dependent and token-budget-trimmed, so it may
  legitimately omit an attribute. It is a lossy answer to an exact question.

**Compatibility.** Additive relative to the seven-interface list; nothing is
removed or renamed. Adding a tool later would have been a minor version bump,
but shipping V1 without it would have pushed consumers onto a
`get_context_pack` workaround that then becomes the de-facto contract.

**Follow-up.** `BRAIN CONTRACT V1` is to be amended from 7 to 8 interfaces
**without deleting its prior text** — the seven-interface version stays as
superseded history, consistent with the append-only journal rule this project
already applies to `PR2_BUILD_EVIDENCE.md`.

---

## DIV-2 — sensitivity and PII

**Previous contract.** Issue #22 listed sensitivity as `PUBLIC`, `INTERNAL`,
`CLIENT_CONFIDENTIAL`, `PII`, `SECRET`.

**Divergence.** The operational instruction listed `PUBLIC`, `INTERNAL`,
`CONFIDENTIAL`, `CLIENT_CONFIDENTIAL`, `SECRET` — dropping `PII` and adding
`CONFIDENTIAL`. Both are load-bearing: `SECRET` gates ContextPack admission and
`PII` gates LGPD handling.

The deeper problem is that `PII` is not a confidentiality *tier* at all, it is a
data *category*. On one axis it makes "public-facing material that contains
personal data" unrepresentable, and forces a false choice between labelling a
client document `CLIENT_CONFIDENTIAL` or `PII`.

**Decision — APPROVED: two orthogonal axes.**

```
sensitivity_level  (exactly one)
  PUBLIC | INTERNAL | CONFIDENTIAL | CLIENT_CONFIDENTIAL | SECRET

data_classes       (set, extensible, empty by default)
  V1 must support at least: PII
```

Rules, as decided:

- `SECRET` **never** enters a ContextPack.
- `PII` must respect scope, minimisation and redaction.
- `PII` is **never** auto-promoted to `SECRET`.
- `CLIENT_CONFIDENTIAL` is **not** weakened or strengthened by whether the item
  carries `PII`. The two axes do not interact.

**Compatibility.** `sensitivity` is effectively unimplemented in the live schema
today — a grep of the migrations finds no sensitivity column or constraint — so
this is greenfield and conflicts with nothing. `data_classes` is defined as a
set precisely so later categories can be added without a breaking change.

---

## DIV-3 — scope

**Previous contract.** Issue #22 asked for `GLOBAL_VORQUEL`, `VERTICAL`,
`COMPANY/ENTITY`, `CLIENT`, `PROJECT`, `PRIVATE_TEST`, with `COMPANY/ENTITY`
written ambiguously — one scope or two was not stated.

**Divergence.** The live database constrains scope to **four** values, on two
tables:

```sql
-- supabase/migrations/20260920_004_n8n_brain_experience_and_runs_v01.sql:27,114
check (scope_type in ('GLOBAL_VORQUEL','CLIENT','PROJECT','PRIVATE_TEST'))
```

So the contract is ahead of storage by two values, and the ambiguity was never
resolved.

**Decision — APPROVED: six scopes, `COMPANY` is not one of them.**

```
GLOBAL_VORQUEL | VERTICAL | ENTITY | CLIENT | PROJECT | PRIVATE_TEST
```

A company is an `ENTITY` with `entity_type=COMPANY`. `PERSONAL` is **not** added
to Brain V1 without a concrete use case.

**Rationale.** Modelling a company as a scope rather than an entity would create
two parallel ways to name the same thing, and every retrieval path would have to
handle both.

**Compatibility — and this is the load-bearing part.**

Brain-V1-A **defines and tests the schema only. It performs no migration.** The
existing four-value constraints on `operational_experiences` and `build_runs`
stay exactly as they are. Nothing in the live database is altered by
Brain-V1-A, so there is a deliberate, recorded gap between the contract schema
(6 scopes) and storage (4 scopes) for the duration of that PR.

The migration adding `VERTICAL` and `ENTITY` to storage is **deferred to
Brain-V1-B**, where it will be planned and tested with backward compatibility.
Until then, no code may assume storage accepts `VERTICAL` or `ENTITY`.

---

## DIV-4 — epistemic status spelling

**Previous contract.** Written as `HIPÓTESE`, accented, in both Issue #22 and
the operational instruction.

**Divergence.** The live constraint uses the unaccented ASCII form:

```sql
-- supabase/migrations/20260920_004_n8n_brain_experience_and_runs_v01.sql:61
check (epistemic_status in (
  'OBSERVADO','DECLARADO','MEDIDO','INFERIDO','HIPOTESE',
  'ESTIMADO','DESCONHECIDO','CONFLITANTE','INVALIDADO'))
```

Schemas written against the accented spelling would fail validation against rows
that already exist, and would do so quietly.

**Decision — APPROVED: split storage value from display value.**

| Layer | Value |
|---|---|
| storage / API / machine-readable | `HIPOTESE` |
| human display | `HIPÓTESE` |

**Compatibility.** Existing rows are **not** migrated merely to add an accent.
The nine values are otherwise unchanged. `verification_state` — `UNREVIEWED`,
`REVIEWED`, `APPROVED`, `REJECTED`, `SUPERSEDED` — does not appear anywhere in
the codebase today and is greenfield; it stays a separate axis and is never
merged into `epistemic_status`.

---

## What Brain-V1-A is allowed to be

Schema-only and validation-only. It must not contain a live migration, new
storage, an MCP server, Oracle deployment, GBrain, a vector database, or a
complete retrieval engine.
