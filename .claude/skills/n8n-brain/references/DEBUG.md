# DEBUG — diagnosticar, corrigir, retestar

> Depende de instancia n8n DEV + MCP n8n. Sem eles, `vorquel-brain-doctor`
> retorna `BLOCKED` e este procedimento nao roda. Nao invente diagnostico sobre
> uma execucao que voce nao leu.

## Loop

```
FAIL → observe → classifique → sanitize → busque experiencias
     → hipoteses → menor teste discriminante → patch → rerun
     → compare → assert → aprenda
```

## 1. Observe antes de opinar

Leia a execucao real: node que falhou, mensagem, input e output do node
anterior, versao do node. Nao adivinhe a partir do nome do erro.

## 2. Classifique

`WORKFLOW_LOGIC` · `EXPRESSION` · `MAPPING` · `NODE_CONFIGURATION` ·
`NODE_VERSION` · `CREDENTIAL` · `AUTH_OAUTH` · `EXTERNAL_API` · `RATE_LIMIT` ·
`DATA_SHAPE` · `DATABASE_SCHEMA` · `ENVIRONMENT` · `TRANSIENT` · `UNKNOWN`

`UNKNOWN` e uma resposta legitima. Uma categoria errada manda a busca de
experiencias para o lado errado.

## 3. Sanitize

Antes de guardar ou exibir: remova segredo, token, header de autorizacao, e-mail
e telefone de pessoa real. Guarde a **estrutura** do erro, nao o dado do
cliente.

## 4. Busque o que ja sabemos

```bash
vorquel-brain-retrieve "<erro sanitizado>" --task-type DEBUG --scope <escopo>
```

Experiencias `MEDIDO` no mesmo ambiente sao autoridade 2. Se ja resolvemos isso,
reuse — e diga que esta reusando, citando o `experience_id`.

## 5. Hipoteses e o menor teste

Liste hipoteses concorrentes. Escolha o teste que **distingue** entre elas com o
menor efeito colateral. Nao mude tres coisas de uma vez: se funcionar, voce nao
sabe qual delas resolveu, e a experiencia registrada fica inutil.

## 6. Orcamento

**Maximo 4 tentativas automaticas por ciclo.** O limite e do banco
(`build_runs.attempts`), nao da sua memoria da conversa.

Ao estourar, pare e entregue:

- fatos observados;
- erro sanitizado;
- hipoteses consideradas;
- cada tentativa e seu resultado;
- melhor explicacao atual;
- o que falta saber;
- **a proxima acao humana, concreta**.

Parar com um relatorio honesto e um resultado. Uma quinta tentativa as cegas
nao e.

## 7. O que voce pode corrigir sozinho (em DEV)

mapping · expressao · conexao de node · parametro seguro · transformacao de
dados · config estrutural · caminho de campo.

## 8. O que exige humano

segredo · credencial · OAuth · pagamento · producao · mensagem a cliente ·
delete · mudanca destrutiva de banco · instalacao de community node · infra ·
permissao · qualquer acao irreversivel.

## 9. Quando esta resolvido

So quando as tres coisas valem:

1. o erro original nao acontece mais;
2. o resultado esperado acontece;
3. as regressoes relevantes passam.

"O erro sumiu" sozinho nao e correcao — pode ser o workflow parando antes.

## 10. Depois

Registre a experiencia (`EVOLVE.md`). Resultado pode ser `MEDIDO`; a explicacao
causal provavelmente continua `INFERIDO`. Nao promova uma correcao unica a regra
universal.
