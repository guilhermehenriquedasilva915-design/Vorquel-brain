# EVOLVE — transformar resultado real em memoria

```
execucao → operational experience → knowledge candidate (ERROR/FIX/PATTERN)
        → revisao humana → knowledge ativo → retrieval futuro
```

## 1. Registre a experiencia

Em `n8n_brain.operational_experiences`, append-only:

`experience_id` · `scope` · `environment` · `workflow_id` · `workflow_hash` ·
`node` · `category` · `observed_error` · `sanitized_context` · `hypothesis` ·
`change_summary` · `result_before` · `result_after` · `execution_ids` ·
`n8n_version` · `epistemic_status`

Nao persista payload cru, PII desnecessaria nem segredo. O banco recusa chaves
como `secret`, `token`, `password` dentro de `sanitized_context` — se bateu na
restricao, o recorte estava errado, nao a restricao.

## 2. Separe resultado de explicacao

Isto e o ponto inteiro deste procedimento:

- **resultado** pode ser `MEDIDO` — nos rodamos, nos vimos;
- **explicacao causal** normalmente continua `INFERIDO` — nos achamos que foi
  por isso.

Registrar os dois como `MEDIDO` e como uma correcao pontual vira regra falsa que
o Brain repete com confianca pelos proximos seis meses.

## 3. Gere o candidato

Uma experiencia util vira candidato:

- `ERROR` — o que quebra, em que condicao;
- `FIX` — o que resolveu, com o contexto em que resolveu;
- `PATTERN` — so quando ja se repetiu.

Inclua o envelope de compatibilidade: `observed_n8n_version`, `node_type`,
`node_version`, `observed_at`. Conhecimento de n8n sem versao e conhecimento com
prazo de validade desconhecido.

Escopo: o mesmo da tarefa. Conhecimento de cliente nasce `CLIENT:x`.

## 4. Promocao a padrao

`PATTERN` exige: repeticao, contexto compativel, ausencia de evidencia forte em
contrario, e revisao humana. Uma ocorrencia e uma ocorrencia.

## 5. Promocao para GLOBAL_VORQUEL

So manualmente, e so com:

- remocao ou minimizacao do que e especifico do cliente;
- proveniencia preservada;
- intencao humana explicita.

Nao ha caminho automatico de `CLIENT:x` para `GLOBAL_VORQUEL`.

## 6. Invalidar o que ficou errado

Se algo que guardamos se provou falso, nao apague: use `supersede` (com o
substituto) ou `withdraw` (com o motivo). O historico de por que acreditamos em
algo errado e parte do que impede repetir.

## 7. Feche o run

Atualize `build_runs` para `PASSED` e registre o release bundle quando o
workflow chegar a `DEV_VERIFIED`. Producao continua manual.
