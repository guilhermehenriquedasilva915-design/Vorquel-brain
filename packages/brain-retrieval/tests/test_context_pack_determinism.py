"""The ContextPack is reproducible, versioned and schema-valid.

Determinism is the property that makes a pack citable. If the same question
against the same facts produced a different pack each time, no pack id would
mean anything, no eval could pin behaviour, and "the model saw this context"
would be unverifiable after the fact.
"""

from __future__ import annotations

import json

import pytest
from vorquel_brain_contract import (
    CONTEXT_PACK_MODES,
    CONTRACT_VERSION,
    check_context_pack_provenance,
    check_gaps_are_not_findings,
    structural_errors,
)

from vorquel_brain_retrieval import (
    CONTEXT_PACK_VERSION,
    InMemoryBrainStore,
    get_context_pack,
)
from vorquel_brain_retrieval.store import COLLECTIONS

ARGS = dict(
    mode="OPERATIONAL",
    token_budget=8000,
    entity_ids=("ent_chaves_hugo",),
    requirements=("skill:diagnostico",),
)


def pack_for(store, scope, **overrides):
    return get_context_pack(
        store, "reduzir tempo de resposta ao lead", scope, **{**ARGS, **overrides}
    ).pack


def test_the_same_inputs_produce_a_byte_identical_pack(store, chaves):
    first = pack_for(store, chaves)
    second = pack_for(store, chaves)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["context_pack_id"] == second["context_pack_id"]


def test_generated_at_does_not_change_the_identity(store, chaves):
    """Two packs from the same facts are the same pack, whenever they were built.

    This is the rule that makes reproducibility testable at all: if the clock
    were part of the identity, every regeneration would look like new context.
    """
    early = pack_for(store, chaves, generated_at="2020-01-01T00:00:00Z")
    late = pack_for(store, chaves, generated_at="2099-12-31T23:59:59Z")

    assert early["generated_at"] != late["generated_at"]
    assert early["context_pack_id"] == late["context_pack_id"]


def test_nothing_reads_the_wall_clock(store, chaves):
    """The default ``generated_at`` comes from the data, not from today."""
    pack = pack_for(store, chaves)
    assert pack["generated_at"] == "2026-07-15T10:00:00Z"


def test_a_different_world_produces_a_different_pack_id(store, chaves):
    payload = {key: list(store.all_of(object_type)) for object_type, key in COLLECTIONS.items()}
    payload["unknowns"] = [
        *payload["unknowns"],
        {
            "contract_version": CONTRACT_VERSION,
            "object_type": "Unknown",
            "unknown_id": "unk_extra",
            "entity_scope": chaves.as_mapping(),
            "statement": "algo mais que nao sabemos",
            "priority": "LOW",
            "status": "OPEN",
            "related_hypothesis_ids": [],
            "related_question_ids": [],
            "created_at": "2026-05-10T10:00:00Z",
            "last_updated_at": "2026-05-10T10:00:00Z",
        },
    ]
    variant = InMemoryBrainStore.from_mapping(payload)

    assert store.fingerprint() != variant.fingerprint()
    assert pack_for(store, chaves)["context_pack_id"] != pack_for(variant, chaves)[
        "context_pack_id"
    ]


@pytest.mark.parametrize(
    "changed",
    [
        {"mode": "AUDIT"},
        {"token_budget": 7999},
        {"requirements": ("skill:outro",)},
        {"entity_ids": ()},
    ],
)
def test_every_input_participates_in_the_identity(store, chaves, changed):
    assert pack_for(store, chaves)["context_pack_id"] != pack_for(store, chaves, **changed)[
        "context_pack_id"
    ]


def test_ordering_is_total_and_stable(store, chaves):
    pack = pack_for(store, chaves)
    for key in (
        "entity_ids",
        "claim_ids",
        "evidence_ids",
        "decision_ids",
        "hypothesis_ids",
        "unknown_ids",
        "gaps",
        "constraints",
        "procedural_refs",
    ):
        assert pack[key] == sorted(pack[key]), f"{key} is not sorted"
    provenance_ids = [entry["object_id"] for entry in pack["provenance_summary"]]
    assert provenance_ids == sorted(provenance_ids)


@pytest.mark.parametrize("mode", CONTEXT_PACK_MODES)
def test_every_mode_produces_a_valid_versioned_pack(store, chaves, mode):
    pack = pack_for(store, chaves, mode=mode)

    assert structural_errors(pack) == []
    assert pack["object_type"] == "ContextPack"
    assert pack["contract_version"] == CONTRACT_VERSION
    assert pack["version"] == CONTEXT_PACK_VERSION
    assert pack["mode"] == mode
    assert pack["context_pack_id"].startswith("cp_")
    assert check_gaps_are_not_findings(pack) == []


def test_every_asserting_object_in_the_pack_carries_provenance(store, chaves):
    pack = pack_for(store, chaves)
    objects_by_id = {
        str(obj[key]): obj
        for object_type, key in (("Claim", "claim_id"), ("Evidence", "evidence_id"))
        for obj in store.all_of(object_type)
    }
    assert check_context_pack_provenance(pack, objects_by_id) == []
    assert pack["provenance_summary"], "a pack with claims carried no provenance at all"


def test_an_unknown_mode_is_refused(store, chaves):
    with pytest.raises(ValueError, match="unknown mode"):
        pack_for(store, chaves, mode="TELEPATHY")
