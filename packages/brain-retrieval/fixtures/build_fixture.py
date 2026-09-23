"""Generate ``brain_v1_b.json``, the synthetic world the evals run against.

Written as a generator rather than hand-authored JSON so that ids, hashes and
cross-references stay consistent, and so the *intent* behind each object is a
comment next to it instead of being lost in a wall of braces.

Everything here is invented. The names echo the real Vorquel cases only so the
evals read the way the contract states them; no real client data, no real
document and no real measurement appears in this file. Regenerate with:

    python fixtures/build_fixture.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "1.0.0"
OUT = Path(__file__).parent / "brain_v1_b.json"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def scope(scope_type: str, scope_id: str = "GLOBAL") -> dict[str, str]:
    return {"scope_type": scope_type, "scope_id": scope_id}


GLOBAL = scope("GLOBAL_VORQUEL")
VERT_IMOB = scope("VERTICAL", "imobiliaria")
VERT_SAUDE = scope("VERTICAL", "saude")
ENT_CHAVES = scope("ENTITY", "chaves-hugo")
CLI_CHAVES = scope("CLIENT", "chaves")
CLI_JACQ = scope("CLIENT", "jacqueline")
CLI_CLINICA = scope("CLIENT", "clinica")
PRIV = scope("PRIVATE_TEST", "sandbox")


def entity(
    entity_id: str,
    entity_type: str,
    name: str,
    where: dict[str, str],
    *,
    aliases: list[str] | None = None,
    status: str = "ACTIVE",
    sensitivity: dict[str, Any] | None = None,
    updated: str = "2026-06-01T12:00:00Z",
) -> dict[str, Any]:
    payload = {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Entity",
        "entity_id": entity_id,
        "entity_type": entity_type,
        "canonical_name": name,
        "aliases": aliases or [],
        "scope": where,
        "status": status,
        "created_at": "2026-01-10T09:00:00Z",
        "last_updated_at": updated,
    }
    if sensitivity:
        payload["sensitivity"] = sensitivity
    return payload


ENTITIES = [
    # Two entities whose names collide on purpose: "Hugo" alone is ambiguous
    # inside the Chaves entity scope, which is what the ambiguity eval needs.
    entity("ent_chaves_hugo", "COMPANY", "Chaves & Hugo Imoveis", ENT_CHAVES,
           aliases=["Chaves e Hugo", "CH Imoveis", "chaves-hugo"]),
    entity("ent_hugo_pessoa", "PERSON", "Hugo Chaves", ENT_CHAVES,
           aliases=["Hugo"],
           sensitivity={"sensitivity_level": "CLIENT_CONFIDENTIAL", "data_classes": ["PII"]}),
    entity("ent_hugo_silva", "PERSON", "Hugo Silva", ENT_CHAVES,
           aliases=["Hugo"],
           sensitivity={"sensitivity_level": "INTERNAL", "data_classes": ["PII"]}),

    entity("ent_chaves_conta", "CLIENT", "Conta Chaves", CLI_CHAVES, aliases=["Chaves"]),
    entity("ent_jacqueline", "CLIENT", "Jacqueline Consultoria", CLI_JACQ,
           aliases=["Jacqueline", "Jacque"]),
    entity("ent_clinica", "CLIENT", "Clinica Vida", CLI_CLINICA, aliases=["Clinica"]),
    entity("ent_santos", "PROSPECT", "Santos Empreendimentos", VERT_IMOB, aliases=["Santos"]),

    entity("ent_vertical_imob", "VERTICAL", "Imobiliaria", VERT_IMOB),
    entity("ent_vertical_saude", "VERTICAL", "Saude", VERT_SAUDE),
    entity("ent_metodologia", "PROCESS", "Metodologia Vorquel de Diagnostico", GLOBAL,
           aliases=["Metodologia Vorquel"]),

    # SECRET. Must never be resolvable, readable or packable.
    entity("ent_cofre", "SYSTEM", "Cofre de Credenciais", CLI_CHAVES,
           sensitivity={"sensitivity_level": "SECRET", "data_classes": []}),
    entity("ent_sandbox", "PROJECT", "Sandbox de Teste", PRIV),
]


def source(
    source_id: str,
    source_type: str,
    title: str,
    where: dict[str, str],
    *,
    level: str = "INTERNAL",
    classes: list[str] | None = None,
    trust: str = "FIRST_PARTY",
    captured: str = "2026-05-01T10:00:00Z",
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Source",
        "source_id": source_id,
        "source_type": source_type,
        "title": title,
        "origin": f"synthetic://{source_id}",
        "captured_at": captured,
        "ingested_at": captured,
        "scope": where,
        "sensitivity_level": level,
        "data_classes": classes or [],
        "trust_class": trust,
        # External text is data, never instruction. Every fixture source says so.
        "instruction_authority": "NONE",
        "status": "ACTIVE",
        "metadata": {},
    }


SOURCES = [
    source("src_hugo_chat", "MESSAGE", "Mensagem generica sobre marketing digital", GLOBAL,
           level="INTERNAL", trust="FIRST_PARTY"),
    source("src_chaves_call", "TRANSCRIPT", "Call de diagnostico Chaves", ENT_CHAVES,
           level="CLIENT_CONFIDENTIAL", classes=["PII"], trust="CLIENT_PROVIDED"),
    source("src_santos_web", "WEB_PAGE", "Materia publica sobre o mercado imobiliario", VERT_IMOB,
           level="PUBLIC", trust="PUBLIC"),
    source("src_jacq_doc", "DOCUMENT", "Briefing Jacqueline", CLI_JACQ,
           level="CLIENT_CONFIDENTIAL", trust="CLIENT_PROVIDED"),
    source("src_clinica_doc", "DOCUMENT", "Briefing Clinica Vida", CLI_CLINICA,
           level="CLIENT_CONFIDENTIAL", classes=["PII"], trust="CLIENT_PROVIDED"),
    source("src_metodologia", "DOCUMENT", "Metodologia Vorquel de diagnostico operacional", GLOBAL,
           level="INTERNAL", trust="FIRST_PARTY"),
    source("src_medicao_chaves", "DATASET", "Medicao de tempo de resposta Chaves", ENT_CHAVES,
           level="CLIENT_CONFIDENTIAL", trust="CLIENT_PROVIDED"),
    # A public document that contains personal data: the case DIV-2 exists for.
    source("src_publico_pii", "WEB_PAGE", "Lista publica de corretores credenciados", VERT_IMOB,
           level="PUBLIC", classes=["PII"], trust="PUBLIC"),
]


def fragment(
    fragment_id: str, source_id: str, content: str, *, kind: str = "TEXT", start: int = 0
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "object_type": "SourceFragment",
        "fragment_id": fragment_id,
        "source_id": source_id,
        "fragment_type": kind,
        "content": content,
        "content_hash": sha(content),
        "created_at": "2026-05-01T10:05:00Z",
        "provenance": {
            "source_id": source_id,
            "fragment_id": fragment_id,
            "locator": {"kind": "CHAR_RANGE", "start": start, "end": start + len(content)},
            "observed_at": "2026-05-01T10:00:00Z",
            "content_hash": sha(content),
        },
    }


FRAGMENTS = [
    # Generic marketing advice. Mentions lead response time, so it *will* match
    # lexically on a Chaves query. It must still not become Chaves evidence.
    fragment("frg_hugo_chat_1", "src_hugo_chat",
             "tempo de resposta ao lead costuma ser o maior gargalo em vendas"),
    fragment("frg_chaves_call_1", "src_chaves_call",
             "o corretor demora para responder o lead e perdemos a venda"),
    fragment("frg_santos_web_1", "src_santos_web",
             "o mercado imobiliario brasileiro enfrenta atraso no atendimento ao cliente"),
    fragment("frg_jacq_doc_1", "src_jacq_doc",
             "a consultoria precisa de um funil de indicacao estruturado"),
    fragment("frg_clinica_doc_1", "src_clinica_doc",
             "a clinica perde consultas por falha na confirmacao de agendamento"),
    fragment("frg_metodologia_1", "src_metodologia",
             "diagnostico operacional mapeia dados canais processos pessoas e gargalos"),
    fragment("frg_medicao_1", "src_medicao_chaves",
             "tempo medio de primeira resposta medido em 14 horas na amostra de abril"),
    fragment("frg_publico_pii_1", "src_publico_pii",
             "corretores credenciados na regiao com nome e numero de registro"),
]


def claim(
    claim_id: str,
    subject: str,
    predicate: str,
    value: Any,
    where: dict[str, str],
    status_epistemic: str,
    *,
    source_ids: list[str] | None = None,
    provenance: list[dict[str, Any]] | None = None,
    supporting: list[str] | None = None,
    counter: list[str] | None = None,
    status: str = "ACTIVE",
    object_entity_id: str | None = None,
    supersedes: str | None = None,
    superseded_by: str | None = None,
    sensitivity: dict[str, Any] | None = None,
    created: str = "2026-04-01T10:00:00Z",
    updated: str = "2026-06-01T10:00:00Z",
    verification: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Claim",
        "claim_id": claim_id,
        "subject_entity_id": subject,
        "predicate": predicate,
        "object_value": value,
        "epistemic_status": status_epistemic,
        "scope": where,
        "source_ids": source_ids or [],
        "supporting_evidence_ids": supporting or [],
        "counter_evidence_ids": counter or [],
        "status": status,
        "created_at": created,
        "last_updated_at": updated,
    }
    if object_entity_id:
        payload["object_entity_id"] = object_entity_id
    if provenance:
        payload["provenance"] = provenance
    if supersedes:
        payload["supersedes"] = supersedes
    if superseded_by:
        payload["superseded_by"] = superseded_by
    if sensitivity:
        payload["sensitivity"] = sensitivity
    if verification:
        payload["verification_state"] = verification
    return payload


def prov(source_id: str, fragment_id: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "fragment_id": fragment_id,
        "observed_at": "2026-05-01T10:00:00Z",
    }


CLAIMS = [
    # Chaves: a client-stated pain, honestly DECLARADO, with its call cited.
    claim("clm_chaves_dor", "ent_chaves_hugo", "dor_operacional",
          "demora na resposta ao lead", ENT_CHAVES, "DECLARADO",
          source_ids=["src_chaves_call"], provenance=[prov("src_chaves_call", "frg_chaves_call_1")],
          supporting=["evd_chaves_call"],
          sensitivity={"sensitivity_level": "CLIENT_CONFIDENTIAL", "data_classes": ["PII"]},
          verification="REVIEWED"),
    # The same subject, measured, with the dataset cited. MEDIDO *with* a source.
    claim("clm_chaves_tempo", "ent_chaves_hugo", "tempo_primeira_resposta_horas", 14,
          ENT_CHAVES, "MEDIDO",
          source_ids=["src_medicao_chaves"],
          provenance=[prov("src_medicao_chaves", "frg_medicao_1")],
          supporting=["evd_chaves_medicao"],
          sensitivity={"sensitivity_level": "CLIENT_CONFIDENTIAL", "data_classes": []}),
    # A relation, expressed as a claim because RELATION has no schema in V1.
    # Both ends sit in the same scope on purpose. Vertical membership is *not*
    # modelled as a relation here: an ENTITY-scoped caller cannot see a
    # VERTICAL-scoped entity, because Brain-V1-B has no scope inheritance, and a
    # relation pointing across that boundary is exactly what the doctor's
    # cross_scope_leak check is built to reject.
    claim("clm_chaves_responsavel", "ent_chaves_hugo", "tem_responsavel", None,
          ENT_CHAVES, "OBSERVADO",
          object_entity_id="ent_hugo_pessoa",
          source_ids=["src_chaves_call"],
          provenance=[prov("src_chaves_call", "frg_chaves_call_1")]),
    # Santos: public research. INFERIDO, and it must never read as validated pain.
    claim("clm_santos_hipotese", "ent_santos", "dor_hipotetica",
          "atraso no atendimento", VERT_IMOB, "INFERIDO",
          source_ids=["src_santos_web"], provenance=[prov("src_santos_web", "frg_santos_web_1")],
          supporting=["evd_santos_web"]),
    # Jacqueline: her own scope, her own material.
    claim("clm_jacq_dor", "ent_jacqueline", "dor_operacional",
          "funil de indicacao inexistente", CLI_JACQ, "DECLARADO",
          source_ids=["src_jacq_doc"], provenance=[prov("src_jacq_doc", "frg_jacq_doc_1")],
          supporting=["evd_jacq_doc"]),
    # Clinica: health vertical, nothing to do with real estate.
    claim("clm_clinica_dor", "ent_clinica", "dor_operacional",
          "falha na confirmacao de agendamento", CLI_CLINICA, "DECLARADO",
          source_ids=["src_clinica_doc"], provenance=[prov("src_clinica_doc", "frg_clinica_doc_1")],
          supporting=["evd_clinica_doc"],
          sensitivity={"sensitivity_level": "CLIENT_CONFIDENTIAL", "data_classes": ["PII"]}),
    # Global methodology: legitimately reusable in any scope.
    claim("clm_metodologia", "ent_metodologia", "define_etapas",
          "dados, canais, processos, pessoas, gargalos", GLOBAL, "DECLARADO",
          source_ids=["src_metodologia"],
          provenance=[prov("src_metodologia", "frg_metodologia_1")]),
    # A superseded claim and the one that replaced it, so delta has something real.
    claim("clm_chaves_canal_v1", "ent_chaves_hugo", "canal_principal", "telefone",
          ENT_CHAVES, "DECLARADO", source_ids=["src_chaves_call"],
          provenance=[prov("src_chaves_call", "frg_chaves_call_1")],
          status="SUPERSEDED", superseded_by="clm_chaves_canal_v2",
          created="2026-02-01T10:00:00Z", updated="2026-07-01T10:00:00Z"),
    claim("clm_chaves_canal_v2", "ent_chaves_hugo", "canal_principal", "whatsapp",
          ENT_CHAVES, "DECLARADO", source_ids=["src_chaves_call"],
          provenance=[prov("src_chaves_call", "frg_chaves_call_1")],
          supersedes="clm_chaves_canal_v1",
          created="2026-07-01T10:00:00Z", updated="2026-07-01T10:00:00Z"),
    # Two active claims that disagree: a conflict the projection must report and
    # must not resolve.
    claim("clm_chaves_equipe_a", "ent_chaves_hugo", "tamanho_equipe", 4,
          ENT_CHAVES, "DECLARADO", source_ids=["src_chaves_call"],
          provenance=[prov("src_chaves_call", "frg_chaves_call_1")]),
    claim("clm_chaves_equipe_b", "ent_chaves_hugo", "tamanho_equipe", 7,
          ENT_CHAVES, "DECLARADO", source_ids=["src_chaves_call"],
          provenance=[prov("src_chaves_call", "frg_chaves_call_1")],
          counter=["evd_chaves_call"]),
    # PII on a PUBLIC object: allowed, and not a promotion to SECRET.
    claim("clm_publico_pii", "ent_vertical_imob", "corretores_credenciados_publicados", True,
          VERT_IMOB, "OBSERVADO", source_ids=["src_publico_pii"],
          provenance=[prov("src_publico_pii", "frg_publico_pii_1")],
          sensitivity={"sensitivity_level": "PUBLIC", "data_classes": ["PII"]}),
    # SECRET. Never resolvable, never packable.
    claim("clm_secreto", "ent_cofre", "possui_credencial_ativa", True,
          CLI_CHAVES, "OBSERVADO", source_ids=["src_chaves_call"],
          provenance=[prov("src_chaves_call", "frg_chaves_call_1")],
          sensitivity={"sensitivity_level": "SECRET", "data_classes": []}),
]


def evidence(
    evidence_id: str,
    source_id: str,
    fragment_ids: list[str],
    where: dict[str, str],
    evidence_type: str,
    direction: str,
    strength: str,
    status_epistemic: str,
    *,
    subject: str | None = None,
    observed: str | None = "2026-05-01T10:00:00Z",
    sensitivity: dict[str, Any] | None = None,
    provenance: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Evidence",
        "evidence_id": evidence_id,
        "source_id": source_id,
        "fragment_ids": fragment_ids,
        "entity_scope": where,
        "evidence_type": evidence_type,
        "direction": direction,
        "strength": strength,
        "epistemic_status": status_epistemic,
        "observed_at": observed,
        "created_at": "2026-05-02T10:00:00Z",
    }
    if subject:
        payload["subject_entity_id"] = subject
    if sensitivity:
        payload["sensitivity"] = sensitivity
    if provenance:
        payload["provenance"] = provenance
    return payload


EVIDENCE = [
    evidence("evd_chaves_call", "src_chaves_call", ["frg_chaves_call_1"], ENT_CHAVES,
             "DIRECT_STATEMENT", "SUPPORTS", "MODERATE", "DECLARADO",
             subject="ent_chaves_hugo",
             sensitivity={"sensitivity_level": "CLIENT_CONFIDENTIAL", "data_classes": ["PII"]},
             provenance=[prov("src_chaves_call", "frg_chaves_call_1")]),
    evidence("evd_chaves_medicao", "src_medicao_chaves", ["frg_medicao_1"], ENT_CHAVES,
             "MEASUREMENT", "SUPPORTS", "STRONG", "MEDIDO",
             subject="ent_chaves_hugo",
             provenance=[prov("src_medicao_chaves", "frg_medicao_1")]),
    # Generic advice. Global scope, attached to no entity: it is reusable, and
    # it is not an observation about anybody.
    evidence("evd_hugo_generico", "src_hugo_chat", ["frg_hugo_chat_1"], GLOBAL,
             "DIRECT_STATEMENT", "NEUTRAL", "WEAK", "DECLARADO",
             provenance=[prov("src_hugo_chat", "frg_hugo_chat_1")]),
    # Public research about a market. Not a validated operational pain.
    evidence("evd_santos_web", "src_santos_web", ["frg_santos_web_1"], VERT_IMOB,
             "PUBLIC_RESEARCH", "SUPPORTS", "WEAK", "INFERIDO",
             subject="ent_santos",
             provenance=[prov("src_santos_web", "frg_santos_web_1")]),
    evidence("evd_jacq_doc", "src_jacq_doc", ["frg_jacq_doc_1"], CLI_JACQ,
             "DIRECT_STATEMENT", "SUPPORTS", "MODERATE", "DECLARADO",
             subject="ent_jacqueline",
             provenance=[prov("src_jacq_doc", "frg_jacq_doc_1")]),
    evidence("evd_clinica_doc", "src_clinica_doc", ["frg_clinica_doc_1"], CLI_CLINICA,
             "DIRECT_STATEMENT", "SUPPORTS", "MODERATE", "DECLARADO",
             subject="ent_clinica",
             sensitivity={"sensitivity_level": "CLIENT_CONFIDENTIAL", "data_classes": ["PII"]},
             provenance=[prov("src_clinica_doc", "frg_clinica_doc_1")]),
    evidence("evd_metodologia", "src_metodologia", ["frg_metodologia_1"], GLOBAL,
             "ARTIFACT", "SUPPORTS", "STRONG", "DECLARADO",
             subject="ent_metodologia",
             provenance=[prov("src_metodologia", "frg_metodologia_1")]),
    # Contradictory evidence that coexists with the supporting kind.
    evidence("evd_chaves_contra", "src_chaves_call", ["frg_chaves_call_1"], ENT_CHAVES,
             "OBSERVATION", "CONTRADICTS", "WEAK", "OBSERVADO",
             subject="ent_chaves_hugo",
             provenance=[prov("src_chaves_call", "frg_chaves_call_1")]),
    # PUBLIC evidence carrying PII. Retrievable, marked, not excluded.
    evidence("evd_publico_pii", "src_publico_pii", ["frg_publico_pii_1"], VERT_IMOB,
             "ARTIFACT", "NEUTRAL", "WEAK", "OBSERVADO",
             sensitivity={"sensitivity_level": "PUBLIC", "data_classes": ["PII"]},
             provenance=[prov("src_publico_pii", "frg_publico_pii_1")]),
    # SECRET evidence. Must never surface.
    evidence("evd_secreto", "src_chaves_call", ["frg_chaves_call_1"], CLI_CHAVES,
             "ARTIFACT", "SUPPORTS", "STRONG", "OBSERVADO",
             subject="ent_cofre",
             sensitivity={"sensitivity_level": "SECRET", "data_classes": []},
             provenance=[prov("src_chaves_call", "frg_chaves_call_1")]),
]


def decision(
    decision_id: str,
    where: dict[str, str],
    title: str,
    text: str,
    status: str,
    effective: str,
    *,
    supersedes: str | None = None,
    superseded_by: str | None = None,
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Decision",
        "decision_id": decision_id,
        "scope": where,
        "title": title,
        "decision": text,
        "status": status,
        "effective_from": effective,
        "source_ids": source_ids or [],
        "created_at": effective,
    }
    if supersedes:
        payload["supersedes"] = supersedes
    if superseded_by:
        payload["superseded_by"] = superseded_by
    return payload


DECISIONS = [
    # The supersession pair: the old one must never win.
    decision("dec_chaves_canal_v1", ENT_CHAVES, "Canal de atendimento",
             "atender leads prioritariamente por telefone", "SUPERSEDED",
             "2026-02-01T00:00:00Z", superseded_by="dec_chaves_canal_v2"),
    decision("dec_chaves_canal_v2", ENT_CHAVES, "Canal de atendimento",
             "atender leads prioritariamente por whatsapp", "ACTIVE",
             "2026-07-01T00:00:00Z", supersedes="dec_chaves_canal_v1"),
    # A stale ACTIVE beside a filled supersedes: the shape that lets an old
    # decision beat a new one if only `status` is checked.
    decision("dec_global_evidencia", GLOBAL, "Evidencia obrigatoria",
             "nenhum status MEDIDO sem fonte rastreavel", "ACTIVE",
             "2026-01-01T00:00:00Z",
             source_ids=["src_metodologia"]),
    decision("dec_jacq_escopo", CLI_JACQ, "Escopo Jacqueline",
             "nao reutilizar material de outro cliente", "ACTIVE", "2026-03-01T00:00:00Z"),
    decision("dec_clinica_escopo", CLI_CLINICA, "Escopo Clinica",
             "conteudo de saude nao herda praticas de imobiliaria", "ACTIVE",
             "2026-03-01T00:00:00Z"),
]

HYPOTHESES = [
    {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Hypothesis",
        "hypothesis_id": "hyp_chaves_resposta",
        "entity_scope": ENT_CHAVES,
        "statement": "reduzir o tempo de primeira resposta aumenta a conversao",
        "status": "OPEN",
        "supporting_evidence_ids": ["evd_chaves_medicao"],
        "counter_evidence_ids": ["evd_chaves_contra"],
        "falsification_criteria": "conversao nao muda apos reduzir o tempo para menos de 2 horas",
        "next_best_learning": "medir conversao antes e depois de um SLA de 2 horas",
        "created_at": "2026-05-10T10:00:00Z",
        "last_updated_at": "2026-06-10T10:00:00Z",
    },
    {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Hypothesis",
        "hypothesis_id": "hyp_santos_dor",
        "entity_scope": VERT_IMOB,
        "statement": "Santos tem a mesma dor observada no mercado",
        "status": "OPEN",
        "supporting_evidence_ids": ["evd_santos_web"],
        "counter_evidence_ids": [],
        "falsification_criteria": "entrevista com Santos nao menciona atraso no atendimento",
        "next_best_learning": "entrevistar Santos diretamente",
        "created_at": "2026-05-10T10:00:00Z",
        "last_updated_at": "2026-05-10T10:00:00Z",
    },
]

UNKNOWNS = [
    {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Unknown",
        "unknown_id": "unk_chaves_volume",
        "entity_scope": ENT_CHAVES,
        "statement": "volume mensal de leads recebidos",
        "priority": "HIGH",
        "status": "OPEN",
        "related_hypothesis_ids": ["hyp_chaves_resposta"],
        "related_question_ids": [],
        "created_at": "2026-05-10T10:00:00Z",
        "last_updated_at": "2026-05-10T10:00:00Z",
    },
    {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Unknown",
        "unknown_id": "unk_chaves_crm",
        "entity_scope": ENT_CHAVES,
        "statement": "qual CRM a equipe usa hoje",
        "priority": "MEDIUM",
        "status": "RESOLVED",
        "related_hypothesis_ids": [],
        "related_question_ids": [],
        "created_at": "2026-04-10T10:00:00Z",
        "last_updated_at": "2026-07-15T10:00:00Z",
    },
]

EVENTS = [
    {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Event",
        "event_id": "evt_chaves_call",
        "event_type": "INGESTION",
        "entity_scope": ENT_CHAVES,
        "occurred_at": "2026-05-01T10:00:00Z",
        "recorded_at": "2026-05-01T11:00:00Z",
        "actor": "operador",
        "source_ids": ["src_chaves_call"],
        "metadata": {},
    },
    {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Event",
        "event_id": "evt_chaves_decisao",
        "event_type": "DECISION_MADE",
        "entity_scope": ENT_CHAVES,
        "occurred_at": "2026-07-01T00:00:00Z",
        "recorded_at": "2026-07-01T00:30:00Z",
        "actor": "operador",
        "source_ids": [],
        "metadata": {"decision_id": "dec_chaves_canal_v2"},
    },
    # Occurred in March, recorded in September: the gap between occurred_at and
    # recorded_at, which get_delta must surface rather than flatten.
    {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Event",
        "event_id": "evt_chaves_tardio",
        "event_type": "OUTCOME_OBSERVED",
        "entity_scope": ENT_CHAVES,
        "occurred_at": "2026-03-15T10:00:00Z",
        "recorded_at": "2026-09-01T10:00:00Z",
        "actor": "operador",
        "source_ids": ["src_chaves_call"],
        "metadata": {},
    },
    {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Event",
        "event_id": "evt_jacq_ingest",
        "event_type": "INGESTION",
        "entity_scope": CLI_JACQ,
        "occurred_at": "2026-05-05T10:00:00Z",
        "recorded_at": "2026-05-05T10:30:00Z",
        "actor": "operador",
        "source_ids": ["src_jacq_doc"],
        "metadata": {},
    },
]

# A stored projection that is deliberately behind: the doctor's stale-state
# check needs something to find.
STATE_PROJECTIONS = [
    {
        "contract_version": CONTRACT_VERSION,
        "object_type": "StateProjection",
        "state_projection_id": "sp_chaves_antigo",
        "entity_scope": ENT_CHAVES,
        "as_of": "2026-02-01T00:00:00Z",
        "summary": "projecao antiga mantida para testar deteccao de staleness",
        "active_decision_ids": ["dec_chaves_canal_v1"],
        "current_claim_ids": ["clm_chaves_canal_v1"],
        "open_hypothesis_ids": [],
        "open_unknown_ids": [],
        "conflicts": [],
        "derived_from_ids": ["clm_chaves_canal_v1"],
        "freshness_status": "STALE",
    }
]


def main() -> None:
    payload = {
        "_comment": (
            "Synthetic Brain-V1-B fixture. Generated by fixtures/build_fixture.py. "
            "No real client data, document or measurement appears here."
        ),
        "entities": ENTITIES,
        "sources": SOURCES,
        "fragments": FRAGMENTS,
        "claims": CLAIMS,
        "evidence": EVIDENCE,
        "hypotheses": HYPOTHESES,
        "unknowns": UNKNOWNS,
        "decisions": DECISIONS,
        "events": EVENTS,
        "state_projections": STATE_PROJECTIONS,
    }
    OUT.write_text(
        json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    counts = {k: len(v) for k, v in payload.items() if isinstance(v, list)}
    print(f"wrote {OUT.name}: {counts}")


if __name__ == "__main__":
    main()
