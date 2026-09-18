# n8n Controlled Ingestion V0.1

Primeiro caminho end-to-end controlado do n8n Brain:

```text
RAW_UNTRUSTED workflow
      ↓
Static Analyzer
      ↓
Knowledge Compiler
      ↓
explicit manifest
      ↓
Knowledge Writer
      ↓
private PostgreSQL schema
```

## Regra central

Descoberta e persistência são separadas.

O planner pode **descobrir**, mas não grava no banco. Ele gera um manifest explícito, pequeno e revisável.

O ingestidor aceita somente os paths do manifest. Sem `--persist`, ele opera em dry-run. Com `--persist`, a conexão vem somente de `N8N_BRAIN_DATABASE_URL`.

## Perfil CONTROLLED_STRUCTURE_V0_1

Um workflow só entra no primeiro lote se, após Analyzer + Compiler:

- `SAFE_FOR_LEARNING`;
- `REFERENCE_PATTERN` ou `STRUCTURE_REFERENCE_RESTRICTED`;
- findings ausentes ou exclusivamente `NETWORK_REQUEST` MEDIUM;
- zero `UNTRUSTED_TEXT`;
- zero executable metadata;
- zero credential types;
- `node_count > 0`;
- no máximo 4 itens por manifest.

Isso é um gate inicial conservador, não uma declaração de segurança para produção.

## Segurança

- symlinks rejeitados;
- paths não podem escapar do corpus root;
- máximo 5 MiB por workflow;
- repo/commit/SHA-256 explícitos;
- nenhum workflow, código, expression, shell, SSH ou HTTP é executado;
- Writer continua reduzindo privilégios com `SET LOCAL ROLE n8n_brain_writer`;
- persistência é append-only e idempotente;
- nenhum diretório inteiro pode ser persistido sem manifest.

## CLI

Planejar:

```bash
vorquel-n8n-plan-ingestion ./workflows \
  --source-repo JustInCache/n8n-workflows \
  --source-commit 5a7864987c22930521382b597873b713cc830dac \
  --analyzer-version 0.1.0 \
  --output manifest.json
```

Validar sem banco:

```bash
vorquel-n8n-ingest-manifest ./workflows manifest.json
```

Persistir explicitamente:

```bash
N8N_BRAIN_DATABASE_URL=... \
vorquel-n8n-ingest-manifest ./workflows manifest.json --persist
```


## Evidência que alterou o perfil inicial

A primeira tentativa exigia zero security findings e apenas `REFERENCE_PATTERN`. No snapshot real pinado, o planner encontrou **0 candidatos**. Esse resultado invalidou a hipótese operacional de que haveria quatro workflows reais úteis sem nenhum finding.

A V0.1 foi então ajustada de forma conservadora: também aceita `STRUCTURE_REFERENCE_RESTRICTED` quando os únicos findings são `NETWORK_REQUEST` de severidade MEDIUM. Isso permite aprender apenas topologia/metadados de chamadas HTTP; não executa a chamada, não persiste credenciais, texto não confiável ou conteúdo executável e não promove o item a implementação autorizada.
