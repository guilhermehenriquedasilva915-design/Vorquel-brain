"""Structural properties every schema in the contract must hold.

These are the rules about the schemas themselves rather than about any one
object: that all twelve exist, that each carries its own version, that the
security prohibition is real rather than aspirational, and that a payload cannot
smuggle in a field nobody declared.
"""

from __future__ import annotations

import json

import pytest

from vorquel_brain_contract import (
    CONTRACT_VERSION,
    FORBIDDEN_FIELD_NAMES,
    V1_OBJECTS,
    load_all_schemas,
    schema_for,
    structural_errors,
)

SHARED_IDS = {
    "envelope",
    "scope",
    "sensitivity",
    "provenance",
    "locator",
    "temporal",
}


def test_all_twelve_v1_objects_have_schemas() -> None:
    assert len(V1_OBJECTS) == 12
    for object_type in V1_OBJECTS:
        assert schema_for(object_type)["title"] == object_type


def test_shared_types_exist() -> None:
    ids = {uri.rsplit("/", 1)[-1].removesuffix(".schema.json") for uri in load_all_schemas()}
    assert ids >= SHARED_IDS


@pytest.mark.parametrize("object_type", sorted(V1_OBJECTS))
def test_every_schema_is_versioned_in_its_payload(object_type: str) -> None:
    """Versioning is explicit, not inferred from the ``v1/`` directory.

    A schema identified only by where its file sits stops being identifiable the
    moment an object is copied, logged or sent somewhere else.
    """
    schema = schema_for(object_type)
    assert "contract_version" in schema["properties"]
    assert "contract_version" in schema["required"]
    assert schema["$id"].startswith("https://schemas.vorquel/brain/v1/")


@pytest.mark.parametrize("object_type", sorted(V1_OBJECTS))
def test_every_schema_rejects_undeclared_fields(object_type: str) -> None:
    """``additionalProperties: false`` everywhere, so nothing rides along unnoticed."""
    assert schema_for(object_type)["additionalProperties"] is False


@pytest.mark.parametrize("object_type", sorted(V1_OBJECTS))
def test_no_schema_declares_a_forbidden_field(object_type: str) -> None:
    """No Brain object may carry a secret or the means to execute anything."""
    declared = {name.lower() for name in schema_for(object_type)["properties"]}
    offending = declared & FORBIDDEN_FIELD_NAMES
    assert not offending, f"{object_type} declares forbidden field(s): {sorted(offending)}"


def test_context_pack_carries_its_own_version_field() -> None:
    pack = schema_for("ContextPack")
    assert "version" in pack["properties"]
    assert "version" in pack["required"]


def test_context_pack_requires_a_positive_token_budget() -> None:
    budget = schema_for("ContextPack")["properties"]["token_budget"]
    assert budget["type"] == "integer"
    assert budget["minimum"] == 1


def test_context_pack_requires_provenance_summary() -> None:
    """The budget floor: provenance is required, so trimming cannot drop it."""
    assert "provenance_summary" in schema_for("ContextPack")["required"]


def test_provenance_requires_a_source_pointer() -> None:
    """Provenance is a structure, not a sentence: a description cannot be followed."""
    provenance = load_all_schemas()[
        "https://schemas.vorquel/brain/shared/provenance.schema.json"
    ]
    assert provenance["required"] == ["source_id"]
    assert "locator" in provenance["properties"]
    assert "content_hash" in provenance["properties"]


def test_locator_supports_non_textual_media() -> None:
    """Character offsets cannot address a transcript, a frame or an OCR block."""
    kinds = load_all_schemas()["https://schemas.vorquel/brain/shared/locator.schema.json"][
        "properties"
    ]["kind"]["enum"]
    for required in ("TIME_INTERVAL", "FRAME_INDEX", "BBOX", "PAGE_NUMBER", "MESSAGE_ID"):
        assert required in kinds


def test_temporal_type_carries_both_clocks_and_supersession() -> None:
    temporal = load_all_schemas()["https://schemas.vorquel/brain/shared/temporal.schema.json"]
    for field in (
        "occurred_at",
        "recorded_at",
        "valid_from",
        "valid_until",
        "supersedes",
        "superseded_by",
    ):
        assert field in temporal["properties"]


def test_source_defaults_to_no_instruction_authority() -> None:
    """External content is data, never direction."""
    authority = schema_for("Source")["properties"]["instruction_authority"]
    assert authority["default"] == "NONE"
    assert "NONE" in authority["enum"]


def test_global_scope_is_pinned_to_the_global_id() -> None:
    entity = {
        "contract_version": CONTRACT_VERSION,
        "object_type": "Entity",
        "entity_id": "e",
        "entity_type": "COMPANY",
        "canonical_name": "n",
        "aliases": [],
        "scope": {"scope_type": "GLOBAL_VORQUEL", "scope_id": "not-global"},
        "status": "ACTIVE",
        "created_at": "2026-01-01T00:00:00+00:00",
        "last_updated_at": "2026-01-01T00:00:00+00:00",
    }
    assert structural_errors(entity), "GLOBAL_VORQUEL must pin scope_id to GLOBAL"


def test_object_type_mismatch_is_rejected() -> None:
    """A payload that lies about what it is fails against the schema it claims."""
    errors = structural_errors({"object_type": "Entity", "contract_version": "1.0.0"})
    assert errors


def test_schema_files_are_valid_json_and_carry_ids() -> None:
    for uri, body in load_all_schemas().items():
        assert body["$id"] == uri
        assert body["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        json.dumps(body)
