# DATA_POLICY — classificacao, escopo e LGPD

## Classificacao

| Classe | Regra |
|---|---|
| `PUBLIC` | livre |
| `INTERNAL` | default; conhecimento da Vorquel |
| `CLIENT_CONFIDENTIAL` | so no escopo do cliente; nunca global sem minimizacao |
| `PII` | minimizar, redigir, preferir dado sintetico; nao persistir payload completo |
| `SECRET` | **nunca** entra em knowledge, log ou experiencia |

`SECRET` nao tem coluna no banco de proposito. Nao existe rotulo para guardar um
segredo "com cuidado" — a restricao falha fechada.

## Escopo

`GLOBAL_VORQUEL` · `CLIENT:x` · `PROJECT:x` · `PRIVATE_TEST:x`

`scope_id` e opaco: nao coloque nome de empresa, CNPJ ou e-mail nele. Use um
identificador estavel e sem significado (`acme7f2`).

Retrieval devolve **escopo pedido + GLOBAL_VORQUEL**. Nunca `CLIENT_A →
CLIENT_B`. Essa regra e aplicada em tres lugares — no RPC, na query de fallback
e numa checagem por linha depois da query — porque e a unica que, se falhar,
falha na frente de um cliente.

## Na duvida, escolha o escopo mais estreito

Promover depois e uma decisao humana de um minuto. Despromover nao existe: o que
vazou, vazou.

## Experiencia operacional

Guarde a **estrutura** do erro, nao o dado pessoal:

- sim: `"Postgres insert falhou: coluna 'email' viola NOT NULL"`;
- nao: `"Postgres insert falhou para joao.silva@cliente.com.br"`.

## Minimizacao de PII

1. o dado e necessario para o conhecimento ser util? normalmente nao;
2. da para substituir por dado sintetico? use;
3. da para descrever a forma sem o valor? descreva;
4. se ainda assim precisa, classifique `PII` e mantenha no escopo do cliente.

## O que nunca e persistido

payload cru de execucao · header de autorizacao · cookie · token · chave
privada · credencial (nem por alias com valor) · e-mail ou telefone de pessoa
real quando evitavel.

## Ambiente

`SECRET` tambem nao aparece em saida de diagnostico. O `brain doctor` diz se uma
variavel **esta definida**, nunca o valor.
