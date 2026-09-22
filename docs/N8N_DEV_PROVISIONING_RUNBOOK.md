# Runbook: provisionar o ambiente n8n DEV

Pré-requisito para PR 2 (BUILD + SAFE TEST) e PR 3 (DEBUG + EVOLVE). Enquanto
este runbook não for executado, `vorquel-brain-doctor` retorna `BLOCKED` e a
Skill recusa BUILD e DEBUG por desenho.

Estado em 2026-09-20: nenhuma instância n8n provisionada, nenhum MCP n8n
configurado, portas 5678/5679 fechadas, Docker parado.

---

## Passo 1 — Subir um n8n DEV isolado

A preferência é uma instância **separada** da produção. Como ainda não há
produção, "separada" significa: uma instância que nunca receberá credencial de
cliente real.

```bash
docker run -d --name n8n-dev \
  -p 5678:5678 \
  -e N8N_ENCRYPTION_KEY="<gere uma chave e guarde fora do repo>" \
  -e GENERIC_TIMEZONE="America/Sao_Paulo" \
  -e N8N_DIAGNOSTICS_ENABLED=false \
  -v n8n_dev_data:/home/node/.n8n \
  docker.n8n.io/n8nio/n8n
```

**Validar:** `curl -sS http://localhost:5678/healthz` responde. Abra
`http://localhost:5678` e crie o owner.

A chave de encriptação não entra em nenhum repositório, em nenhum knowledge item
e em nenhuma experiência. Ela é `SECRET` pela política em `DATA_POLICY.md`.

---

## Passo 2 — Criar o principal dedicado

Não use o owner para o MCP. Crie um usuário/API key próprio para o agente, e um
projeto DEV dedicado.

1. Settings → n8n API → criar API key rotulada `vorquel-brain-dev`.
2. Criar um projeto chamado `DEV`.
3. Não conceder a esse principal acesso a nenhuma credencial fora do projeto DEV.

**Validar — este é o teste que importa:**

```bash
curl -sS -H "X-N8N-API-KEY: $N8N_API_KEY" \
  http://localhost:5678/api/v1/credentials | head -c 400
```

Se esse comando listar credenciais fora do projeto DEV, **pare**. Conforme
`N8N_DEV.md`, criação de workflow com auto-atribuição de credencial fica
proibida até isso ser resolvido — o risco não é o workflow, é o workflow
herdando uma credencial que ninguém revisou.

---

## Passo 3 — Declarar o ambiente

```bash
export N8N_BASE_URL="http://localhost:5678"
export N8N_ENVIRONMENT="DEV"
export N8N_API_KEY="<a key do passo 2>"
```

No Windows/PowerShell use `$env:N8N_BASE_URL = "..."`.

Se `N8N_ENVIRONMENT` não estiver declarado, o doctor assume **não-DEV** e bloqueia
mutação. Isso é intencional: o default seguro é recusar.

**Validar:** `vorquel-brain-doctor` deve mover `n8n.instance` e
`n8n.environment` para `ok`.

---

## Passo 4 — Configurar o MCP n8n

Antes de escolher, confira a documentação oficial atual do n8n e use o MCP
oficial se existir. Wrapper próprio só com gap concreto — não recrie um builder
MCP inteiro.

Ao adicionar o servidor, registre o nome real dele. **As regras
`mcp__n8n__*` em `.claude/settings.json` foram escritas antes de qualquer MCP
existir e os nomes de tool são placeholders não verificados.** O doctor reporta
isso como `n8n.deny_rules` → `warn`. Uma denylist que não casa com nenhum nome
real dá falsa segurança, o que é pior que não ter denylist.

**Validar:** liste as tools expostas pelo MCP e confirme, uma a uma, que cada
tool destrutiva aparece no `deny` com o nome correto:

- publish / activate
- execução em produção
- delete (workflow, execução, credencial)
- criação e alteração de credencial
- instalação de community node
- deploy

---

## Passo 5 — Registrar o N8N_ENVIRONMENT_PROFILE

Coletar e persistir: `instance_id`, `environment`, `n8n_version`, matriz de
capacidades do MCP, projeto DEV, principal, node types, versões de node,
community/custom nodes, aliases e tipos de credencial, `checked_at`.

Nunca coletar nem retornar: key, token, password, segredo de OAuth, payload de
credencial. Alias e tipo bastam para decidir o que construir.

---

## Passo 6 — Runtime de IA (só se necessário)

Se algum workflow precisar de LLM **em execução**, registre no
RUNTIME_CAPABILITY_REGISTRY: provider, model, alias de credencial, ambiente,
classe de custo, `approved`, `available`.

Sem runtime de IA aprovado, a resposta correta é solução determinística ou
**PARAR** e informar o requisito. Nunca adicionar provider pago em silêncio.

---

## Critério de pronto

`vorquel-brain-doctor` retorna `READY` ou `READY_WITH_LIMITS`, com:

| Check | Estado esperado |
|---|---|
| `n8n.instance` | ok |
| `n8n.environment` | ok (DEV) |
| `n8n.mcp` | ok |
| `n8n.deny_rules` | ok, depois dos nomes confirmados no passo 4 |
| `safety.scope_isolation` | ok, depois das migrations 0021/0022 |
| `safety.run_journal` | ok, depois da migration 20260920_004 |

Só então PR 2 sai do papel.
