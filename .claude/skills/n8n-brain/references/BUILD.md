# BUILD — projetar e construir workflow

> **Estado V1:** este procedimento depende de uma instancia n8n DEV e de um MCP
> n8n configurado. Rode `vorquel-brain-doctor` primeiro. Se `n8n.mcp` ou
> `n8n.instance` estiver `BLOCKED`, **pare** e diga o que falta — nao simule
> criacao de workflow, nao gere JSON apresentado como "criado", nao prometa
> teste.

## Loop

```
REQUEST
 → clarify (so se faltar requisito critico)
 → retrieve_n8n_context
 → N8N_ENVIRONMENT_PROFILE
 → RUNTIME_CAPABILITY_REGISTRY
 → referencia do MCP n8n oficial
 → PLAN
 → draft
 → validacao deterministica
 → validacao do n8n
 → Vorquel Analyzer
 → classificacao de efeito colateral
 → snapshot (se ja existe)
 → drift check
 → create/update em DEV
 → safe test
 → assertions
 → report
```

## 1. Contexto antes do desenho

```bash
vorquel-brain-retrieve "<objetivo>" --task-type BUILD --scope <escopo>
```

Depois confira o ambiente real: versao do n8n, node types instalados, versoes de
node, community nodes, projeto DEV, credenciais **por alias** (nunca payload).
O ambiente e autoridade 1: se ele contradiz a memoria, o ambiente vence.

## 2. Runtime de IA

Se o workflow precisa de LLM **em execucao** (um agente que responde 24/7), isso
e diferente de voce ser o builder. Consulte o RUNTIME_CAPABILITY_REGISTRY:
provider, model, alias de credencial, ambiente, classe de custo, `approved`,
`available`.

Se nao houver runtime de IA aprovado:

- prefira solucao deterministica se ela resolve; ou
- **PARE** e informe o requisito.

Nunca adicione um provider pago silenciosamente.

## 3. Validacao deterministica (antes de qualquer execucao)

- JSON valido;
- IDs de node unicos;
- conexoes coerentes;
- referencias de node existentes;
- node type instalado nesta instancia;
- versao de node compativel;
- config obrigatoria presente;
- expressoes invalidas detectaveis;
- ambiente = DEV;
- politica de node privilegiado (ver abaixo).

Sua auto-revisao e camada adicional. Ela **nao** e prova.

## 4. Nodes privilegiados

| Node | Politica |
|---|---|
| Execute Command, SSH, leitura/escrita de filesystem | **BLOQUEADO** |
| Code, community/custom node, HTTP para rede privada, operacao destrutiva | **REVIEW_REQUIRED** |
| built-in e allowlisted | permitido |

Instalacao automatica de community node: proibida. Registre package, versao e
origem quando um for usado.

## 5. Efeito colateral

Classifique **antes** de executar:

- `SAFE_TEST` — transformacao pura, mock, pin data, dado sintetico;
- `CONTROLLED_WRITE` — DB de DEV, endpoint sandbox, conta de teste;
- `HUMAN_REQUIRED` — cliente real, e-mail/WhatsApp/Instagram real, producao,
  pagamento, delete, migration destrutiva, OAuth, mudanca de credencial, deploy,
  qualquer acao externa irreversivel.

"DEV" nao significa "sem efeito real". Um HTTP Request em DEV chama a internet
de verdade.

## 6. Workflow existente

`GET` atual → hash → compare com `expected_base_hash`. Se mudou:
**STALE_WORKFLOW**, pare, nao sobrescreva. Depois: snapshot → patch parcial →
validar → testar. Se regredir, restaure o snapshot.

Registre `before_hash`, `after_hash`, resumo do patch, execucao e rollback.

## 7. Credencial auto-atribuida

Criacao/atualizacao de workflow pode auto-atribuir credencial. Sempre:

1. inspecione o resultado;
2. compare ID/projeto da credencial com a allowlist DEV;
3. se estiver fora: **PARE**, desative o draft, reporte.

Nunca confie no **nome** da credencial. Nome nao e escopo.

## 8. Test spec

Todo workflow criado ou alterado precisa de uma: fixture de entrada, saidas
esperadas, nodes esperados, efeitos colaterais **proibidos**, assertions,
cleanup. Sem test spec, o workflow nao esta pronto — esta escrito.

## 9. Journal

Mantenha `n8n_brain.build_runs` atualizado: `PLANNING` → `DRAFT` →
`VALIDATING` → `AWAITING_APPROVAL` → `TESTING` → `DEBUGGING` → `PASSED` /
`BLOCKED` / `ABORTED`.
