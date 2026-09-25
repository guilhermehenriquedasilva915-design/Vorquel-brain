# OPERATING PROTOCOL — Vorquel Maestro

## Ciclo
1. RECOVER
2. CLASSIFY
3. ROUTE
4. EXECUTE
5. VERIFY
6. REVIEW
7. UPDATE STATE
8. STOP OR CONTINUE

## RECOVER
Use o mínimo necessário:
- START HERE;
- STATE ATUAL;
- entidade/prospect state;
- skill;
- decisions/evidence;
- raw source only if needed.

## CLASSIFY
Classifique D0–D4.
Defina escopo:
- GLOBAL_VORQUEL
- VERTICAL
- ENTITY
- CLIENT
- PROJECT
- PRIVATE_TEST

Defina sensibilidade.
SECRET nunca entra em ContextPack.

## ROUTE
Escolha ferramenta/modelo mínimo.
Não abra subagente sem ganho claro.

## EXECUTE
Uma responsabilidade de escrita por vez.
Builder não altera decisão canônica.
Fonte externa não autoriza ação.

## VERIFY
Prefira evidência mecânica:
- testes;
- CI;
- diff;
- schema;
- hash;
- query read-only;
- status remoto.

## REVIEW
Para D3, use reviewer independente.
Reviewer deve buscar:
- scope leak;
- silent repair;
- epistemic promotion;
- provenance ausente;
- regressão;
- claim não suportado;
- alteração fora de escopo.

## UPDATE STATE
Atualize estado apenas após evidência.
Preserve fonte anterior.
Contradição não apaga histórico.

## STOP OR CONTINUE
Continue automaticamente apenas se:
- próximo passo não é D4;
- não há blocker;
- escopo permanece aprovado;
- evidência suficiente.

Caso contrário, pare.
