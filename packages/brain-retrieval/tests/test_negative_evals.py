"""The negative evals, run against the real retrieval path and the real generator.

In Brain-V1-A these were JSON fixtures checked against validators. Here each one
calls the function a consumer would call and asserts on what actually comes
back. That is the difference between a rule being stated and a rule being
enforced: a validator proves a malformed object is rejected, and these prove the
system does not produce one in the first place.

Every test is named for the case it defends, so a failure reports which
guarantee broke rather than which assertion did.
"""

from __future__ import annotations

import json

import pytest
from vorquel_brain_contract import (
    NO_EVIDENCE_FOUND,
    check_context_pack_excludes_secret,
    check_no_evidence_not_false,
)

from vorquel_brain_retrieval import (
    NON_DROPPABLE,
    Absence,
    BudgetTooSmallError,
    Scope,
    detect_promotion,
    get_context_pack,
    get_entity,
    get_state,
    resolve_entity,
    search_evidence,
)

# ---------------------------------------------------------------------------
# A. Generic content does not become entity-specific evidence
# ---------------------------------------------------------------------------


def test_a_generic_content_is_never_attributed_to_the_entity(store, chaves):
    """Hugo's generic marketing message must not become evidence about Chaves.

    The message mentions lead response time, so it *does* match the Chaves query
    lexically — that is the point of the fixture. What must not happen is
    attribution: it stays global, subject-less, and reaches the result only
    through the lexical stage, never the relational one.
    """
    found = search_evidence(
        store,
        "tempo de resposta ao lead",
        chaves,
        entity_ids=("ent_chaves_hugo",),
    )
    generic = [h for h in found.hits if h.evidence_id == "evd_hugo_generico"]

    if generic:
        hit = generic[0]
        assert hit.subject_entity_id is None, "generic content acquired a subject entity"
        assert hit.entity_scope.is_global(), "generic content was rescoped to the entity"
        assert "STRUCTURED_RELATIONAL" not in hit.retrieval_stages, (
            "generic content matched as a structured fact about the entity"
        )
        assert hit.retrieval_score < max(
            h.retrieval_score for h in found.hits if h.subject_entity_id == "ent_chaves_hugo"
        ), "generic content outranked real evidence about the entity"

    # And it is not wired into any Chaves claim as support.
    for claim in store.all_of("Claim"):
        if claim.get("subject_entity_id") == "ent_chaves_hugo":
            assert "evd_hugo_generico" not in claim.get("supporting_evidence_ids", [])


# ---------------------------------------------------------------------------
# B. Public research does not become validated operational pain
# ---------------------------------------------------------------------------


def test_b_public_research_stays_inferido_and_hypothetical(store, imobiliaria):
    """Santos's pain came from a public article. It must not read as observed.

    Three separate things have to hold, because dropping any one of them turns
    market research into a customer finding: the evidence stays PUBLIC_RESEARCH
    and INFERIDO, the claim it supports stays INFERIDO, and the whole thing is
    still carried as an open hypothesis rather than as a fact.
    """
    found = search_evidence(store, "atraso no atendimento", imobiliaria, entity_ids=("ent_santos",))
    santos = {h.evidence_id: h for h in found.hits}
    assert "evd_santos_web" in santos

    hit = santos["evd_santos_web"]
    assert hit.evidence_type == "PUBLIC_RESEARCH"
    assert hit.epistemic_status == "INFERIDO"
    assert hit.strength == "WEAK"

    claim = store.by_id("Claim", "clm_santos_hipotese")
    assert claim["epistemic_status"] == "INFERIDO"
    assert claim["predicate"] == "dor_hipotetica"

    state = get_state(store, imobiliaria)
    assert "hyp_santos_dor" in state["open_hypothesis_ids"], (
        "public research stopped being carried as an open question"
    )


def test_b_promoting_public_research_to_measured_is_refused(store):
    """And the promotion that would launder it is caught against stored state."""
    stored = store.by_id("Claim", "clm_santos_hipotese")
    proposal = dict(stored, epistemic_status="MEDIDO")

    finding = detect_promotion(store, proposal)

    assert finding.verdict == finding.FORBIDDEN
    assert finding.before == "INFERIDO"
    assert finding.after == "MEDIDO"
    assert finding.violations
    # Reported, never applied.
    assert store.by_id("Claim", "clm_santos_hipotese")["epistemic_status"] == "INFERIDO"


# ---------------------------------------------------------------------------
# C. Jacqueline never receives Chaves
# ---------------------------------------------------------------------------


def test_c_jacqueline_never_receives_chaves(store, jacqueline):
    """Another client's entity, claims and evidence are all unreachable."""
    assert isinstance(get_entity(store, "ent_chaves_hugo", jacqueline), Absence)

    resolution = resolve_entity(store, "Chaves e Hugo", jacqueline)
    assert resolution.matches == (), "another client's entity was resolvable by name"

    found = search_evidence(store, "tempo de resposta ao lead", jacqueline)
    assert all(not h.evidence_id.startswith("evd_chaves") for h in found.hits)

    state = get_state(store, jacqueline)
    assert all(not c.startswith("clm_chaves") for c in state["current_claim_ids"])

    pack = get_context_pack(
        store, "tempo de resposta ao lead", jacqueline, entity_ids=("ent_jacqueline",)
    ).pack
    serialized = json.dumps(pack)
    for forbidden in ("ent_chaves_hugo", "clm_chaves", "evd_chaves", "src_chaves"):
        assert forbidden not in serialized, f"{forbidden} leaked into Jacqueline's pack"


# ---------------------------------------------------------------------------
# D. The clinic does not receive real-estate context
# ---------------------------------------------------------------------------


def test_d_clinic_never_receives_real_estate_context(store, clinica):
    """No implicit vertical inheritance, in either direction.

    Asserted on ids and on referenced scopes, not on the word "imobiliaria".
    The clinic's own decision says it does not inherit real-estate practice, so
    the word legitimately appears in the pack; matching on it would fail the
    test for containing the rule that makes the test pass.
    """
    pack = get_context_pack(
        store, "confirmacao de agendamento", clinica, entity_ids=("ent_clinica",)
    ).pack

    real_estate_ids = _ids_in_scope(store, Scope("VERTICAL", "imobiliaria")) | _ids_in_scope(
        store, Scope("ENTITY", "chaves-hugo")
    )
    assert real_estate_ids, "the fixture has no real-estate material to leak"

    referenced = _referenced_ids(pack)
    leaked = sorted(referenced & real_estate_ids)
    assert leaked == [], f"real-estate material {leaked} reached the clinic"

    found = search_evidence(store, "atraso no atendimento ao cliente", clinica)
    assert all(h.entity_scope.scope_id != "imobiliaria" for h in found.hits)


def _ids_in_scope(store, scope) -> set[str]:
    return {
        str(obj[key])
        for object_type, key in (
            ("Claim", "claim_id"),
            ("Evidence", "evidence_id"),
            ("Entity", "entity_id"),
            ("Decision", "decision_id"),
            ("Hypothesis", "hypothesis_id"),
            ("Unknown", "unknown_id"),
        )
        for obj in store.all_of(object_type)
        if (obj.get("scope") or obj.get("entity_scope")) == scope.as_mapping()
    }


def _referenced_ids(pack) -> set[str]:
    referenced: set[str] = set(pack["entity_ids"])
    for key in (
        "claim_ids",
        "evidence_ids",
        "decision_ids",
        "hypothesis_ids",
        "unknown_ids",
        "recent_event_ids",
        "state_projection_ids",
    ):
        referenced |= set(pack[key])
    referenced |= {entry["object_id"] for entry in pack["provenance_summary"]}
    referenced |= {c.split(":", 1)[0] for c in pack["constraints"]}
    return referenced


# ---------------------------------------------------------------------------
# E. An old decision never beats the current one
# ---------------------------------------------------------------------------


def test_e_superseded_decision_never_presented_as_active(store, chaves):
    state = get_state(store, chaves)
    assert "dec_chaves_canal_v2" in state["active_decision_ids"]
    assert "dec_chaves_canal_v1" not in state["active_decision_ids"]

    pack = get_context_pack(
        store, "qual canal usar", chaves, entity_ids=("ent_chaves_hugo",)
    ).pack
    assert "dec_chaves_canal_v1" not in pack["decision_ids"]
    assert "dec_chaves_canal_v2" in pack["decision_ids"]

    # The superseded claim goes the same way.
    assert "clm_chaves_canal_v1" not in pack["claim_ids"]
    assert "clm_chaves_canal_v2" in pack["claim_ids"]

    # And the constraint the pack states is the current one, not the old one.
    constraints = " ".join(pack["constraints"])
    assert "whatsapp" in constraints
    assert "telefone" not in constraints


# ---------------------------------------------------------------------------
# F. MEDIDO without a source fails
# ---------------------------------------------------------------------------


def test_f_medido_without_a_source_never_enters_a_pack(store, chaves):
    """An unsourced measurement is dropped and the drop is recorded.

    Built by taking the real measured claim and removing its provenance, so the
    test cannot pass because the object was malformed in some other way.
    """
    raw = json.loads(json.dumps(store._objects))  # noqa: SLF001 - building a variant world
    unsourced = dict(
        store.by_id("Claim", "clm_chaves_tempo"),
        claim_id="clm_sem_fonte",
        source_ids=[],
        provenance=[],
    )
    del raw  # the variant is assembled explicitly below, not patched in place

    from vorquel_brain_retrieval import InMemoryBrainStore
    from vorquel_brain_retrieval.store import COLLECTIONS

    payload = {key: list(store.all_of(object_type)) for object_type, key in COLLECTIONS.items()}
    payload["claims"] = [*payload["claims"], unsourced]
    variant = InMemoryBrainStore.from_mapping(payload)

    result = get_context_pack(
        variant, "tempo de resposta", chaves, entity_ids=("ent_chaves_hugo",)
    )

    assert "clm_sem_fonte" not in result.pack["claim_ids"], (
        "a MEDIDO claim with no source reached the pack"
    )
    assert any("no traceable source" in gap for gap in result.pack["gaps"]), (
        "the exclusion happened silently"
    )
    assert all(entry["provenance"] for entry in result.pack["provenance_summary"])


def test_f_promotion_into_medido_without_a_source_is_refused(store):
    stored = store.by_id("Claim", "clm_chaves_dor")
    proposal = dict(stored, epistemic_status="MEDIDO", source_ids=[], provenance=[])

    finding = detect_promotion(store, proposal)

    assert finding.verdict == finding.FORBIDDEN
    assert finding.violations


# ---------------------------------------------------------------------------
# G. SECRET never appears
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["OPERATIONAL", "RESEARCH", "BUILD", "AUDIT", "STRATEGY"])
def test_g_secret_never_enters_a_pack_in_any_mode(store, chaves_client, mode):
    result = get_context_pack(store, "credenciais", chaves_client, mode=mode, token_budget=8000)
    pack = result.pack
    serialized = json.dumps(pack)

    for secret_id in ("ent_cofre", "clm_secreto", "evd_secreto"):
        assert secret_id not in serialized, f"{secret_id} reached a {mode} pack"
    assert pack["sensitivity_level"] != "SECRET"

    # The contract's own check agrees. It is given the whole world by id, so it
    # would catch a SECRET object that the pack referenced through any field —
    # not just the three this test names.
    everything = {
        str(obj[key]): obj
        for object_type, key in (
            ("Claim", "claim_id"),
            ("Evidence", "evidence_id"),
            ("Entity", "entity_id"),
            ("Decision", "decision_id"),
            ("Source", "source_id"),
        )
        for obj in store.all_of(object_type)
    }
    assert check_context_pack_excludes_secret(pack, everything) == []

    # Withholding is stated rather than silent.
    assert any("SECRET" in gap for gap in pack["gaps"])


def test_g_secret_is_not_resolvable_readable_or_searchable(store, chaves_client):
    assert resolve_entity(store, "Cofre de Credenciais", chaves_client).matches == ()
    assert isinstance(get_entity(store, "ent_cofre", chaves_client), Absence)
    found = search_evidence(store, "credencial ativa", chaves_client)
    assert all(h.evidence_id != "evd_secreto" for h in found.hits)


# ---------------------------------------------------------------------------
# H. NO_EVIDENCE_FOUND is not FALSE
# ---------------------------------------------------------------------------


def test_h_no_evidence_found_is_an_absence_not_a_negative_finding(store, chaves):
    found = search_evidence(store, "zzz nenhuma correspondencia possivel zzz", chaves)

    assert found.hits == ()
    assert found.absence is not None
    assert found.absence.kind == NO_EVIDENCE_FOUND
    # Falsy for control flow, and emphatically not the boolean False.
    assert not found.absence
    assert found.absence is not False
    assert found.absence.as_dict()["absence"] == NO_EVIDENCE_FOUND

    pack = get_context_pack(
        store, "zzz nenhuma correspondencia possivel zzz", chaves
    ).pack

    # The absence is reported as a gap, spelled with the contract's own marker.
    assert any(NO_EVIDENCE_FOUND in gap for gap in pack["gaps"])
    # A gap is a string saying what is missing. It is never a boolean, and the
    # gap list never becomes a place where `false` is asserted about the world.
    assert all(isinstance(gap, str) for gap in pack["gaps"])
    assert not any(value is False for value in pack.values())
    # Nothing was invented to fill the hole.
    assert pack["evidence_ids"] == []

    # The contract's own rule, applied to a claim serialised from an absence.
    serialised_wrongly = {"object_value": False, "epistemic_status": "DESCONHECIDO"}
    assert check_no_evidence_not_false(serialised_wrongly), (
        "the contract no longer catches an absence written as False"
    )


# ---------------------------------------------------------------------------
# I. Token budget trimming preserves provenance
# ---------------------------------------------------------------------------


def test_i_trimming_never_drops_provenance_or_the_core(store, chaves):
    budgets = [8000, 2000, 1000, 820, 800, 780, 760, 740]
    issued = 0

    for budget in budgets:
        try:
            result = get_context_pack(
                store,
                "reduzir tempo de resposta ao lead",
                chaves,
                mode="AUDIT",
                token_budget=budget,
                entity_ids=("ent_chaves_hugo",),
                requirements=("skill:a", "skill:b", "skill:c"),
            )
        except BudgetTooSmallError:
            continue
        issued += 1
        pack = result.pack

        assert result.estimated_tokens <= budget, "an issued pack exceeded its own budget"
        for field in NON_DROPPABLE:
            assert field in pack, f"{field} was dropped at budget {budget}"

        kept = set(pack["claim_ids"]) | set(pack["evidence_ids"])
        traced = {entry["object_id"] for entry in pack["provenance_summary"]}
        assert kept <= traced, f"items at budget {budget} lost their provenance"
        assert traced <= kept, f"provenance at budget {budget} outlived its item"
        assert all(entry["provenance"] for entry in pack["provenance_summary"])

    assert issued >= 3, "the budget sweep did not actually issue trimmed packs"


def test_i_a_budget_too_small_refuses_instead_of_mutilating(store, chaves):
    with pytest.raises(BudgetTooSmallError) as excinfo:
        get_context_pack(
            store,
            "reduzir tempo de resposta ao lead",
            chaves,
            mode="AUDIT",
            token_budget=10,
            entity_ids=("ent_chaves_hugo",),
        )

    error = excinfo.value
    assert error.code == "BUDGET_TOO_SMALL"
    assert error.requested == 10
    assert error.minimum_required > 10
    assert "No pack was generated" in str(error)


# ---------------------------------------------------------------------------
# J. Client A and Client B: zero leakage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("owner", "intruder"),
    [
        (Scope("CLIENT", "jacqueline"), Scope("CLIENT", "clinica")),
        (Scope("CLIENT", "clinica"), Scope("CLIENT", "jacqueline")),
        (Scope("CLIENT", "jacqueline"), Scope("ENTITY", "chaves-hugo")),
        (Scope("CLIENT", "chaves"), Scope("CLIENT", "jacqueline")),
    ],
)
def test_j_no_client_sees_another(store, owner, intruder):
    """Whatever is in one scope is invisible from the other, both ways."""
    owner_ids = {
        str(obj[key])
        for object_type, key in (
            ("Claim", "claim_id"),
            ("Evidence", "evidence_id"),
            ("Entity", "entity_id"),
            ("Decision", "decision_id"),
        )
        for obj in store.all_of(object_type)
        if (obj.get("scope") or obj.get("entity_scope")) == owner.as_mapping()
    }
    assert owner_ids, "the fixture has nothing in the owning scope to leak"

    pack = get_context_pack(store, "dor operacional processo cliente", intruder).pack
    serialized = json.dumps(pack)
    leaked = sorted(i for i in owner_ids if i in serialized)
    assert leaked == [], f"{intruder} saw {leaked} belonging to {owner}"
