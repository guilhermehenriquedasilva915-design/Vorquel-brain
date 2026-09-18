# n8n Workflow Static Analyzer

Componente isolado do Vorquel Brain para análise estática de workflows n8n.

## Fronteira de segurança

Este pacote recebe JSON externo como **RAW_UNTRUSTED**. Ele não executa workflows, código, shell, SSH ou requests encontrados no conteúdo.

O pacote não depende de outros módulos do Vorquel Brain. Essa regra é intencional para permitir extração futura para um repositório próprio sem refatoração estrutural relevante.

## Desenvolvimento

```bash
cd packages/n8n-analyzer
python -m pip install -e '.[dev]'
ruff check .
pytest
```

## CLI

```bash
vorquel-n8n-analyze workflow.json --pretty
vorquel-n8n-analyze diretorio/com/workflows --pretty --output reports/corpus.json
```
