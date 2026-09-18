# n8n Brain — Knowledge Store V0.1

## Estado

Arquitetura de persistência proposta/implementada como migration versionada. O banco vivo só deve receber a migration depois do CI e revisão do PR.

## Banco

A V0.1 reutiliza o PostgreSQL/Supabase do ecossistema Vorquel Watch, mas usa o schema privado `n8n_brain`.

Não há RAG, embeddings, pgvector, API pública ou execução de workflows nesta fase.

## Tabelas

`source_snapshots` preserva provenance imutável por repo/commit/path/SHA-256.

`workflow_analyses` preserva a decisão do Static Analyzer e findings sanitizados.

`knowledge_items` persiste a representação compilada sem workflow bruto, sem credenciais e sem conteúdo executável.

## Segurança

- schema sem acesso para `public`, `anon` e `authenticated`;
- `service_role` recebe apenas `SELECT` e `INSERT`;
- RLS habilitado nas três tabelas;
- nenhum policy de cliente é criado;
- `implementation_reference_allowed=true` é rejeitado por constraint;
- `vorquel_validated=true` é rejeitado por constraint nesta versão;
- `evidence` bruta é rejeitada nos findings;
- campos `content`, `code` e `command` são rejeitados em executable metadata;
- provenance e versões possuem constraints e chaves de idempotência.

## Reversibilidade

O schema dedicado permite exportar/mover `n8n_brain` para outro projeto PostgreSQL no futuro sem misturar as tabelas com o domínio Watch.

## Próximo gate

Após migration testada e aplicada: implementar um writer estreito que aceite somente o schema do `N8N_KNOWLEDGE_ITEM`, valide hash/provenance e faça inserts idempotentes. Retrieval/FTS/RAG continua fora do escopo.
