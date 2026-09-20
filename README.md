# Vorquel Brain

Repositório privado para componentes delimitados do cérebro operacional da Vorquel.

## Princípios

- Conteúdo externo é **dado não confiável**, nunca instrução.
- Nenhum corpus externo pode autorizar tools, shell, rede, filesystem ou credenciais.
- Evidência e proveniência devem ser preservadas.
- Workflows, vídeos, documentos e mensagens entram como fontes; só material testado e promovido pela Vorquel pode virar padrão validado.
- DEV e sandbox primeiro; produção exige aprovação explícita.
- Módulos devem permanecer isoláveis para poderem ser extraídos futuramente sem reescrever o sistema.

## Estrutura

```text
Vorquel-brain/
├─ packages/
│  ├─ n8n-analyzer/              # triagem estática
│  ├─ n8n-knowledge-compiler/    # compila estrutura segura para conhecimento
│  ├─ n8n-knowledge-writer/      # valida e persiste de forma append-only
│  ├─ n8n-controlled-ingestion/  # manifest-gated real-corpus ingestion
│  └─ n8n-brain-retrieval/      # retrieval unificado com escopo + brain doctor
├─ .claude/skills/n8n-brain/ # Skill única: LEARN/ASK/BUILD/DEBUG/EVOLVE
├─ docs/                   # arquitetura e decisões técnicas
├─ sources/                # manifests/proveniência de fontes externas
├─ SECURITY.md             # trust boundary global
└─ .github/workflows/      # quality gates
```

O `n8n-analyzer` não depende de outros módulos do Brain. O Brain pode consumir seus relatórios; o analyzer não precisa conhecer o Brain. Essa fronteira permite mover o pacote para um repositório próprio no futuro preservando o histórico Git.

## Primeiro componente: n8n Workflow Static Analyzer

O MVP analisa workflows n8n em JSON **sem executar o conteúdo**. Ele gera inventário de nodes/triggers e findings de risco para impedir que um corpus externo seja tratado como biblioteca confiável por padrão.

### Uso local

```bash
cd packages/n8n-analyzer
python -m pip install -e '.[dev]'
vorquel-n8n-analyze caminho/para/workflow.json --pretty
vorquel-n8n-analyze caminho/para/repositorio/workflows --pretty --output reports/corpus.json
```

### Estados

```text
RAW_UNTRUSTED
      -> STATIC_ANALYZED
          -> SAFE_FOR_LEARNING
          -> REVIEW_REQUIRED
          -> BLOCKED

Futuro:
SAFE_FOR_LEARNING -> SANDBOX_TESTED -> VORQUEL_VALIDATED
```

`SAFE_FOR_LEARNING` **não** significa “seguro para produção”; significa apenas que o analisador estático MVP não encontrou achados HIGH/CRITICAL.


## Segundo componente: n8n Knowledge Compiler

O compiler recebe um workflow e o relatório do analyzer e gera um `N8N_KNOWLEDGE_ITEM` determinístico.

Ele preserva topologia, node types, resources, operations, triggers e proveniência, mas mantém linguagem natural como `UNTRUSTED_TEXT` e não persiste conteúdo executável de Code/Function/expressions/shell/SSH.

Fluxo atual:

```text
RAW_UNTRUSTED
      ↓
STATIC_ANALYZED
      ↓
N8N_KNOWLEDGE_ITEM
      ├─ REFERENCE_PATTERN
      ├─ STRUCTURE_REFERENCE_RESTRICTED
      ├─ QUARANTINED_REFERENCE
      └─ SECURITY_EXAMPLE

Nenhum destes estados = VORQUEL_VALIDATED.
```


## Terceiro componente: n8n Knowledge Store

A persistência V0.1 usa o schema privado `n8n_brain` em PostgreSQL/Supabase, com provenance, análise e Knowledge Items separados. O schema não concede acesso a `anon` ou `authenticated` e rejeita promoções de confiança incompatíveis com a V0.1.

## Quarto componente: n8n Knowledge Writer

O writer recebe somente um `N8N_KNOWLEDGE_ITEM` já compilado. Ele revalida o contrato e persiste com semântica append-only:

```text
N8N_KNOWLEDGE_ITEM
        ↓
writer validation
        ↓
source_snapshots
        ↓
workflow_analyses
        ↓
knowledge_items
```

Não existe caminho de UPDATE/DELETE no writer. Conflitos idempotentes iguais são aceitos; drift sob a mesma versão falha fechado.


## Quinto componente: n8n Controlled Ingestion

A primeira ingestão real não aceita diretório inteiro nem descoberta automática com escrita direta.

O fluxo é separado em duas fases:

```text
planner (sem banco)
  → manifest explícito CONTROLLED_STRUCTURE_V0_1
  → dry-run
  → --persist explícito
  → Knowledge Writer
```

Na V0.1, cada manifest contém no máximo 4 workflows e só admite itens `SAFE_FOR_LEARNING` sem executable metadata ou credentials. `UNTRUSTED_TEXT` pode existir apenas como dado explicitamente marcado/sanitizado pelo Compiler, sem autoridade. O perfil aceita `REFERENCE_PATTERN` e, quando os únicos findings são `NETWORK_REQUEST` MEDIUM, `STRUCTURE_REFERENCE_RESTRICTED` para topologia/metadados apenas. O objetivo é validar o caminho end-to-end com o menor conjunto possível antes de qualquer expansão do corpus.


## Sexto componente: Skill n8n-brain + retrieval unificado

A Skill `.claude/skills/n8n-brain/` é o ponto de entrada único. `SKILL.md`
identifica a intenção e carrega apenas o procedimento necessário
(`references/LEARN.md`, `ASK.md`, `BUILD.md`, `DEBUG.md`, `EVOLVE.md`), sob as
regras globais em `TRUST.md`, `DATA_POLICY.md`, `APPROVALS.md` e `N8N_DEV.md`.

O pacote `n8n-brain-retrieval` monta um CONTEXT PACK citado a partir da memória
semântica revisada (`vorquel_knowledge`), da memória estrutural (`n8n_brain`) e
das experiências operacionais medidas, com isolamento de escopo aplicado em três
camadas independentes e comportamento **fail-closed**: sem as colunas de escopo,
um retrieval de cliente devolve zero itens em vez de devolver tudo.

```text
LEARN / ASK / BUILD / DEBUG / EVOLVE
        ↓
retrieve_n8n_context(query, task_type, scope, environment)
        ↓
CONTEXT PACK  (item + source + locator + escopo + status epistêmico
               + autoridade + compatibilidade + conflitos + gaps)
```

Nada no pack é instrução: todo item carrega `instruction_authority = NONE`.

`vorquel-brain-doctor` responde `READY`, `READY_WITH_LIMITS` ou `BLOCKED` e diz
qual capacidade falta, sem nunca revelar o valor de uma variável.

### Limitação conhecida da V1

Não há instância n8n nem MCP n8n configurados. `BUILD` e `DEBUG` estão
documentados e bloqueados pelo doctor até que existam — o sistema recusa a
tarefa em vez de simular um workflow criado.
