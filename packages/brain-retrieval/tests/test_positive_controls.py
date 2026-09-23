"""Positive controls: the things that must still work.

A scope guard that returned nothing would pass every negative eval in this
suite. These are the tests that stop the isolation rules from being satisfied by
a system that simply refuses to answer, which is the cheap way to look safe.
"""

from __future__ import annotations

import json

from vorquel_brain_contract import check_pii_orthogonality

from vorquel_brain_retrieval import (
    Scope,
    detect_promotion,
    expand_relations,
    get_context_pack,
    get_entity,
    get_state,
    resolve_entity,
    search_evidence,
)
from vorquel_brain_retrieval.scope import ScopeGuard


def test_global_methodology_reaches_an_entity_pack(store, chaves):
    """Vorquel's own methodology is global because it applies everywhere.

    If global material could not reach a client pack, the scope rules would be
    isolating the Brain from itself.
    """
    pack = get_context_pack(
        store, "diagnostico operacional", chaves, entity_ids=("ent_chaves_hugo",)
    ).pack

    assert "clm_metodologia" in pack["claim_ids"], "global methodology did not reach the pack"
    assert "dec_global_evidencia" in pack["decision_ids"], "the global rule did not reach the pack"
    assert any("MEDIDO sem fonte" in c for c in pack["constraints"])


def test_global_methodology_reaches_a_client_pack(store, jacqueline):
    pack = get_context_pack(
        store, "diagnostico operacional", jacqueline, entity_ids=("ent_jacqueline",)
    ).pack
    assert "clm_metodologia" in pack["claim_ids"]
    # And the client's own material is there too, not only the global part.
    assert "clm_jacq_dor" in pack["claim_ids"]


def test_pii_does_not_imply_secret(store, imobiliaria):
    """A PUBLIC object carrying PII stays PUBLIC and stays retrievable.

    DIV-2 exists because PII is a data category and not a confidentiality tier.
    Auto-promoting it to SECRET would make public material unrepresentable and
    would quietly delete it from every pack.
    """
    evidence = store.by_id("Evidence", "evd_publico_pii")
    assert evidence["sensitivity"]["sensitivity_level"] == "PUBLIC"
    assert evidence["sensitivity"]["data_classes"] == ["PII"]
    assert check_pii_orthogonality(evidence) == []

    found = search_evidence(store, "corretores credenciados", imobiliaria)
    hit = next((h for h in found.hits if h.evidence_id == "evd_publico_pii"), None)
    assert hit is not None, "PUBLIC evidence carrying PII was excluded as if it were SECRET"
    assert hit.sensitivity_level == "PUBLIC"
    assert "PII" in hit.data_classes, "the PII marking was lost on the way out"


def test_pii_is_carried_into_the_pack_as_a_marking_not_a_tier(store, chaves):
    pack = get_context_pack(
        store, "dor operacional", chaves, entity_ids=("ent_chaves_hugo",)
    ).pack
    assert "PII" in pack["data_classes"], "the pack lost the PII marking it must minimise against"
    assert pack["sensitivity_level"] != "SECRET"
    # CLIENT_CONFIDENTIAL is neither strengthened nor weakened by carrying PII.
    assert pack["sensitivity_level"] == "CLIENT_CONFIDENTIAL"


def test_legitimate_relation_expansion_is_allowed(store, chaves):
    """One hop, inside the scope, to an entity the caller may already read."""
    guard = ScopeGuard(requested=chaves)
    reached = expand_relations(store, ("ent_chaves_hugo",), guard)

    assert "ent_hugo_pessoa" in reached, "a legitimate in-scope relation was not expanded"
    for entity_id in reached:
        entity = store.by_id("Entity", entity_id)
        assert guard.admits(entity), f"expansion reached {entity_id}, which is out of scope"


def test_expansion_stops_at_the_scope_boundary(store, jacqueline):
    guard = ScopeGuard(requested=jacqueline)
    assert expand_relations(store, ("ent_chaves_hugo",), guard) == ()


def test_contradictory_evidence_coexists_with_supporting_evidence(store, chaves):
    """A conflict is reported and left standing, not adjudicated away."""
    found = search_evidence(
        store, "corretor demora responder lead", chaves, entity_ids=("ent_chaves_hugo",)
    )
    directions = {h.evidence_id: h.direction for h in found.hits}

    assert directions.get("evd_chaves_call") == "SUPPORTS"
    assert directions.get("evd_chaves_contra") == "CONTRADICTS", (
        "contradicting evidence was filtered out of the result"
    )

    state = get_state(store, chaves)
    assert state["conflicts"], "the projection resolved a conflict instead of reporting it"
    # Both sides of the disagreement survive as current claims.
    assert "clm_chaves_equipe_a" in state["current_claim_ids"]
    assert "clm_chaves_equipe_b" in state["current_claim_ids"]


def test_an_allowed_promotion_is_not_blocked(store):
    """DESCONHECIDO is forbidden to jump to MEDIDO; HIPOTESE to INVALIDADO is fine.

    Without this, a detector that returned FORBIDDEN unconditionally would pass
    every promotion eval in the suite.
    """
    stored = store.by_id("Claim", "clm_chaves_dor")
    allowed = dict(stored, epistemic_status="CONFLITANTE")

    finding = detect_promotion(store, allowed)

    assert finding.verdict == finding.ALLOWED
    assert finding.violations == ()


def test_an_unchanged_status_is_reported_as_unchanged(store):
    stored = store.by_id("Claim", "clm_chaves_dor")
    finding = detect_promotion(store, dict(stored))
    assert finding.verdict == finding.UNCHANGED


def test_the_owner_can_read_its_own_material(store, jacqueline):
    """The mirror of every leak test: in-scope reads actually return something."""
    entity = get_entity(store, "ent_jacqueline", jacqueline)
    assert getattr(entity, "canonical_name", None) == "Jacqueline Consultoria"

    resolution = resolve_entity(store, "Jacque", jacqueline)
    assert resolution.resolved_entity_id == "ent_jacqueline"

    found = search_evidence(store, "funil de indicacao", jacqueline, entity_ids=("ent_jacqueline",))
    assert [h.evidence_id for h in found.hits] == ["evd_jacq_doc"]

    state = get_state(store, jacqueline)
    assert "clm_jacq_dor" in state["current_claim_ids"]
    assert "dec_jacq_escopo" in state["active_decision_ids"]


def test_every_scope_type_is_usable_end_to_end(store):
    """All six contract scopes work as a request scope, not just the legacy four."""
    scopes = [
        Scope.global_vorquel(),
        Scope("VERTICAL", "imobiliaria"),
        Scope("ENTITY", "chaves-hugo"),
        Scope("CLIENT", "jacqueline"),
        Scope("PROJECT", "proj-a"),
        Scope("PRIVATE_TEST", "sandbox"),
    ]
    for scope in scopes:
        result = search_evidence(store, "diagnostico", scope)
        # Some scopes hold nothing; what matters is that none of them raises and
        # each returns a well-formed answer, absence included.
        assert result.scope == scope
        assert (result.hits and result.absence is None) or (
            not result.hits and result.absence is not None
        )


def test_a_pack_is_json_serialisable_and_carries_no_executable_reference(store, chaves):
    from vorquel_brain_contract import check_no_forbidden_fields

    pack = get_context_pack(store, "diagnostico", chaves, entity_ids=("ent_chaves_hugo",)).pack
    json.dumps(pack)
    assert check_no_forbidden_fields(pack) == []
