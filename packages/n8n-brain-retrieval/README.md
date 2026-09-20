# n8n Brain Retrieval

Camada unica de recuperacao sobre a memoria da Vorquel, e o `brain doctor`.

Nada que este pacote devolve e instrucao. Toda linha lida do banco e dado, com
`instruction_authority = NONE`, porque foi escrita a partir de uma fonte
externa.

## O que ele combina

| Store | Papel |
|---|---|
| `vorquel_knowledge` | memoria semantica revisada por humano |
| `n8n_brain.knowledge_items` | referencia estrutural de workflows analisados |
| `n8n_brain.operational_experiences` | o que medimos nas nossas proprias execucoes |
| ambiente n8n | fato atual da instancia (ainda nao disponivel) |

## Isolamento entre clientes

Um retrieval em `CLIENT:acme` devolve `CLIENT:acme` **mais** `GLOBAL_VORQUEL`, e
nada alem disso.

A regra e aplicada em tres lugares independentes:

1. no RPC `search_knowledge_items_scoped` (migration 0022);
2. no predicado da query de fallback, quando o RPC nao esta implantado;
3. numa checagem por linha (`Scope.admits`) depois de qualquer query.

A terceira existe porque as duas primeiras sao codigo que pode ter bug, e esta e
a unica regra cujo erro aparece na frente de um cliente.

**Fail-closed:** se as colunas de escopo nao existirem (migration 0021 nao
aplicada), um retrieval de cliente devolve **zero** itens e registra o motivo em
`degraded`. Ele nao cai para "devolve tudo".

## Uso

```bash
python -m pip install -e '.[dev]'
export VORQUEL_BRAIN_DATABASE_URL='postgresql://...'   # read-only

vorquel-brain-retrieve "retry do HTTP Request" --task-type ASK
vorquel-brain-retrieve "webhook dedup" --task-type BUILD --scope CLIENT:acme7f2
vorquel-brain-retrieve "timeout no Postgres" --task-type DEBUG --json
```

A conexao e aberta `read only`. Este pacote nao escreve.

## brain doctor

```bash
export VORQUEL_WATCH_ROOT='/caminho/para/Vorquel-watch'
vorquel-brain-doctor
```

Retorna `READY`, `READY_WITH_LIMITS` ou `BLOCKED`, e diz qual capacidade falta.
Ele informa se uma variavel **esta definida**, nunca o valor.

## Classes de autoridade

Prioridade operacional quando as fontes discordam (menor vence):

1. `N8N_ENVIRONMENT_FACT`
2. `MEASURED_OWN_EXECUTION`
3. `VORQUEL_VALIDATED_PATTERN`
4. `HUMAN_APPROVED_CORRECTION`
5. `OFFICIAL_DOCS`
6. `EXTERNAL_WORKFLOW_ANALYZED`
7. `TUTORIAL`
8. `COMMUNITY`
9. `MODEL_INFERENCE`

E autoridade sobre **nossas decisoes**, nao um ranking de verdade: uma execucao
medida na nossa instancia vence a documentacao oficial porque a instancia e o
que estamos prestes a mudar.

Conflitos vao para `pack.conflicts` e aparecem na resposta. Nunca sao resolvidos
em silencio.

## Por que FTS e nao embeddings

Nenhuma medicao mostrou ainda que FTS e insuficiente para este corpus. Adicionar
vector DB antes dessa evidencia e infraestrutura, nao capacidade.

## Migrations necessarias

| Migration | Repo | Sem ela |
|---|---|---|
| `0021_knowledge_scope_and_generic_provenance` | Vorquel-watch | sem isolamento entre clientes; so provenance de midia |
| `0022_scoped_knowledge_retrieval` | Vorquel-watch | retrieval usa fallback direto (funciona, mais lento) |
| `20260920_004_n8n_brain_experience_and_runs_v01` | Vorquel-brain | sem memoria operacional e sem journal de build |
