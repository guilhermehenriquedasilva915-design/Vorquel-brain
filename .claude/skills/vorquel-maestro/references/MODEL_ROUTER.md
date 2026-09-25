# MODEL ROUTER — Vorquel Maestro

## Objetivo
Escolher o executor mais barato que mantenha confiabilidade suficiente.
Modelo forte é recurso escasso, não default.

## Classes

### D0 — sem LLM
Use shell/API/código determinístico.

Exemplos:
- git status, diff, log, branch, SHA;
- listar arquivos/migrations;
- grep/find;
- pytest, ruff, typecheck;
- checar CI;
- comparar JSON/schema/hash;
- SQL read-only já conhecido;
- parse de logs por regra.

### D1 — modelo barato/rápido
Use para:
- resumir output;
- triagem de arquivos;
- checklist;
- handoff;
- classificação simples;
- documentação mecânica.

Preferência: Haiku ou equivalente econômico disponível.

### D2 — modelo intermediário
Use para:
- implementação comum;
- testes;
- refactor;
- migration sob especificação aprovada;
- adapter sob contrato definido;
- debugging normal;
- review de código não load-bearing.

Preferência: Sonnet ou equivalente intermediário.

### D3 — modelo forte
Use para:
- arquitetura;
- reconciliação de ontologia;
- conflito entre fontes canônicas;
- persistência load-bearing;
- segurança;
- isolamento multi-tenant;
- migrations sensíveis;
- review final de mudança crítica;
- bug difícil após falhas D1/D2.

Preferência: Opus/Codex forte conforme aptidão da tarefa.

### D4 — humano
Não delegar decisão final:
- merge;
- produção;
- migration live destrutiva;
- mudança de contrato;
- mudança de source-of-truth;
- segredo;
- decisão irreversível.

## Regras de escalada
1. D0 primeiro quando possível.
2. D1 antes de D2 quando a tarefa for apenas leitura/síntese.
3. D2 antes de D3 para implementação normal.
4. D3 só com justificativa explícita.
5. D4 sempre para humanos.

## Anti-waste
Nunca usar modelo forte só para:
- descobrir branch;
- verificar HEAD;
- abrir arquivo;
- executar teste;
- ler exit code;
- formatar lista;
- conferir CI;
- copiar dados entre formatos.

## Review independente
Builder e reviewer não devem ser o mesmo contexto quando a mudança for D3.
Para PR crítico:
- builder: D2/D3 conforme necessário;
- reviewer: executor independente;
- merge: humano.
