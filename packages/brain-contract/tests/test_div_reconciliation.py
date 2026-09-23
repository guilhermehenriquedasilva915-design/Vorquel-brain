"""The four reconciliation decisions, asserted rather than described.

``docs/BRAIN_CONTRACT_V1_RECONCILIATION.md`` records DIV-1 through DIV-4. A
document can drift from the code silently; these tests cannot. If someone later
adds a ninth tool, folds PII back into the sensitivity tier, quietly migrates
storage or reintroduces the accented status, the build says so.
"""

from __future__ import annotations

import json
from pathlib import Path

from vorquel_brain_contract import (
    BRAIN_V1_CONTROLLED_WRITES,
    BRAIN_V1_READS,
    BRAIN_V1_TOOLS,
    DATA_CLASSES,
    EPISTEMIC_STATUS_DISPLAY,
    EPISTEMIC_STATUSES,
    FRESHNESS_STATUSES,
    LEGACY_STORAGE_SCOPE_TYPES,
    SCOPE_TYPES,
    SCOPES_AWAITING_STORAGE_MIGRATION,
    SENSITIVITY_LEVELS,
    STORAGE_SCOPE_TYPES,
    VERIFICATION_STATES,
    display_epistemic_status,
    load_all_schemas,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


# --- DIV-1 ----------------------------------------------------------------


def test_contract_is_eight_tools() -> None:
    assert len(BRAIN_V1_READS) == 6
    assert len(BRAIN_V1_CONTROLLED_WRITES) == 2
    assert len(BRAIN_V1_TOOLS) == 8


def test_get_entity_is_in_the_contract() -> None:
    """DIV-1's whole content. The seven-interface list was the outlier."""
    assert "get_entity" in BRAIN_V1_READS


def test_reads_and_writes_do_not_overlap() -> None:
    assert not set(BRAIN_V1_READS) & set(BRAIN_V1_CONTROLLED_WRITES)


def test_this_package_implements_no_tools() -> None:
    """Brain-V1-A defines the contract and implements none of it."""
    import vorquel_brain_contract as contract

    for tool in BRAIN_V1_TOOLS:
        assert not hasattr(contract, tool), f"{tool} must not be implemented in V1-A"


# --- DIV-2 ----------------------------------------------------------------


def test_sensitivity_is_a_five_value_tier() -> None:
    assert SENSITIVITY_LEVELS == (
        "PUBLIC",
        "INTERNAL",
        "CONFIDENTIAL",
        "CLIENT_CONFIDENTIAL",
        "SECRET",
    )


def test_pii_is_a_data_class_and_not_a_sensitivity_level() -> None:
    """The two axes stay apart, which is what keeps public-with-PII representable."""
    assert "PII" in DATA_CLASSES
    assert "PII" not in SENSITIVITY_LEVELS


def test_schemas_keep_the_two_axes_separate() -> None:
    schema = load_all_schemas()["https://schemas.vorquel/brain/shared/sensitivity.schema.json"]
    levels = schema["properties"]["sensitivity_level"]["enum"]
    classes = schema["properties"]["data_classes"]["items"]["enum"]
    assert "PII" not in levels
    assert "PII" in classes
    assert schema["properties"]["data_classes"]["default"] == []


# --- DIV-3 ----------------------------------------------------------------


def test_schema_declares_six_scopes() -> None:
    assert SCOPE_TYPES == (
        "GLOBAL_VORQUEL",
        "VERTICAL",
        "ENTITY",
        "CLIENT",
        "PROJECT",
        "PRIVATE_TEST",
    )
    assert len(SCOPE_TYPES) == 6


def test_company_is_not_a_scope() -> None:
    """A company is an Entity with entity_type=COMPANY, addressed by scope ENTITY."""
    assert "COMPANY" not in SCOPE_TYPES
    entity = load_all_schemas()["https://schemas.vorquel/brain/v1/entity.schema.json"]
    assert "COMPANY" in entity["properties"]["entity_type"]["enum"]


def test_the_storage_gap_is_closed() -> None:
    """DIV-3's recorded gap was closed by Brain-V1-B, and stays closed.

    Brain-V1-A shipped with the contract deliberately two values ahead of
    storage, and an earlier version of this test asserted that gap was open —
    which is what kept it recorded rather than forgotten. ``20260922_006``
    closed it. The test is not deleted along with the gap: it now asserts the
    opposite, so a future migration that narrowed storage again would fail here
    instead of silently reopening a divergence this project already paid to find
    once.
    """
    assert set(STORAGE_SCOPE_TYPES) == set(SCOPE_TYPES)
    assert SCOPES_AWAITING_STORAGE_MIGRATION == ()
    # The pre-migration set is kept as history, and is still what it was.
    assert len(LEGACY_STORAGE_SCOPE_TYPES) == 4
    assert set(SCOPE_TYPES) - set(LEGACY_STORAGE_SCOPE_TYPES) == {"VERTICAL", "ENTITY"}


def test_the_live_storage_constraint_matches_the_contract() -> None:
    """Read the actual SQL, so this claim cannot rot into a comment."""
    migration = (
        REPO_ROOT
        / "supabase"
        / "migrations"
        / "20260922_006_brain_scope_vertical_entity_v01.sql"
    )
    sql = migration.read_text(encoding="utf-8")
    for scope in SCOPE_TYPES:
        assert f"'{scope}'" in sql, f"{scope} is not in the live scope constraint"
    assert "'COMPANY'" not in sql, "COMPANY became a scope"


def test_the_pre_migration_constraint_is_still_on_record() -> None:
    """The four-value constraint Brain-V1-A was written against is unchanged.

    ``20260922_006`` widens by replacing a constraint, not by editing ``004``.
    If ``004`` were rewritten in place, the migration history would no longer
    describe how the database actually got here.
    """
    migration = (
        REPO_ROOT
        / "supabase"
        / "migrations"
        / "20260920_004_n8n_brain_experience_and_runs_v01.sql"
    )
    sql = migration.read_text(encoding="utf-8")
    expected = "check (scope_type in ('GLOBAL_VORQUEL','CLIENT','PROJECT','PRIVATE_TEST'))"
    assert expected in sql, "migration 004 was edited in place instead of being superseded"


def test_no_unreviewed_migration_appears() -> None:
    """The migration set is pinned, so a new one cannot land unnoticed.

    Brain-V1-A asserted this set had five members and that it added none. It now
    has six: ``20260922_006`` is the migration DIV-3 deferred to Brain-V1-B, and
    it is named here because it was reviewed. The gate itself is unchanged — an
    unexpected seventh file still fails.
    """
    migrations = sorted((REPO_ROOT / "supabase" / "migrations").glob("*.sql"))
    names = {m.name for m in migrations}
    assert names == {
        "20260918_001_n8n_brain_knowledge_store_v01.sql",
        "20260918_002_n8n_brain_writer_role_v01.sql",
        "20260918_003_n8n_brain_writer_postgres_membership_v01.sql",
        "20260920_004_n8n_brain_experience_and_runs_v01.sql",
        "20260920_005_fix_touch_build_run_search_path.sql",
        "20260922_006_brain_scope_vertical_entity_v01.sql",
    }, f"unexpected migration set: {sorted(names)}"


# --- DIV-4 ----------------------------------------------------------------


def test_storage_spelling_is_ascii() -> None:
    assert "HIPOTESE" in EPISTEMIC_STATUSES
    assert "HIPÓTESE" not in EPISTEMIC_STATUSES


def test_accent_is_display_only() -> None:
    assert display_epistemic_status("HIPOTESE") == "HIPÓTESE"
    assert EPISTEMIC_STATUS_DISPLAY["HIPOTESE"] == "HIPÓTESE"


def test_no_schema_enum_carries_the_accent() -> None:
    """The accented form must never reach a machine-readable vocabulary."""
    blob = json.dumps(load_all_schemas(), ensure_ascii=False)
    assert "HIPÓTESE" not in blob


def test_epistemic_enum_matches_the_live_migration() -> None:
    migration = (
        REPO_ROOT
        / "supabase"
        / "migrations"
        / "20260920_004_n8n_brain_experience_and_runs_v01.sql"
    )
    sql = migration.read_text(encoding="utf-8")
    for status in EPISTEMIC_STATUSES:
        assert f"'{status}'" in sql, f"{status} is not in the live epistemic constraint"


# --- freshness -------------------------------------------------------------
#
# Not one of DIV-1..4. An earlier version of this package invented AGING and
# shortened UNKNOWN_FRESHNESS to UNKNOWN, which was an unapproved widening of a
# canonical vocabulary. These tests pin the contract's three values so the same
# drift cannot recur silently.


def test_freshness_matches_the_canonical_contract() -> None:
    assert FRESHNESS_STATUSES == ("FRESH", "STALE", "UNKNOWN_FRESHNESS")


def test_state_projection_freshness_enum_is_exactly_the_contract() -> None:
    schema = load_all_schemas()[
        "https://schemas.vorquel/brain/v1/state_projection.schema.json"
    ]
    assert schema["properties"]["freshness_status"]["enum"] == list(FRESHNESS_STATUSES)


def test_context_pack_freshness_enum_is_exactly_the_contract() -> None:
    schema = load_all_schemas()["https://schemas.vorquel/brain/v1/context_pack.schema.json"]
    assert schema["properties"]["freshness_status"]["enum"] == list(FRESHNESS_STATUSES)


def test_the_withdrawn_freshness_values_are_gone() -> None:
    """AGING and a bare UNKNOWN must not survive anywhere in the freshness axis.

    ``UNKNOWN`` is checked only against the freshness enums, not the whole
    schema set: it is a legitimate ``CANDIDATE_TYPES`` value, meaning a candidate
    that proposes an Unknown object, and that is unrelated to staleness.
    """
    assert "AGING" not in FRESHNESS_STATUSES
    assert "UNKNOWN" not in FRESHNESS_STATUSES

    blob = json.dumps(load_all_schemas())
    assert "AGING" not in blob, "AGING is still present in a schema"

    for uri, schema in load_all_schemas().items():
        freshness = schema.get("properties", {}).get("freshness_status")
        if freshness is None:
            continue
        assert "AGING" not in freshness["enum"], uri
        assert "UNKNOWN" not in freshness["enum"], uri


def test_no_machine_readable_freshness_alias_exists() -> None:
    """A second spelling is how a pinned vocabulary quietly comes unpinned."""
    import vorquel_brain_contract as contract

    assert not hasattr(contract, "FRESHNESS_STATUS_DISPLAY")
    assert not hasattr(contract, "FRESHNESS_ALIASES")


def test_verification_state_is_a_separate_axis() -> None:
    """The two vocabularies must not share a single value."""
    assert not set(EPISTEMIC_STATUSES) & set(VERIFICATION_STATES)
    assert VERIFICATION_STATES == (
        "UNREVIEWED",
        "REVIEWED",
        "APPROVED",
        "REJECTED",
        "SUPERSEDED",
    )
