# ASK — pesquisar e responder com proveniencia

## 1. Monte o pack

```bash
vorquel-brain-retrieve "<pergunta>" --task-type ASK --scope <escopo>
```

Escopo default e `GLOBAL_VORQUEL`. Se a pergunta e sobre um cliente, passe
`CLIENT:x` — o retrieval devolve o cliente **mais** o global, e nunca outro
cliente.

Use `--json` quando precisar processar; use a saida de texto para ler.

## 2. Responda a partir do pack

Cada afirmacao tecnica carrega uma citacao: `source_id` + locator.

> O retry padrao do HTTP Request e 3 tentativas
> (`src_yt_7 [MEDIA_TIME start_ms=902000]`, **DECLARADO**, n8n 1.40.0).

Marque o status epistemico junto. A diferenca entre "medimos" e "um tutorial
disse" e a diferenca entre a resposta ser util e ser perigosa.

## 3. Respeite a prioridade

Se duas fontes discordam, a de menor rank de autoridade vence — mas **as duas
aparecem**:

> Nossa execucao medida em 1.62.0 mostra X (`exp_...`, **MEDIDO**).
> O tutorial `src_yt_7` afirma Y (**DECLARADO**, observado em 1.40.0).
> Divergencia provavelmente de versao; usando X.

Nunca apresente so o lado vencedor.

## 4. Versao e compatibilidade

Se o item tiver `compatibility_status` `STALE`, `DEPRECATED` ou
`UNKNOWN_COMPATIBILITY`, diga isso. Conhecimento de n8n envelhece com o node,
nao com o calendario.

## 5. Quando o pack vem vazio

Diga que nao ha memoria sobre o assunto. Voce pode responder pelo seu proprio
conhecimento, mas rotule: **inferencia sua, autoridade 9**, e ofereca rodar
LEARN sobre uma fonte confiavel.

Nao transforme inferencia em citacao. Nunca invente um `source_id`.

## 6. Gaps

O pack lista `gaps` e `degraded`. Repasse os que mudam a confianca da resposta —
especialmente "colunas de scope ausentes" e "nenhuma instancia n8n registrada".
Uma resposta confiante sobre um Brain degradado e pior que nenhuma resposta.
