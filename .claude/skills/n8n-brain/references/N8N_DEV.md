# N8N_DEV — fronteira de execucao

> **Estado V1:** nenhuma instancia n8n esta registrada e nenhum MCP n8n esta
> configurado. Enquanto `vorquel-brain-doctor` mostrar `n8n.instance` e
> `n8n.mcp` como `BLOCKED`, BUILD e DEBUG nao rodam. Este arquivo descreve a
> fronteira que precisa existir **antes** deles rodarem.

## Preferencia

Instancia n8n **DEV separada** da producao.

Fallback aceitavel, se DEV separada nao for viavel:

- principal/usuario MCP dedicado;
- projeto DEV dedicado;
- zero credencial de producao visivel para esse principal;
- somente credenciais de teste;
- tools de producao negadas.

Se o principal do MCP enxerga credenciais globais reais, **nao** permita criacao
de workflow com auto-atribuicao de credencial ate isso ser resolvido. O risco
nao e o workflow — e o workflow herdando uma credencial de producao sem
ninguem notar.

## N8N_ENVIRONMENT_PROFILE

Antes de construir, colete e registre:

`instance_id` · `environment` · `n8n_version` · matriz de capacidades do MCP ·
projeto DEV · principal/usuario · node types · versoes de node ·
community/custom nodes · capacidades de workflow · **aliases** e tipos de
credencial · `checked_at`.

Nunca colete nem retorne: key, token, password, segredo de OAuth, payload de
credencial. Alias e tipo bastam para decidir; o valor nunca e necessario para
construir.

Se `environment != DEV`: **mutacoes bloqueadas**. Se o ambiente nao estiver
declarado, trate como nao-DEV.

## MCP oficial primeiro

Antes de escrever wrapper proprio, confira a documentacao oficial atual do n8n e
use o MCP oficial para: referencia de SDK, busca de node, node types, validacao
de workflow, criacao/atualizacao, execucoes, teste com pin data, metadados de
credencial, historico/diff.

Wrapper proprio **so** com gap concreto identificado. Nao recrie um builder MCP
inteiro.

## Permissoes reais de tool

Nao confie so em prompt. Configure allowlist/denylist de tools MCP em
`.claude/settings.json`.

**READ_PROFILE** — leitura, capabilities, schemas, busca de workflow, leitura de
execucao, referencia de node/docs.

**BUILD_DEV_PROFILE** — create/update/test **apenas em DEV**.

**Negado na V1** — publish · execucao em producao · delete · operacao destrutiva
de dados · gestao de credencial de producao · deploy · mutacao de canal ao vivo ·
instalacao de community node · qualquer equivalente de producao.

## Estrategia de teste seguro

| Nivel | O que roda |
|---|---|
| 0 — PURE | validacao deterministica + Analyzer. Sem execucao. |
| 1 — PINNED | pin data, inspecao de skipped nodes, Safe Test Gate, test workflow |
| 2 — SANDBOX | credenciais de teste, endpoints sandbox |
| 3 — REAL | so com aprovacao humana explicita |
| PRODUCAO | fora da autonomia V1 |

**`test_workflow` nao e sandbox total.** Um node sem credencial que faz I/O
executa de verdade. Por isso o Analyzer e a revisao de skipped nodes sao
obrigatorios no nivel 1 — o "teste" e onde um Execute Command passa
despercebido.
