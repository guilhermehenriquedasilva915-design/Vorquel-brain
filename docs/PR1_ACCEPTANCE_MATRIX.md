# PR1 — matriz de aceitacao: LEARN + ASK

O que o PR1 tem de provar: **uma fonte externa vira conhecimento aprovado,
citavel, isolado por escopo — e responde uma pergunta**. Nao "existe uma Skill
e existe retrieval".

Esta matriz e escrita contra o codigo que existe, com a evidencia que roda. Um
item so e `IMPLEMENTADO` se algum teste falha quando a regra e quebrada.

Legenda: **I** implementado · **P** parcial · **A** ausente

---

## 1. Ciclo e entrada

| Requisito | Status | Evidencia |
|---|---|---|
| Skill unica `n8n-brain`, roteada por intencao | I | `.claude/skills/n8n-brain/SKILL.md`; procedimentos em `references/` carregados por intencao |
| Intent LEARN | I | `references/LEARN.md`; `packages/n8n-brain-learn` implementa o contrato |
| Intent ASK | I | `references/ASK.md`; `retrieve_n8n_context()` em `packages/n8n-brain-retrieval/src/.../retrieval.py` |
| Retrieval unificado (knowledge + n8n_brain + experiencia) | I | `retrieval.py`; `tests/test_context_pack.py` |
| BUILD / DEBUG bloqueados enquanto nao houver n8n | I | `doctor.py` retorna `BLOCKED`; CI `n8n-brain-retrieval-quality` falha se o doctor mentir |

## 2. Escopo — o gate mais importante

| Requisito | Status | Evidencia |
|---|---|---|
| GLOBAL ve GLOBAL | I | Watch `supabase/tests/knowledge_scope_and_external_sources.sql` §4 |
| CLIENT A ve GLOBAL + A | I | idem §4 |
| CLIENT A **nao** ve CLIENT B | I | idem §4, assercao simetrica nos dois sentidos |
| CLIENT nao ve PRIVATE_TEST | I | idem §4 |
| Sem migration de escopo, retrieval de cliente falha fechado | I | `retrieval.py` `_fetch_knowledge`; `tests/test_scope_isolation.py` |
| Escopo malformado falha em vez de ampliar | I | SQL §4; `tests/test_scope_and_locators.py` |
| Candidato nao pode ser arquivado em escopo alheio ao da fonte | I | Watch 0023 `create_knowledge_candidate_scoped`; SQL §4 |
| Isolamento em tres camadas independentes | I | RPC (0022) + filtro por linha (`Scope.admits`) + validacao de entrada |

## 3. Politica de dados

| Requisito | Status | Evidencia |
|---|---|---|
| SECRET rejeitado | I | `policy.py` `SecretDetected`; `tests/test_data_policy.py` cobre 10 formatos; DB nao tem classificacao SECRET (0021) e 0023 recusa explicitamente |
| Nunca persistir password / token / API key / cookie / chave privada | I | `tests/test_data_policy.py::test_a_secret_bearing_unit_is_refused_but_the_batch_reports_it`; `test_a_repo_secret_is_refused_rather_than_stored` |
| Segredo nao vaza nem na mensagem de erro | I | `test_every_secret_shape_is_refused`; `test_a_bad_dsn_never_appears_in_the_error` |
| PII minimizada, nao descartada | I | `test_pii_is_minimised_and_widens_the_classification` |
| Classificacao so amplia | I | `test_classification_is_never_narrowed` |
| Mencionar credencial != vazar credencial | I | `test_naming_a_credential_is_not_leaking_one` |

## 4. Revisao humana

| Requisito | Status | Evidencia |
|---|---|---|
| Candidato criado **nao** aparece como knowledge aprovado | I | SQL §3: `search_knowledge_items_scoped` nao retorna nada antes da aprovacao |
| Depois de aprovacao explicita, aparece no retrieval | I | SQL §3 |
| Nada no pacote LEARN aprova | I | `writer.py` so chama `create_knowledge_candidate_scoped`; CLI nao tem flag de aprovacao |
| Batch opera so sobre IDs ja apresentados | I | `approve_knowledge_candidates_batch(p_candidate_ids text[])`; SQL §6 |
| Batch limitado a um tamanho humano | I | cap de 50; SQL §6 rejeita 51 |
| Trilha de auditoria por aprovacao | I | SQL §6 verifica `knowledge_reviews` com `actor_type = 'HUMAN'` |
| Um item ruim nao derruba o lote em silencio | I | SQL §6: resultado por candidato |

## 5. Proveniencia e citacao

| Requisito | Status | Evidencia |
|---|---|---|
| Locator generico por tipo de fonte | I | Watch 0021 `locator_kind` + `locator` |
| Proveniencia sobrevive a aprovacao | I | **regressao corrigida no 0023**; SQL §3 falha se `PDF_PAGE` sumir na aprovacao |
| Locator e endereco, nunca payload | I | constraint `knowledge_sources_locator_no_secret_check`; `validate_locator`; SQL §5 |
| Citacao no CONTEXT PACK | I | `contextpack.py`; `tests/test_context_pack.py` |

## 6. Versionamento de fonte

| Requisito | Status | Evidencia |
|---|---|---|
| Mesma fonte + mesmo hash = idempotente | I | SQL §2 (fonte) e §3 (candidato, com `reused = true` no replay) |
| Hash/commit diferente = nova versao | I | SQL §2: versao 2 com `supersedes_source_id` |
| Historico anterior preservado | I | SQL §2 verifica que a versao 1 continua existindo |
| Identidade derivada do conteudo, nao do relogio | I | `model.py`; `test_learning_the_same_material_twice_is_identical` |

## 7. Fronteira de prompt injection

| Requisito | Status | Evidencia |
|---|---|---|
| Todo texto de fonte e `UNTRUSTED_DERIVED` / autoridade `NONE` | I | `untrusted.py`; constraints em 0014/0021 |
| Tentativa de instruir e detectada | I | `tests/test_untrusted_boundary.py`, 7 formatos (PT e EN) |
| Trecho sinalizado e mostrado ao revisor, nao descartado | I | `test_a_flagged_unit_is_kept_and_surfaced_not_silently_dropped` |
| Repositorio nao configura o agente que o le | I | `test_an_agent_config_file_is_read_as_evidence_without_authority` |

## 8. Adaptadores de fonte

| Fonte | Status | Evidencia |
|---|---|---|
| mensagem / texto | I | `adapters/text.py`; `test_client_material_is_never_quietly_global` |
| `.txt` | I | `test_plain_text_falls_back_to_paragraphs` |
| `.md` | I | `test_markdown_is_addressed_by_heading` |
| `.json` | I | `test_json_is_addressed_by_path` |
| PDF | I | `test_pdf_is_addressed_by_page` (PDF real, extracao real) |
| DOCX | I | `test_docx_is_addressed_by_section` (`.docx` real) |
| repositorio Git | I | `tests/test_repo_adapter.py`, 10 casos incluindo symlink e path traversal |
| workflow n8n | I | `tests/test_workflow_and_watch.py`; sem bypass do Analyzer/Compiler |
| Watch / YouTube | **P** | contrato e proveniencia testados com fixture; o E2E de video real depende do runtime do Watch. Limite declarado, nao mascarado |

Sem macro e sem execucao: `.docm`/`.dotm` recusados pela extensao,
`vbaProject.bin` recusado dentro de um `.docx` aparentemente inocente.
Texto nativo preferido; **sem OCR** — um PDF digitalizado levanta erro em vez de
devolver um lote vazio que parece sucesso.

## 9. Guardas de repositorio

| Requisito | Status | Evidencia |
|---|---|---|
| URL explicita, https | I | `test_a_non_https_url_is_refused` |
| Pin por commit (branch recusada) | I | `test_a_branch_name_is_not_a_pin` |
| Sem setup, sem executar codigo | I | `repo.py` so faz init/remote/fetch/checkout/rev-parse |
| Sem git hooks | I | `core.hooksPath=/dev/null`, `credential.helper=` vazio |
| Sem submodules | I | `--no-recurse-submodules` |
| README/CLAUDE.md sem autoridade | I | `test_an_agent_config_file_is_read_as_evidence_without_authority` |
| Symlink e path traversal bloqueados | I | `test_a_symlink_is_never_followed` (roda no Linux do CI; CI falha se for pulado) |
| Limites de tamanho | I | `test_an_oversized_file_is_skipped` |
| Binarios ignorados | I | `test_a_binary_disguised_as_text_is_skipped` (sniff de conteudo, nao so extensao) |
| Commit obtido == commit pedido | I | `checkout_pinned` confere `rev-parse HEAD` |

---

## Limitacoes reais deste PR

1. **Watch / video**: provado no contrato, nao ponta a ponta. Nenhum teste aqui
   afirma que transcricao ou OCR funcionam — essa afirmacao pertence ao
   Vorquel Watch.
2. **Persistencia Python contra schema real**: o schema `vorquel_knowledge`
   vive no repositorio Vorquel Watch, que este CI nao faz checkout. A prova
   SQL da cadeia LEARN -> revisao -> retrieval roda la, no job
   `knowledge-migrations`. Aqui, os testes de persistencia pulam quando nao ha
   `N8N_BRAIN_TEST_DATABASE_URL` — e o skip e visivel, nunca um falso verde.
3. **BUILD e DEBUG continuam bloqueados**: nao existe instancia n8n nem MCP
   n8n. O doctor responde `BLOCKED` e o CI falha se ele responder outra coisa.
4. **Nenhuma migration foi aplicada live.** Ver `MIGRATIONS_PENDING.md`.
