"""Three things that have to hold for the rest of the suite to mean anything.

* the pipeline really runs relational-first, in the order it claims;
* the closed vocabularies agree across Python, the schemas and storage;
* Brain-V1-B stayed inside its boundary — no writes, no MCP, no new store.
"""

from __future__ import annotations

import inspect

import pytest
from vorquel_brain_contract import (
    BRAIN_V1_CONTROLLED_WRITES,
    BRAIN_V1_READS,
    FORBIDDEN_FIELD_NAMES,
    SCOPE_TYPES,
)

from vorquel_brain_retrieval import (
    IMPLEMENTED_READS,
    PIPELINE_STAGES,
    BrainStore,
    InMemoryBrainStore,
    ParityError,
    Scope,
    assert_parity,
    check_parity,
    parity_report,
    retrieve,
)
from vorquel_brain_retrieval.parity import STORAGE_COLUMNS, storage_enum

# ---------------------------------------------------------------------------
# Pipeline order
# ---------------------------------------------------------------------------


def test_the_pipeline_runs_the_contract_order(store, chaves):
    result = retrieve(
        store, "reduzir tempo de resposta ao lead", chaves, entity_query="Chaves & Hugo Imoveis"
    )
    assert result.trace.order() == PIPELINE_STAGES


def test_relational_retrieval_runs_before_lexical(store, chaves):
    result = retrieve(store, "tempo de resposta ao lead", chaves, entity_ids=("ent_chaves_hugo",))
    order = result.trace.order()
    assert order.index("STRUCTURED_RELATIONAL") < order.index("LEXICAL")
    assert order.index("SCOPE_GUARD") < order.index("STRUCTURED_RELATIONAL")
    # The scope guard is not the last thing that happens.
    assert order.index("SCOPE_GUARD") < order.index("CURRENT_STATE")


def test_a_structured_hit_outranks_a_purely_lexical_one(store, chaves):
    result = retrieve(store, "tempo de resposta ao lead", chaves, entity_ids=("ent_chaves_hugo",))
    hits = result.evidence.hits
    relational = [h for h in hits if "STRUCTURED_RELATIONAL" in h.retrieval_stages]
    lexical_only = [h for h in hits if h.retrieval_stages == ("LEXICAL",)]
    assert relational, "nothing matched structurally, so the ordering claim is untested"
    if lexical_only:
        assert min(h.retrieval_score for h in relational) > max(
            h.retrieval_score for h in lexical_only
        )


def test_the_trace_reports_the_semantic_stage_as_unavailable(store, chaves):
    result = retrieve(store, "qualquer coisa", chaves)
    assert result.trace.unavailable == ["SEMANTIC"]
    assert "SEMANTIC" not in result.trace.order()


def test_ambiguity_travels_with_the_result_instead_of_being_resolved(store, chaves):
    result = retrieve(store, "dor operacional", chaves, entity_query="Hugo")
    assert result.resolution.ambiguity
    assert result.resolution.resolved_entity_id is None
    # Every candidate is carried forward; none is silently preferred.
    assert len(result.entity_ids) > 1


# ---------------------------------------------------------------------------
# Enum parity
# ---------------------------------------------------------------------------


def test_python_schemas_and_storage_agree(repo_root):
    """The scratch audit, made permanent. A divergence fails CI."""
    assert_parity(repo_root)


def test_the_parity_check_actually_covers_something(repo_root):
    report = parity_report(repo_root)
    assert report["status"] == "OK"
    assert len(report["checked_python_vs_schema"]) >= 13
    assert set(report["checked_python_vs_storage"]) == set(STORAGE_COLUMNS)


def test_storage_accepts_all_six_contract_scopes(repo_root):
    """DIV-3 is closed: the contract is no longer ahead of storage."""
    assert set(storage_enum("scope_type", repo_root)) == set(SCOPE_TYPES)


def test_storage_uses_the_ascii_spelling(repo_root):
    """DIV-4 still holds: HIPOTESE in storage, the accent is display only."""
    stored = storage_enum("epistemic_status", repo_root)
    assert "HIPOTESE" in stored
    assert "HIPÓTESE" not in stored


def test_parity_detects_a_planted_divergence(repo_root, monkeypatch):
    """The test that proves the parity test can fail."""
    from vorquel_brain_retrieval import parity

    monkeypatch.setitem(parity.PYTHON_VOCABULARIES, "SCOPE_TYPES", (*SCOPE_TYPES, "COMPANY"))
    divergences = check_parity(repo_root)
    assert divergences
    with pytest.raises(ParityError, match="SCOPE_TYPES"):
        assert_parity(repo_root)


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def test_this_package_implements_the_six_reads_and_neither_write():
    import vorquel_brain_retrieval as pkg

    assert set(IMPLEMENTED_READS) == set(BRAIN_V1_READS)
    for write in BRAIN_V1_CONTROLLED_WRITES:
        assert not hasattr(pkg, write), (
            f"{write} is a Brain-V1-C controlled write and must not exist here"
        )


def test_the_storage_port_has_no_write_method():
    """A read path with no write method cannot grow one by accident."""
    methods = {name for name in dir(BrainStore) if not name.startswith("_")}
    assert methods == {"all_of", "by_id", "fingerprint"}
    for forbidden in ("write", "insert", "update", "delete", "save", "record", "upsert"):
        assert not hasattr(InMemoryBrainStore, forbidden)


def test_no_mcp_server_was_introduced():
    import vorquel_brain_retrieval as pkg

    source = "".join(
        inspect.getsource(module)
        for module in vars(pkg).values()
        if inspect.ismodule(module) and module.__name__.startswith("vorquel_brain_retrieval")
    )
    for forbidden in ("mcp.server", "FastMCP", "@mcp.tool", "stdio_server"):
        assert forbidden not in source


def test_nothing_in_the_package_takes_sql_shell_or_a_secret():
    """The forbidden field names never appear as a parameter of a public read."""
    import vorquel_brain_retrieval as pkg

    for name in IMPLEMENTED_READS:
        function = getattr(pkg, name, None)
        if function is None:
            continue
        parameters = set(inspect.signature(function).parameters)
        assert parameters.isdisjoint(FORBIDDEN_FIELD_NAMES), (
            f"{name} accepts a forbidden parameter"
        )


def test_the_package_does_not_import_a_vector_or_graph_database():
    import vorquel_brain_retrieval as pkg

    source = "".join(
        inspect.getsource(module)
        for module in vars(pkg).values()
        if inspect.ismodule(module) and module.__name__.startswith("vorquel_brain_retrieval")
    )
    for forbidden in ("import chromadb", "import qdrant", "import pinecone", "import neo4j",
                      "from neo4j", "import weaviate", "import pgvector"):
        assert forbidden not in source


def test_the_store_refuses_an_object_the_contract_would_reject():
    """A fixture cannot prove a rule by being malformed in a convenient way."""
    from vorquel_brain_retrieval import StoreIntegrityError

    with pytest.raises(StoreIntegrityError):
        InMemoryBrainStore.from_mapping(
            {"entities": [{"object_type": "Entity", "entity_id": "ent_x"}]}
        )


def test_the_store_refuses_an_unknown_collection():
    from vorquel_brain_retrieval import StoreIntegrityError

    with pytest.raises(StoreIntegrityError, match="unknown collection"):
        InMemoryBrainStore.from_mapping({"evidences": []})


def test_the_fixture_contains_no_real_client_identifier(store):
    """The dataset is synthetic, and stays synthetic."""
    import json
    from pathlib import Path

    raw = Path(__file__).resolve().parents[1] / "fixtures" / "brain_v1_b.json"
    text = raw.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert "synthetic" in payload["_comment"].lower()

    for marker in ("@gmail.", "@outlook.", "http://", "https://", "+55", "CPF", "CNPJ"):
        assert marker not in text, f"the fixture looks like it carries real data: {marker}"


def test_every_scope_in_the_fixture_is_a_contract_scope(store):
    for object_type in ("Entity", "Claim", "Evidence", "Decision", "Hypothesis", "Unknown",
                        "Event", "Source", "StateProjection"):
        for obj in store.all_of(object_type):
            raw = obj.get("scope") or obj.get("entity_scope")
            scope = Scope.from_mapping(raw)
            assert scope.scope_type in SCOPE_TYPES
