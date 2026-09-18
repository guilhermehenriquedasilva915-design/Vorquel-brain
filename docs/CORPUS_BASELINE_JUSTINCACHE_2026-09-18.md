# Baseline medido — JustInCache/n8n-workflows — 2026-09-18

## Escopo

Fonte externa analisada estaticamente:

- Repositório: `JustInCache/n8n-workflows`
- Snapshot pinado: `5a7864987c22930521382b597873b713cc830dac`
- Diretório analisado: `workflows/`
- Execução de workflows externos: **não**
- Execução de código, shell, SSH ou requests contidos no corpus: **não**

## Resultado observado

Total de arquivos JSON analisados: **2057**.

Decisões do analyzer:

- `BLOCKED`: **3**
- `REVIEW_REQUIRED`: **31**
- `SAFE_FOR_LEARNING`: **2023**

Maior severidade por workflow:

- `CRITICAL`: **3**
- `HIGH`: **31**
- `MEDIUM`: **1171**
- `INFO`: **852**

Findings agregados:

- `DECRYPTED_CREDENTIAL_EXPORT`: **3**
- `EXECUTE_COMMAND`: **35**
- `SSH_EXECUTION`: **15**
- `CUSTOM_CODE`: **1249**
- `FILESYSTEM_ACCESS`: **138**
- `NETWORK_REQUEST`: **2123**
- `CODE_EVAL`: **1**
- `CODE_FILESYSTEM`: **2**

Os números acima são **MEDIDOS neste snapshot** e não devem ser generalizados para versões futuras do repositório.

## Workflows bloqueados no baseline

Os três `BLOCKED` continham exportação descriptografada de credenciais n8n:

1. `workflows/Code/0516_Code_GitHub_Create_Scheduled.json`
2. `workflows/Code/1984_Code_Executecommand_Automation_Webhook.json`
3. `workflows/Splitout/1169_Splitout_Code_Import_Webhook.json`

Nos três casos, o comando observado contém `export:credentials` com `--decrypted`.

## Falso positivo encontrado e corrigido

A primeira rodada havia produzido **4** workflows `BLOCKED`.

`workflows/Bitly/0910_Bitly_Datetime_Update_Webhook.json` foi inicialmente escalado para CRITICAL porque o analyzer inferia presença de IA pelo **nome exibido** de um node (`AI Agent`) ao mesmo tempo em que existia um `Execute Command`.

A inspeção mostrou que o node chamado `AI Agent` era do tipo `n8n-nodes-base.noOp`. Logo, o nome sozinho não era evidência suficiente para concluir que um agente de IA controlava execução privilegiada.

A regra foi corrigida para não promover labels/display names a capacidade observada. Após a correção:

- `BLOCKED`: 4 → **3**
- `REVIEW_REQUIRED`: 30 → **31**

Foi adicionado teste de regressão para impedir o retorno desse falso positivo.

## Hardening adicional após o corpus real

- symlinks de entrada agora são bloqueados;
- tamanho de arquivo é verificado antes de ler o conteúdo em memória;
- evidências de código perigoso não armazenam mais o código bruto;
- valores secret-like são totalmente redigidos;
- URLs privadas não são registradas integralmente;
- GitHub Actions foi alterado para `persist-credentials: false`;
- ações externas do CI permanecem pinadas por SHA.

## Interpretação correta

`SAFE_FOR_LEARNING` não significa “seguro para executar” e não transforma o workflow em padrão validado.

Todos os workflows do corpus continuam `RAW_UNTRUSTED` como origem. O analyzer apenas permite triagem estática e classificação inicial.

Próximo gate: revisão estratificada de exemplos `INFO`, `MEDIUM`, `HIGH` e `CRITICAL`, seguida da definição do compilador de conhecimento que separará estrutura/topologia, parâmetros, código, linguagem natural e artefatos que devem permanecer em quarentena.
