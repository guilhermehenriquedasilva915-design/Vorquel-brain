"""Scope travels with the material, and a locator stays an address."""

from __future__ import annotations

import pytest

from vorquel_n8n_brain_learn.adapters import learn_message
from vorquel_n8n_brain_learn.model import Candidate, LearnError, SourceRef, validate_locator
from vorquel_n8n_brain_learn.scope_util import ScopeError, resolve_scope

LONG = "Este paragrafo tem conteudo suficiente para virar um candidato citavel."


def test_client_material_is_never_quietly_global() -> None:
    batch = learn_message(LONG, "CLIENT:acme", "CLIENT_CONFIDENTIAL")

    assert batch.source.scope.scope_type == "CLIENT"
    assert batch.source.scope.scope_id == "acme"
    assert str(batch.source.scope) == "CLIENT:acme"
    assert batch.source.data_classification == "CLIENT_CONFIDENTIAL"
    assert all(
        candidate.data_classification == "CLIENT_CONFIDENTIAL" for candidate in batch.candidates
    )


@pytest.mark.parametrize(
    "raw",
    [
        "CLIENT:GLOBAL",  # GLOBAL is reserved for GLOBAL_VORQUEL
        "GLOBAL_VORQUEL:acme",  # ...and GLOBAL_VORQUEL may not be narrowed
        "EVERYONE:all",
        "CLIENT:acme; drop table",
        "CLIENT:",
    ],
)
def test_a_malformed_scope_fails_closed(raw: str) -> None:
    with pytest.raises(ScopeError):
        resolve_scope(raw)


def test_a_scope_error_stops_learning_before_anything_is_extracted() -> None:
    with pytest.raises(ScopeError):
        learn_message(LONG, "CLIENT:GLOBAL")


def test_secret_is_not_a_classification_a_source_can_carry() -> None:
    with pytest.raises(LearnError, match="SECRET"):
        SourceRef(
            source_kind="TEXT",
            content_sha256="a" * 64,
            byte_size=1,
            detected_mime="text/plain",
            scope=resolve_scope("GLOBAL_VORQUEL"),
            data_classification="SECRET",
        )


@pytest.mark.parametrize(
    "locator",
    [
        {"token": "abc"},
        {"password": "x"},
        {"command": "rm -rf /"},
        {"sql": "select 1"},
        {"payload": "..."},
        {"body": "..."},
    ],
)
def test_a_locator_may_not_carry_a_payload(locator: dict) -> None:
    # If the address needed one of these keys, the excerpt is wrong.
    with pytest.raises(LearnError, match="payload-shaped"):
        validate_locator("REPO_FILE", locator)


def test_an_unknown_locator_kind_is_refused() -> None:
    with pytest.raises(LearnError, match="locator_kind"):
        validate_locator("ARBITRARY", {"path": "README.md"})


def test_the_same_excerpt_from_a_different_place_is_a_different_candidate() -> None:
    def build(page: int) -> Candidate:
        return Candidate(
            title="Retry",
            summary=LONG,
            knowledge_type="PROCEDURE",
            epistemic_status="DECLARADO",
            locator_kind="PDF_PAGE",
            locator={"page": page},
        )

    assert build(1).content_hash != build(2).content_hash
    assert build(1).candidate_id == build(1).candidate_id


def test_provenance_addresses_exactly_one_place_in_the_source() -> None:
    candidate = Candidate(
        title="Retry",
        summary=LONG,
        knowledge_type="PROCEDURE",
        epistemic_status="DECLARADO",
        locator_kind="PDF_PAGE",
        locator={"page": 12},
    )

    provenance = candidate.provenance()
    assert len(provenance) == 1
    assert provenance[0]["locator_kind"] == "PDF_PAGE"
    assert provenance[0]["locator"] == {"page": 12}
    assert provenance[0]["knowledge_source_id"].startswith("ksr_")


def test_measured_is_not_a_status_a_document_can_claim_for_itself() -> None:
    # Adapters that read a document assert DECLARADO. MEDIDO has to be earned
    # by measuring one of our own runs, which LEARN never does.
    batch = learn_message(LONG, "GLOBAL_VORQUEL")
    assert {candidate.epistemic_status for candidate in batch.candidates} == {"DECLARADO"}
