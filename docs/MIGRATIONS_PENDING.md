# Migrations aguardando aplicacao live

Nenhuma das migrations abaixo foi aplicada ao projeto Supabase gerenciado.
Todas passam primeiro por Git -> CI -> PostgreSQL descartavel. A aplicacao live
e um **gate humano**: precisa de autorizacao explicita do operador.

Projeto de destino quando autorizado: **vorquel-content-brain**
(`xnygwzuckijaxzlszfpn`).

| Migration | Repositorio | Schema | Validada em CI | Aplicada live |
|---|---|---|---|---|
| `0021_knowledge_scope_and_generic_provenance.sql` | Vorquel-watch | `vorquel_knowledge`, `public` | job `knowledge-migrations` | **NAO** |
| `0022_scoped_knowledge_retrieval.sql` | Vorquel-watch | `public` | job `knowledge-migrations` | **NAO** |
| `0023_external_sources_and_scoped_candidates.sql` | Vorquel-watch | `vorquel_knowledge`, `public` | job `knowledge-migrations` | **NAO** |
| `20260920_004_n8n_brain_experience_and_runs_v01.sql` | Vorquel-brain | `n8n_brain` | job `n8n-knowledge-store-migration` | **NAO** |

## O que o CI prova antes de qualquer aplicacao live

- todas as migrations do Watch aplicam em ordem, do zero, num PostgreSQL
  descartavel;
- `0021`, `0022` e `0023` sao **re-aplicaveis** (rodam duas vezes sem erro), que
  e a condicao real de um projeto que ja tem linhas;
- os invariantes de isolamento, revisao, classificacao e versionamento passam
  (`supabase/tests/knowledge_scope_and_external_sources.sql`).

## Risco de aplicar live

`0021` e `0023` sao aditivas, mas tres pontos merecem atencao do operador:

1. **`0021` faz um backfill** de `knowledge_sources.locator`, reexpressando o
   locator de midia que ja esta em colunas dedicadas. Nao inventa fato novo,
   mas escreve em linhas existentes.
2. **`0023` substitui o corpo de `approve_knowledge_candidate`.** Isso e uma
   correcao: aplicar `0021` **sem** `0023` deixa a aprovacao descartando
   `locator_kind`/`locator`, ou seja, perdendo a proveniencia de toda fonte nao
   midiatica no momento em que ela vira conhecimento. As tres devem ser
   aplicadas juntas, na ordem.
3. **`0023` relaxa `NOT NULL` em `public.sources.duration_ms`** e troca os
   checks de `source_kind` e `data_trust_class`. Midia continua obrigada a
   declarar duracao (`sources_media_duration_check`).

Nenhuma delas apaga dados, remove coluna ou altera linha de knowledge aprovado.

## Autorizacao necessaria

O operador precisa dizer, explicitamente, que autoriza aplicar **0021, 0022 e
0023 no projeto vorquel-content-brain**, e se `20260920_004` vai junto.
Ate la, as migrations ficam versionadas e verdes no CI, e nada toca o projeto
gerenciado.
