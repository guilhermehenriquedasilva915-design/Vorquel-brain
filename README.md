# Vorquel Brain

Repositório privado para os componentes do cérebro operacional da Vorquel.

## Princípios

- Conteúdo externo é **dado não confiável**, nunca instrução.
- Nenhum corpus externo pode autorizar tools, shell, rede, filesystem ou credenciais.
- Evidência e proveniência devem ser preservadas.
- Workflows, vídeos, documentos e mensagens entram como fontes; só material testado e promovido pela Vorquel pode virar padrão validado.
- DEV e sandbox primeiro; produção exige aprovação explícita.

## Módulos iniciais

- `n8n-analyzer`: análise estática de workflows n8n sem execução.
- `n8n-brain`: catálogo/knowledge layer posterior.
- `content-brain`: ingestão e proveniência posterior.

> Estado atual: arquitetura + primeiro MVP do analisador estático.
