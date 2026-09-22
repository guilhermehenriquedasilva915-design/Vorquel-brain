"""Unit tests for the semantic rules, including the cases the fixtures do not reach.

The fixtures prove the ten scenarios end to end. These prove the edges: that a
rule fires for the right reason, that it stays silent when it should, and that
absence of a field reads as failure rather than as a pass.
"""

from __future__ import annotations

import pytest

from vorquel_brain_contract import (
    CRITICAL,
    NO_EVIDENCE_FOUND,
    SENSITIVITY_LEVELS,
    check_candidate_is_not_canonical,
    check_context_pack_excludes_secret,
    check_context_pack_provenance,
    check_decision_supersession,
    check_epistemic_promotion,
    check_epistemic_provenance,
    check_no_evidence_not_false,
    check_no_forbidden_fields,
    check_pii_orthogonality,
    check_scope_isolation,
)


def codes(violations) -> set[str]:
    return {v.code for v in violations}


# --- provenance -----------------------------------------------------------


def test_medido_without_any_pointer_fails() -> None:
    assert codes(check_epistemic_provenance({"epistemic_status": "MEDIDO"})) == {
        "EPISTEMIC_PROVENANCE_REQUIRED"
    }


def test_observado_without_any_pointer_fails() -> None:
    assert codes(check_epistemic_provenance({"epistemic_status": "OBSERVADO"})) == {
        "EPISTEMIC_PROVENANCE_REQUIRED"
    }


def test_empty_source_list_is_not_provenance() -> None:
    """An empty list is 'nobody recorded one', which is the failure, not a pass."""
    assert check_epistemic_provenance({"epistemic_status": "MEDIDO", "source_ids": []})


def test_provenance_entry_without_source_id_is_not_provenance() -> None:
    """A pointer to nothing is not a pointer."""
    assert check_epistemic_provenance(
        {"epistemic_status": "MEDIDO", "provenance": [{"locator": {"kind": "PAGE_NUMBER"}}]}
    )


def test_inferido_needs_no_source() -> None:
    """Seven of the nine statuses may stand on reasoning, and say so by name."""
    assert check_epistemic_provenance({"epistemic_status": "INFERIDO"}) == []


def test_source_id_alone_satisfies_provenance() -> None:
    assert check_epistemic_provenance({"epistemic_status": "MEDIDO", "source_id": "S1"}) == []


# --- SECRET ---------------------------------------------------------------


def test_pack_may_not_be_secret_itself() -> None:
    violations = check_context_pack_excludes_secret(
        {"context_pack_id": "P", "sensitivity_level": "SECRET"}
    )
    assert codes(violations) == {"SECRET_IN_CONTEXT_PACK"}
    assert violations[0].severity == CRITICAL


def test_internal_pack_carrying_a_secret_object_still_fails() -> None:
    """Labelling the pack INTERNAL does not un-leak the secret inside it."""
    pack = {"context_pack_id": "P", "sensitivity_level": "INTERNAL", "evidence_ids": ["E"]}
    objects = {"E": {"sensitivity": {"sensitivity_level": "SECRET"}}}
    assert codes(check_context_pack_excludes_secret(pack, objects)) == {
        "SECRET_IN_CONTEXT_PACK"
    }


# --- PII ------------------------------------------------------------------


@pytest.mark.parametrize("level", SENSITIVITY_LEVELS)
@pytest.mark.parametrize("classes", [[], ["PII"]], ids=["without-pii", "with-pii"])
def test_every_tier_is_representable_with_and_without_pii(level: str, classes: list) -> None:
    """The whole of DIV-2 in one matrix: ten combinations, none of them a violation.

    The axes are independent, so every tier has to survive both states of the
    data-class axis — including ``SECRET`` with ``PII``, which an earlier version
    of this validator rejected. It had no way to be satisfied: the escape hatch
    it demanded was a field the schemas forbid, so a schema-valid object was
    permanently invalid. Co-occurrence was never evidence of promotion anyway.
    """
    obj = {"claim_id": "C", "sensitivity_level": level, "data_classes": classes}
    assert check_pii_orthogonality(obj) == []


def test_secret_with_pii_is_a_representable_object() -> None:
    """Stated on its own, because this is the case the old rule made impossible.

    An object may be SECRET for a reason that has nothing to do with the personal
    data it happens to contain. Storing it is fine. What is forbidden is a
    separate rule with a separate check: it may not enter a ContextPack.
    """
    obj = {"claim_id": "C", "sensitivity_level": "SECRET", "data_classes": ["PII"]}
    assert check_pii_orthogonality(obj) == []


def test_secret_with_pii_still_cannot_enter_a_context_pack() -> None:
    """Relaxing the orthogonality rule must not relax the ContextPack rule."""
    pack = {"context_pack_id": "P", "sensitivity_level": "INTERNAL", "claim_ids": ["C"]}
    objects = {"C": {"sensitivity_level": "SECRET", "data_classes": ["PII"]}}
    violations = check_context_pack_excludes_secret(pack, objects)
    assert codes(violations) == {"SECRET_IN_CONTEXT_PACK"}
    assert violations[0].severity == CRITICAL


def test_a_tier_used_as_a_data_class_is_rejected() -> None:
    """The axes may not be conflated in either direction."""
    obj = {"claim_id": "C", "sensitivity_level": "INTERNAL", "data_classes": ["SECRET"]}
    assert codes(check_pii_orthogonality(obj)) == {"SENSITIVITY_AXIS_CONFLATED"}


def test_a_data_class_used_as_a_tier_is_rejected() -> None:
    obj = {"claim_id": "C", "sensitivity_level": "PII", "data_classes": []}
    assert codes(check_pii_orthogonality(obj)) == {"SENSITIVITY_AXIS_CONFLATED"}


def test_malformed_data_classes_is_rejected() -> None:
    obj = {"claim_id": "C", "sensitivity_level": "INTERNAL", "data_classes": "PII"}
    assert codes(check_pii_orthogonality(obj)) == {"DATA_CLASSES_MALFORMED"}


def test_nested_sensitivity_block_is_read_too() -> None:
    """Objects carry sensitivity either flat or under a `sensitivity` key."""
    obj = {"claim_id": "C", "sensitivity": {"sensitivity_level": "PII", "data_classes": []}}
    assert codes(check_pii_orthogonality(obj)) == {"SENSITIVITY_AXIS_CONFLATED"}


# --- supersession ---------------------------------------------------------


def test_superseded_decision_may_not_stay_active() -> None:
    decisions = [
        {"decision_id": "OLD", "status": "ACTIVE", "superseded_by": "NEW"},
        {"decision_id": "NEW", "status": "ACTIVE", "supersedes": "OLD"},
    ]
    assert "SUPERSEDED_DECISION_STILL_ACTIVE" in codes(check_decision_supersession(decisions))


def test_correct_supersession_is_silent() -> None:
    decisions = [
        {"decision_id": "OLD", "status": "SUPERSEDED", "superseded_by": "NEW"},
        {"decision_id": "NEW", "status": "ACTIVE", "supersedes": "OLD"},
    ]
    assert check_decision_supersession(decisions) == []


def test_superseding_a_missing_decision_is_reported() -> None:
    decisions = [{"decision_id": "NEW", "status": "ACTIVE", "supersedes": "GONE"}]
    assert codes(check_decision_supersession(decisions)) == {"SUPERSEDES_BROKEN_REFERENCE"}


def test_superseded_is_not_invalidated() -> None:
    """A replaced decision is not a wrong one, and must not be deleted."""
    decisions = [
        {"decision_id": "OLD", "status": "SUPERSEDED", "superseded_by": "NEW"},
        {"decision_id": "NEW", "status": "ACTIVE", "supersedes": "OLD"},
    ]
    assert check_decision_supersession(decisions) == []
    assert any(d["decision_id"] == "OLD" for d in decisions)


# --- epistemic promotion --------------------------------------------------


def test_inferido_may_not_become_medido() -> None:
    assert codes(check_epistemic_promotion("INFERIDO", "MEDIDO")) == {
        "INVALID_EPISTEMIC_PROMOTION"
    }


def test_declarado_may_not_become_observado() -> None:
    assert check_epistemic_promotion("DECLARADO", "OBSERVADO")


def test_hipotese_may_not_become_observado() -> None:
    assert check_epistemic_promotion("HIPOTESE", "OBSERVADO")


def test_demotion_is_always_allowed() -> None:
    """Learning that you knew less is never the dangerous direction."""
    assert check_epistemic_promotion("MEDIDO", "INFERIDO") == []
    assert check_epistemic_promotion("OBSERVADO", "CONFLITANTE") == []


def test_unchanged_status_is_not_a_promotion() -> None:
    assert check_epistemic_promotion("MEDIDO", "MEDIDO") == []


def test_pending_candidate_may_not_propose_unsourced_observation() -> None:
    candidate = {
        "candidate_id": "K",
        "status": "PENDING",
        "proposed_epistemic_status": "MEDIDO",
    }
    assert codes(check_candidate_is_not_canonical(candidate)) == {
        "CANDIDATE_PROPOSES_UNSOURCED_OBSERVATION"
    }


# --- scope ----------------------------------------------------------------


def _pack(scope_type, scope_id, **kwargs):
    return {
        "context_pack_id": "P",
        "scope": {"scope_type": scope_type, "scope_id": scope_id},
        **kwargs,
    }


def test_cross_client_reference_is_critical() -> None:
    pack = _pack("CLIENT", "a", evidence_ids=["E"])
    objects = {"E": {"entity_scope": {"scope_type": "CLIENT", "scope_id": "b"}}}
    violations = check_scope_isolation(pack, objects)
    assert codes(violations) == {"CROSS_CLIENT_REFERENCE"}
    assert violations[0].severity == CRITICAL


def test_cross_vertical_reference_is_an_error() -> None:
    pack = _pack("VERTICAL", "clinic", claim_ids=["C"])
    objects = {"C": {"scope": {"scope_type": "VERTICAL", "scope_id": "real-estate"}}}
    assert codes(check_scope_isolation(pack, objects)) == {"CROSS_SCOPE_REFERENCE"}


def test_global_knowledge_reaches_every_scope() -> None:
    """Methodology is meant to apply everywhere; that is not a leak."""
    pack = _pack("CLIENT", "a", decision_ids=["D"])
    objects = {"D": {"scope": {"scope_type": "GLOBAL_VORQUEL", "scope_id": "GLOBAL"}}}
    assert check_scope_isolation(pack, objects) == []


def test_a_pack_without_scope_cannot_be_cleared() -> None:
    """Absence of scope is failure, not permission."""
    violations = check_scope_isolation({"context_pack_id": "P"}, {})
    assert codes(violations) == {"PACK_SCOPE_MISSING"}
    assert violations[0].severity == CRITICAL


# --- NO_EVIDENCE_FOUND ----------------------------------------------------


def test_desconhecido_with_false_is_critical() -> None:
    violations = check_no_evidence_not_false(
        {"claim_id": "C", "epistemic_status": "DESCONHECIDO", "object_value": False}
    )
    assert codes(violations) == {"NO_EVIDENCE_SERIALIZED_AS_FALSE"}
    assert violations[0].severity == CRITICAL


def test_marker_must_be_labelled_desconhecido() -> None:
    violations = check_no_evidence_not_false(
        {"claim_id": "C", "epistemic_status": "OBSERVADO", "object_value": NO_EVIDENCE_FOUND}
    )
    assert codes(violations) == {"NO_EVIDENCE_FOUND_MISLABELLED"}


def test_correct_absence_is_silent() -> None:
    assert (
        check_no_evidence_not_false(
            {
                "claim_id": "C",
                "epistemic_status": "DESCONHECIDO",
                "object_value": NO_EVIDENCE_FOUND,
            }
        )
        == []
    )


def test_a_genuine_false_finding_is_allowed() -> None:
    """A measured negative is a real result and must stay expressible."""
    assert (
        check_no_evidence_not_false(
            {"claim_id": "C", "epistemic_status": "MEDIDO", "object_value": False}
        )
        == []
    )


# --- pack provenance ------------------------------------------------------


def test_included_evidence_needs_a_provenance_entry() -> None:
    pack = {"context_pack_id": "P", "evidence_ids": ["E"], "provenance_summary": []}
    assert codes(check_context_pack_provenance(pack)) == {"CONTEXT_PACK_MISSING_PROVENANCE"}


def test_empty_provenance_entry_is_rejected() -> None:
    pack = {
        "context_pack_id": "P",
        "evidence_ids": ["E"],
        "provenance_summary": [{"object_id": "E", "object_type": "Evidence", "provenance": []}],
    }
    assert codes(check_context_pack_provenance(pack)) == {"CONTEXT_PACK_EMPTY_PROVENANCE_ENTRY"}


def test_decisions_need_no_provenance_entry() -> None:
    """Decisions describe the Brain's own posture; they assert nothing about the world."""
    pack = {"context_pack_id": "P", "decision_ids": ["D"], "provenance_summary": []}
    assert check_context_pack_provenance(pack) == []


# --- security -------------------------------------------------------------


def test_a_nested_token_is_still_found() -> None:
    obj = {"claim_id": "C", "metadata": {"nested": {"api_key": "x"}}}
    violations = check_no_forbidden_fields(obj)
    assert codes(violations) == {"FORBIDDEN_FIELD"}
    assert violations[0].severity == CRITICAL


def test_a_token_inside_a_list_is_still_found() -> None:
    obj = {"claim_id": "C", "metadata": {"items": [{"dsn": "postgres://"}]}}
    assert codes(check_no_forbidden_fields(obj)) == {"FORBIDDEN_FIELD"}


def test_an_ordinary_object_is_clean() -> None:
    assert check_no_forbidden_fields({"claim_id": "C", "metadata": {"note": "fine"}}) == []
