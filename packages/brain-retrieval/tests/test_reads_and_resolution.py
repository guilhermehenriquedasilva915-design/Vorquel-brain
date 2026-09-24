"""Unit behaviour of the five non-pack reads, and of the scope guard beneath them."""

from __future__ import annotations

import pytest

from vorquel_brain_retrieval import (
    Absence,
    AmbiguousEntityError,
    Scope,
    ScopeError,
    get_delta,
    get_entity,
    get_state,
    resolve_entity,
    search_evidence,
)
from vorquel_brain_retrieval.reads import Delta
from vorquel_brain_retrieval.scope import ScopeGuard

# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


def test_the_six_contract_scopes_are_constructible():
    for scope_type, scope_id in (
        ("GLOBAL_VORQUEL", "GLOBAL"),
        ("VERTICAL", "imobiliaria"),
        ("ENTITY", "chaves-hugo"),
        ("CLIENT", "jacqueline"),
        ("PROJECT", "proj-a"),
        ("PRIVATE_TEST", "sandbox"),
    ):
        assert str(Scope(scope_type, scope_id))


@pytest.mark.parametrize(
    "bad",
    [
        ("COMPANY", "x"),
        ("ENTITY", "GLOBAL"),
        ("GLOBAL_VORQUEL", "not-global"),
        ("CLIENT", "has spaces"),
        ("", "x"),
    ],
)
def test_malformed_scopes_fail_closed(bad):
    with pytest.raises(ScopeError):
        Scope(*bad)


def test_a_guard_sees_its_own_scope_and_global_and_nothing_else():
    guard = ScopeGuard(requested=Scope("CLIENT", "jacqueline"))
    assert guard.visible_scopes() == (Scope.global_vorquel(), Scope("CLIENT", "jacqueline"))
    assert not guard.admits_scope(Scope("CLIENT", "clinica"))
    assert not guard.admits_scope(Scope("VERTICAL", "imobiliaria"))


def test_there_is_no_vertical_inheritance():
    """A client does not see its vertical, and a vertical does not see its clients."""
    client = ScopeGuard(requested=Scope("CLIENT", "chaves"))
    vertical = ScopeGuard(requested=Scope("VERTICAL", "imobiliaria"))
    assert not client.admits_scope(Scope("VERTICAL", "imobiliaria"))
    assert not vertical.admits_scope(Scope("CLIENT", "chaves"))


def test_an_object_with_no_readable_scope_is_not_admitted():
    """Absence of a scope is not permission."""
    guard = ScopeGuard(requested=Scope("CLIENT", "jacqueline"))
    assert not guard.admits({})
    assert not guard.admits({"scope": "CLIENT:jacqueline"})
    assert not guard.admits({"scope": {"scope_type": "CLIENT"}})


# ---------------------------------------------------------------------------
# resolve_entity
# ---------------------------------------------------------------------------


def test_an_exact_alias_resolves_to_exactly_one_entity(store, chaves):
    resolution = resolve_entity(store, "CH Imoveis", chaves)
    assert resolution.resolved_entity_id == "ent_chaves_hugo"
    assert not resolution.ambiguity
    assert resolution.matches[0].match_kind == "EXACT_ALIAS"


def test_accents_and_punctuation_do_not_prevent_resolution(store, chaves):
    assert resolve_entity(store, "chaves & hugo imoveis", chaves).resolved_entity_id == (
        "ent_chaves_hugo"
    )


def test_an_ambiguous_query_never_picks_silently(store, chaves):
    resolution = resolve_entity(store, "Hugo", chaves)

    assert resolution.ambiguity
    assert resolution.resolved_entity_id is None
    top = [m for m in resolution.matches if m.match_kind == resolution.matches[0].match_kind]
    assert len(top) > 1

    with pytest.raises(AmbiguousEntityError) as excinfo:
        resolution.require_one()
    assert excinfo.value.code == "AMBIGUOUS_ENTITY"


def test_a_clearly_better_match_is_not_ambiguous(store, chaves):
    """An exact hit beside a weak prefix hit is a decision, not a tie."""
    resolution = resolve_entity(store, "Chaves & Hugo Imoveis", chaves)
    assert not resolution.ambiguity
    assert resolution.resolved_entity_id == "ent_chaves_hugo"


def test_match_score_is_a_retrieval_number_not_a_confidence(store, chaves):
    """It grades the string match. Nothing about truth is inferred from it."""
    resolution = resolve_entity(store, "CH Imoveis", chaves)
    match = resolution.matches[0]
    assert 0.0 <= match.match_score <= 1.0
    assert not hasattr(match, "epistemic_status")
    assert not hasattr(match, "confidence")


def test_out_of_scope_entities_are_not_candidates(store, jacqueline):
    assert resolve_entity(store, "Chaves & Hugo Imoveis", jacqueline).matches == ()
    assert resolve_entity(store, "Hugo", jacqueline).matches == ()


def test_an_unmatched_query_is_not_an_error(store, chaves):
    resolution = resolve_entity(store, "zzz nao existe zzz", chaves)
    assert resolution.matches == ()
    assert not resolution.ambiguity
    assert resolution.resolved_entity_id is None


# ---------------------------------------------------------------------------
# get_entity
# ---------------------------------------------------------------------------


def test_get_entity_returns_the_canonical_record(store, chaves):
    view = get_entity(store, "ent_chaves_hugo", chaves)
    assert view.canonical_name == "Chaves & Hugo Imoveis"
    assert view.entity_type == "COMPANY"
    assert view.status == "ACTIVE"
    assert "CH Imoveis" in view.aliases
    assert view.freshness_status in ("FRESH", "STALE", "UNKNOWN_FRESHNESS")


def test_get_entity_exposes_relations_derived_from_claims(store, chaves):
    view = get_entity(store, "ent_chaves_hugo", chaves)
    relations = {r.predicate: r for r in view.relations}
    assert "tem_responsavel" in relations
    relation = relations["tem_responsavel"]
    assert relation.object_entity_id == "ent_hugo_pessoa"
    # A relation is exactly as well-known as the claim asserting it.
    assert relation.epistemic_status == "OBSERVADO"
    assert relation.claim_id == "clm_chaves_responsavel"


def test_missing_denied_and_secret_entities_are_indistinguishable(store, chaves, jacqueline):
    missing = get_entity(store, "ent_nao_existe", chaves)
    denied = get_entity(store, "ent_chaves_hugo", jacqueline)
    secret = get_entity(store, "ent_cofre", Scope("CLIENT", "chaves"))

    for absence in (missing, denied, secret):
        assert isinstance(absence, Absence)
        assert absence.kind == Absence.NOT_FOUND


# ---------------------------------------------------------------------------
# get_state
# ---------------------------------------------------------------------------


def test_get_state_separates_the_parts_of_the_picture(store, chaves):
    state = get_state(store, chaves)
    for key in (
        "current_claim_ids",
        "active_decision_ids",
        "open_hypothesis_ids",
        "open_unknown_ids",
        "conflicts",
        "next_best_learning",
        "freshness_status",
    ):
        assert key in state
    assert state["object_type"] == "StateProjection"
    assert state["derived_from_ids"], "a projection that says nothing derived it is not rebuildable"


def test_a_state_projection_is_derived_not_stored(store, chaves):
    """The stale stored projection is not what ``get_state`` returns."""
    state = get_state(store, chaves)
    assert state["state_projection_id"] != "sp_chaves_antigo"
    assert "dec_chaves_canal_v1" not in state["active_decision_ids"]


def test_open_questions_carry_the_next_thing_worth_learning(store, chaves):
    state = get_state(store, chaves)
    assert state["open_unknown_ids"] == ["unk_chaves_volume"]
    assert "unk_chaves_crm" not in state["open_unknown_ids"]
    assert state["next_best_learning"]


def test_an_empty_scope_returns_an_explicit_absence(store):
    absence = get_state(store, Scope("PROJECT", "nao-existe"), include_global=False)
    assert isinstance(absence, Absence)
    assert absence.kind == Absence.NO_STATE_RECORDED
    assert not absence


def test_get_state_is_deterministic(store, chaves):
    assert get_state(store, chaves) == get_state(store, chaves)


# ---------------------------------------------------------------------------
# get_delta
# ---------------------------------------------------------------------------


def test_delta_reports_what_changed_after_a_point(store, chaves):
    delta = get_delta(store, chaves, since="2026-06-01T00:00:00Z")
    assert "clm_chaves_canal_v2" in delta.new_claim_ids
    assert "clm_chaves_canal_v1" in delta.superseded_claim_ids
    assert "unk_chaves_crm" in delta.resolved_unknown_ids
    assert any(d["decision_id"] == "dec_chaves_canal_v2" for d in delta.decision_changes)


def test_delta_keeps_occurred_at_and_recorded_at_apart(store, chaves):
    """The gap between them is information, and it is surfaced rather than flattened."""
    delta = get_delta(store, chaves, since="2026-01-01T00:00:00Z")
    late = next(e for e in delta.recent_events if e["event_id"] == "evt_chaves_tardio")
    assert late["occurred_at"] != late["recorded_at"]
    assert any("before it was recorded" in note for note in delta.notes)


def test_delta_admits_when_it_cannot_see_far_enough_back(store, chaves):
    """"Not found" is never reported as "did not happen"."""
    delta = get_delta(store, chaves, since="2000-01-01T00:00:00Z")
    assert delta.coverage == Delta.PARTIAL_NO_RECORD_BEFORE
    assert any("not that nothing happened" in note for note in delta.notes)


def test_an_empty_scope_delta_says_no_record_rather_than_no_change(store):
    delta = get_delta(store, Scope("PROJECT", "nao-existe"), include_global=False)
    assert delta.coverage == Delta.NO_RECORD
    assert delta.is_empty()
    assert any("not a statement that nothing happened" in note for note in delta.notes)


# ---------------------------------------------------------------------------
# search_evidence
# ---------------------------------------------------------------------------


def test_every_hit_carries_a_usable_source_pointer(store, chaves):
    found = search_evidence(store, "tempo de resposta", chaves, entity_ids=("ent_chaves_hugo",))
    assert found.hits
    for hit in found.hits:
        assert hit.source_pointers
        for pointer in hit.source_pointers:
            assert pointer["source_id"]
            assert store.by_id("Source", pointer["source_id"]) is not None


def test_retrieval_score_and_epistemic_status_are_separate(store, chaves):
    found = search_evidence(store, "tempo de resposta", chaves, entity_ids=("ent_chaves_hugo",))
    by_id = {h.evidence_id: h for h in found.hits}
    # The strongest match here is MEDIDO and the next is DECLARADO: the score
    # ordering and the epistemic ordering are allowed to disagree, and nothing
    # derives one from the other.
    assert by_id["evd_chaves_medicao"].epistemic_status == "MEDIDO"
    assert by_id["evd_chaves_call"].epistemic_status == "DECLARADO"
    assert by_id["evd_chaves_contra"].epistemic_status == "OBSERVADO"


def test_filters_narrow_without_widening(store, chaves):
    found = search_evidence(
        store,
        "corretor demora responder lead",
        chaves,
        entity_ids=("ent_chaves_hugo",),
        filters={"direction": "CONTRADICTS"},
    )
    assert [h.evidence_id for h in found.hits] == ["evd_chaves_contra"]


def test_the_semantic_stage_is_reported_as_unavailable_not_skipped(store, chaves):
    found = search_evidence(store, "tempo de resposta", chaves)
    assert "SEMANTIC" in found.stages_unavailable
    assert "SEMANTIC" not in found.stages_run
    assert found.stages_run[0] == "SCOPE_FILTER"


def test_results_are_ordered_deterministically(store, chaves):
    first = search_evidence(store, "tempo de resposta", chaves, entity_ids=("ent_chaves_hugo",))
    second = search_evidence(store, "tempo de resposta", chaves, entity_ids=("ent_chaves_hugo",))
    assert [h.evidence_id for h in first.hits] == [h.evidence_id for h in second.hits]
