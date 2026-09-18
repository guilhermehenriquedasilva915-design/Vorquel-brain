# n8n Knowledge Compiler — Architecture V0.1

## Purpose

Transform a workflow that has already passed static analysis into a deterministic knowledge representation without granting authority to retrieved content.

```text
RAW_UNTRUSTED workflow JSON
          +
STATIC_ANALYZED report
          |
          v
Knowledge Compiler
          |
          +--> provenance
          +--> topology (nodes + edges)
          +--> node/resource/operation metadata
          +--> integration + trigger inventory
          +--> UNTRUSTED_TEXT
          +--> EXECUTABLE_SNIPPET_UNTRUSTED metadata
          +--> security findings without raw evidence
          |
          v
N8N_KNOWLEDGE_ITEM
```

## Non-negotiable boundaries

The compiler never executes source content.

Credential values, IDs and names are omitted. Only credential **types** may be retained.

Executable material is not persisted as executable content in V0.1. Code, expressions, shell and SSH commands are represented by SHA-256, length, origin path and type.

Natural-language content remains explicitly tagged `UNTRUSTED_TEXT`; it is not a system prompt and cannot authorize tools.

## Admission policy

| Input state | Knowledge role | Default scope |
| --- | --- | --- |
| INFO/LOW + SAFE_FOR_LEARNING | REFERENCE_PATTERN | structure + metadata |
| MEDIUM + SAFE_FOR_LEARNING | STRUCTURE_REFERENCE_RESTRICTED | structure only |
| HIGH / REVIEW_REQUIRED | QUARANTINED_REFERENCE | review only |
| CRITICAL / BLOCKED | SECURITY_EXAMPLE | security only |

No role is `VORQUEL_VALIDATED` in V0.1.

## Why this is separate from RAG

Compilation is a deterministic security and data-model boundary. Retrieval/embeddings come later. This prevents “put the repository in a vector database” from silently turning third-party instructions, code or secrets into trusted context.

## Evals

The first package includes unit tests and a 25-case synthetic admission-policy eval pack. This does not replace later human/real-corpus evaluation before enabling RAG or builder actions.
