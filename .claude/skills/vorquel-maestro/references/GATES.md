# GATES — Vorquel Maestro

## Gates obrigatórios

Pare e peça aprovação humana antes de:

1. merge de PR;
2. deploy em produção;
3. migration live;
4. delete físico ou alteração irreversível;
5. mudança de source-of-truth;
6. mudança de contrato/schema canônico;
7. mudança de ontologia, incluindo RELATION;
8. promoção de padrão local para verdade global;
9. uso/revelação de secrets ou credenciais;
10. bypass de review, RLS, guard ou policy;
11. force push;
12. ação que possa cruzar escopo de cliente.

## Como reportar um gate

Mostre:
- decisão necessária;
- estado observado;
- opções;
- riscos;
- evidência;
- recomendação técnica sem executar;
- ação exata que ficará pendente.

Não esconda gate dentro de uma pergunta vaga.

## Fail closed

Se o estado não puder ser reconciliado com confiança:
- não adivinhe;
- preserve o estado;
- marque DESCONHECIDO/CONFLITANTE;
- pare na ação load-bearing.
